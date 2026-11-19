"""Synthetic canaries for scope, job authenticity, upload and encryption controls.

In-memory Redis doubles establish client failure/contract behavior. The separate
integration case executes real Redis Lua; it is not inferred from the doubles.
"""

import asyncio
import io
import os
import struct
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

import pytest
from insightrag.security.controls import (
    ControlUnavailable,
    JobEnvelopeRejected,
    RateLimiter,
    RateLimitExceeded,
    SignedJobEnvelope,
    assert_object_scope,
    cache_key,
    object_key,
)
from insightrag.security.crypto import (
    EncryptionRejected,
    EnvelopeCipher,
    LocalKeyProvider,
)
from insightrag.security.uploads import (
    ClamAVScanner,
    ScannerUnavailable,
    UploadRejected,
    validate_upload,
)
from redis.asyncio import Redis


class CleanScanner:
    async def scan(self, data: bytes) -> Literal["clean", "infected"]:
        return "clean"


class InfectedScanner:
    async def scan(self, data: bytes) -> Literal["clean", "infected"]:
        return "infected"


async def chunks(data: bytes):
    for offset in range(0, len(data), 3):
        yield data[offset : offset + 3]


def office_zip(
    extra: tuple[str, bytes] | None = None,
    *,
    suffix: str = ".docx",
    compression: int = zipfile.ZIP_STORED,
) -> bytes:
    output = io.BytesIO()
    manifest = (
        b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        if suffix == ".docx"
        else b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    )
    name = "word/document.xml" if suffix == ".docx" else "xl/workbook.xml"
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                b'<Override PartName="/'
                + name.encode()
                + b'" ContentType="'
                + manifest
                + b'"/></Types>'
            ),
        )
        archive.writestr(name, b"<document>synthetic</document>")
        if extra:
            archive.writestr(*extra)
    return output.getvalue()


def test_cache_keys_change_for_every_access_and_version_boundary():
    organization, user, resource, version = (uuid4() for _ in range(4))
    original = cache_key(organization, user, 1, resource, version, "answer")
    alternatives = {
        cache_key(uuid4(), user, 1, resource, version, "answer"),
        cache_key(organization, uuid4(), 1, resource, version, "answer"),
        cache_key(organization, user, 2, resource, version, "answer"),
        cache_key(organization, user, 1, uuid4(), version, "answer"),
        cache_key(organization, user, 1, resource, uuid4(), "answer"),
        cache_key(organization, user, 1, resource, version, "chart"),
    }
    assert original not in alternatives
    assert len(alternatives) == 6
    with pytest.raises(ValueError):
        cache_key(organization, user, -1, resource, version, "answer")


def test_object_scope_denies_other_tenants_workspaces_and_traversal():
    organization, workspace, resource, version = (uuid4() for _ in range(4))
    key = object_key(organization, workspace, resource, version)
    assert_object_scope(key, organization, workspace)
    for bad_key, bad_org, bad_workspace in (
        (key, uuid4(), workspace),
        (key, organization, uuid4()),
        (key + "/../source", organization, workspace),
        (key.replace("/source", "/source%2f.."), organization, workspace),
    ):
        with pytest.raises(PermissionError):
            assert_object_scope(bad_key, bad_org, bad_workspace)


async def test_quota_missing_or_broken_redis_fails_closed():
    organization, user = uuid4(), uuid4()
    with pytest.raises(ControlUnavailable):
        await RateLimiter(None).check(organization, user, limit=1)

    class BrokenRedis:
        async def eval(self, *args):
            raise RuntimeError("synthetic-secret")

    with pytest.raises(ControlUnavailable, match="^Rate limiting is unavailable$"):
        await RateLimiter(cast(Redis, BrokenRedis())).check(organization, user, limit=1)


async def test_quota_rejection_is_distinct_from_protection_failure():
    class RejectingRedis:
        async def eval(self, script, key_count, key, window, limit):
            assert "redis.call('TIME')" in script
            assert key_count == 1 and window == 60 and limit == 3
            return [0, 42]

    with pytest.raises(RateLimitExceeded) as caught:
        await RateLimiter(cast(Redis, RejectingRedis())).check(uuid4(), uuid4(), limit=3)
    assert caught.value.retry_after == 42


def test_signed_jobs_bind_identity_and_reject_tampering_expiry_and_wrong_key():
    clock = [1000.0]
    signer = SignedJobEnvelope(os.urandom(32), clock=lambda: clock[0])
    ids = [uuid4() for _ in range(4)]
    token = signer.issue(*ids, policy_revision=7)
    claims = signer.verify(token)
    assert [claims.organization_id, claims.user_id, claims.job_id, claims.resource_id] == ids
    assert claims.policy_revision == 7
    body, signature = token.split(".")
    mutated = ("A" if body[0] != "A" else "B") + body[1:] + "." + signature
    for invalid in (mutated, "not.a.valid.envelope"):
        with pytest.raises(JobEnvelopeRejected):
            signer.verify(invalid)
    with pytest.raises(JobEnvelopeRejected):
        SignedJobEnvelope(os.urandom(32), clock=lambda: clock[0]).verify(token)
    clock[0] = 1300
    with pytest.raises(JobEnvelopeRejected):
        signer.verify(token)


async def test_signed_jobs_replay_guard_allows_one_concurrent_consumer():
    class ReplayRedis:
        def __init__(self):
            self.values = set()
            self.lock = asyncio.Lock()

        async def set(self, name, value, *, nx, ex):
            assert nx and 0 < ex <= 300
            async with self.lock:
                if name in self.values:
                    return None
                self.values.add(name)
                return True

    signer = SignedJobEnvelope(os.urandom(32))
    token = signer.issue(*(uuid4() for _ in range(4)), policy_revision=1)
    redis = cast(Redis, ReplayRedis())
    results = await asyncio.gather(
        *(signer.verify_once(token, redis) for _ in range(8)), return_exceptions=True
    )
    assert sum(not isinstance(value, BaseException) for value in results) == 1
    assert sum(isinstance(value, JobEnvelopeRejected) for value in results) == 7
    with pytest.raises(ControlUnavailable):
        await signer.verify_once(token, None)


async def test_upload_requires_clean_scanner_and_detected_content():
    with pytest.raises(ScannerUnavailable):
        await validate_upload(chunks(b"synthetic"), filename="note.txt", content_type="text/plain")
    with pytest.raises(UploadRejected) as infected:
        await validate_upload(
            chunks(b"synthetic"),
            filename="note.txt",
            content_type="text/plain",
            scanner=InfectedScanner(),
        )
    assert infected.value.code == "malware_detected"
    result = await validate_upload(
        chunks(b"synthetic"), filename="note.txt", content_type="text/plain", scanner=CleanScanner()
    )
    assert result.size_bytes == 9 and len(result.sha256) == 64 and result.media_type == "text/plain"
    with pytest.raises(UploadRejected):
        await validate_upload(
            chunks(b"not a PDF"),
            filename="report.pdf",
            content_type="application/pdf",
            scanner=CleanScanner(),
        )


@pytest.mark.parametrize(
    "filename,data,content_type,limit",
    [
        ("../report.txt", b"text", "text/plain", 100),
        ("macro.xlsm", b"text", "application/octet-stream", 100),
        ("report.txt", b"text", "application/pdf", 100),
        ("report.txt", b"text", "text/plain", 3),
        ("report.txt", b"", "text/plain", 100),
        ("report.txt", b"binary\x00text", "text/plain", 100),
        ("report.pdf", b"%PDF-1.7 /JavaScript", "application/pdf", 100),
    ],
)
async def test_upload_rejects_unsafe_name_type_size_and_active_content(
    filename, data, content_type, limit
):
    with pytest.raises(UploadRejected):
        await validate_upload(
            chunks(data),
            filename=filename,
            content_type=content_type,
            scanner=CleanScanner(),
            max_file_bytes=limit,
        )


@pytest.mark.parametrize(
    "extra",
    [("../escaped.xml", b"unsafe"), ("word/vbaProject.bin", b"macro"), ("nested.zip", b"archive")],
)
async def test_office_archive_rejects_traversal_macros_and_nested_archives(extra):
    with pytest.raises(UploadRejected):
        await validate_upload(
            chunks(office_zip(extra)),
            filename="report.docx",
            content_type=None,
            scanner=CleanScanner(),
        )


async def test_office_archive_checks_expansion_and_actual_type():
    bomb = office_zip(("word/large.xml", b"A" * 100000), compression=zipfile.ZIP_DEFLATED)
    with pytest.raises(UploadRejected) as failure:
        await validate_upload(
            chunks(bomb), filename="report.docx", content_type=None, scanner=CleanScanner()
        )
    assert failure.value.code == "archive_expansion_limit"
    with pytest.raises(UploadRejected):
        await validate_upload(
            chunks(office_zip()), filename="report.xlsx", content_type=None, scanner=CleanScanner()
        )
    result = await validate_upload(
        chunks(office_zip()), filename="report.docx", content_type=None, scanner=CleanScanner()
    )
    assert result.suffix == ".docx"


async def test_office_manifest_comments_and_symlink_members_cannot_pass_validation():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                "<!-- application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document.main+xml -->"
                "</Types>"
            ),
        )
        archive.writestr("word/document.xml", "<document/>")
    with pytest.raises(UploadRejected):
        await validate_upload(
            chunks(output.getvalue()),
            filename="spoof.docx",
            content_type=None,
            scanner=CleanScanner(),
        )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        link = zipfile.ZipInfo("word/link")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        archive.writestr(link, "../../outside")
    with pytest.raises(UploadRejected) as failure:
        await validate_upload(
            chunks(output.getvalue()),
            filename="link.docx",
            content_type=None,
            scanner=CleanScanner(),
        )
    assert failure.value.code == "unsafe_archive_member"


async def test_scanner_timeout_is_fail_closed():
    class SlowScanner:
        async def scan(self, data):
            await asyncio.sleep(1)
            return "clean"

    with pytest.raises(ScannerUnavailable):
        await validate_upload(
            chunks(b"synthetic"),
            filename="report.txt",
            content_type=None,
            scanner=SlowScanner(),
            scanner_timeout_seconds=0.01,
        )


async def test_clamav_stream_protocol_and_unexpected_reply_fail_closed():
    replies = [b"stream: OK\0", b"stream: Synthetic-Test FOUND\0", b"stream: ERROR\0"]
    captured = []

    async def daemon(reader, writer):
        assert await reader.readuntil(b"\0") == b"zINSTREAM\0"
        body = bytearray()
        while size := struct.unpack("!I", await reader.readexactly(4))[0]:
            body.extend(await reader.readexactly(size))
        captured.append(bytes(body))
        writer.write(replies.pop(0))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(daemon, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        scanner = ClamAVScanner("127.0.0.1", port)
        assert await scanner.scan(b"synthetic") == "clean"
        assert await scanner.scan(b"synthetic") == "infected"
        with pytest.raises(ScannerUnavailable):
            await scanner.scan(b"synthetic")
    assert captured == [b"synthetic"] * 3


async def test_envelope_encryption_binds_both_tenant_and_resource_and_rejects_tamper():
    organization, resource = uuid4(), uuid4()
    provider = LocalKeyProvider("synthetic-test-key", os.urandom(32), environment="test")
    cipher = EnvelopeCipher(provider, "synthetic-test-key")
    encrypted = await cipher.encrypt(organization, resource, b"synthetic-private-document")
    assert b"synthetic-private-document" not in encrypted.ciphertext
    assert await cipher.decrypt(organization, resource, encrypted) == b"synthetic-private-document"
    for other_org, other_resource in ((uuid4(), resource), (organization, uuid4())):
        with pytest.raises(EncryptionRejected):
            await cipher.decrypt(other_org, other_resource, encrypted)
    with pytest.raises(EncryptionRejected):
        await cipher.decrypt(
            organization,
            resource,
            replace(
                encrypted,
                ciphertext=encrypted.ciphertext[:-1] + bytes([encrypted.ciphertext[-1] ^ 1]),
            ),
        )
    with pytest.raises(ControlUnavailable):
        await EnvelopeCipher(None, "synthetic-test-key").encrypt(organization, resource, b"data")
    with pytest.raises(ValueError):
        LocalKeyProvider("synthetic-test-key", os.urandom(32), environment="production")


@pytest.mark.integration
async def test_real_redis_quota_is_atomic_under_concurrency():
    file = os.getenv("INSIGHTRAG_TEST_REDIS_URL_FILE")
    url = (
        (await asyncio.to_thread(Path(file).read_text)).strip()
        if file
        else os.getenv("INSIGHTRAG_TEST_REDIS_URL")
    )
    if not url:
        if os.getenv("CI"):
            pytest.fail("CI requires real Redis test configuration")
        pytest.skip("Real Redis test configuration not supplied")
    redis = Redis.from_url(url)
    organization, user = uuid4(), uuid4()
    limiter = RateLimiter(redis)
    try:
        results = await asyncio.gather(
            *(limiter.check(organization, user, limit=3) for _ in range(10)), return_exceptions=True
        )
        assert sum(value is None for value in results) == 3
        assert sum(isinstance(value, RateLimitExceeded) for value in results) == 7
    finally:
        await redis.delete(f"quota:v1:{organization}:{user}:api")
        await redis.aclose()
