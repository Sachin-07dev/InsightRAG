"""Bounded upload quarantine checks and a fail-closed ClamAV INSTREAM adapter.

Validation does not parse/index content or establish authorization. Phase 4 must
retain scanner freshness, isolated parsers and immutable quarantine publication.
"""

import asyncio
import hashlib
import io
import re
import stat
import struct
import zipfile
import zlib
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal, Protocol
from xml.etree import ElementTree

from insightrag.security.controls import ControlUnavailable

MAX_FILE_BYTES = 50 * 1024 * 1024
_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class UploadRejected(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__("Upload failed security validation")
        self.code = code


class ScannerUnavailable(ControlUnavailable):
    """No clean verdict means the upload remains rejected/quarantined."""


class MalwareScanner(Protocol):
    async def scan(self, data: bytes) -> Literal["clean", "infected"]: ...


class UnavailableScanner:
    async def scan(self, data: bytes) -> Literal["clean", "infected"]:
        raise ScannerUnavailable("Malware scanner is unavailable")


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    suffix: str
    media_type: str
    sha256: str
    size_bytes: int
    data: bytes = field(default=b"", repr=False, compare=False)


def _inspect_zip(data: bytes, suffix: str) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if not members or len(members) > 1000:
                raise UploadRejected("archive_member_limit")
            names: set[str] = set()
            expanded = actual_total = 0
            for member in members:
                name = member.filename
                parts = PurePosixPath(name).parts
                if (
                    name.startswith(("/", "\\"))
                    or "\\" in name
                    or ":" in name
                    or ".." in parts
                    or any(ord(character) < 32 for character in name)
                    or name in names
                ):
                    raise UploadRejected("unsafe_archive_path")
                names.add(name)
                if stat.S_IFMT(member.external_attr >> 16) == stat.S_IFLNK or member.flag_bits & 1:
                    raise UploadRejected("unsafe_archive_member")
                if member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise UploadRejected("unsupported_archive_compression")
                lower = name.lower()
                if "vbaproject" in lower or lower.endswith(
                    (".zip", ".7z", ".rar", ".gz", ".docm", ".xlsm", ".docx", ".xlsx")
                ):
                    raise UploadRejected("active_or_nested_archive")
                expanded += member.file_size
                if (
                    expanded > 200 * 1024 * 1024
                    or member.file_size > max(member.compress_size, 1) * 100
                ):
                    raise UploadRejected("archive_expansion_limit")
                with archive.open(member) as stream:
                    while chunk := stream.read(65536):
                        actual_total += len(chunk)
                        if actual_total > 200 * 1024 * 1024:
                            raise UploadRejected("archive_expansion_limit")
            required = "word/document.xml" if suffix == ".docx" else "xl/workbook.xml"
            if "[Content_Types].xml" not in names or required not in names:
                raise UploadRejected("archive_type_mismatch")
            types = archive.getinfo("[Content_Types].xml")
            if types.file_size > 1024 * 1024:
                raise UploadRejected("archive_manifest_limit")
            manifest = archive.read(types)
            if any(
                marker in manifest.lower()
                for marker in (b"macroenabled", b"vbaproject", b"<!doctype", b"<!entity")
            ):
                raise UploadRejected("archive_type_mismatch")
            root = ElementTree.fromstring(manifest)
            namespace = "{http://schemas.openxmlformats.org/package/2006/content-types}"
            expected = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
                if suffix == ".docx"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
            )
            if root.tag != namespace + "Types" or not any(
                member.tag == namespace + "Override"
                and member.attrib.get("PartName") == "/" + required
                and member.attrib.get("ContentType") == expected
                for member in root
            ):
                raise UploadRejected("archive_type_mismatch")
    except UploadRejected:
        raise
    except (
        zipfile.BadZipFile,
        RuntimeError,
        OSError,
        ValueError,
        NotImplementedError,
        zlib.error,
        ElementTree.ParseError,
    ):
        raise UploadRejected("invalid_archive") from None


async def validate_upload(
    stream: AsyncIterable[bytes],
    *,
    filename: str,
    content_type: str | None,
    scanner: MalwareScanner | None = None,
    max_file_bytes: int = MAX_FILE_BYTES,
    scanner_timeout_seconds: float = 15,
) -> ValidatedUpload:
    if not 1 <= max_file_bytes <= MAX_FILE_BYTES:
        raise ValueError("Invalid upload byte limit")
    if not 0 < scanner_timeout_seconds <= 60:
        raise ValueError("Invalid scanner timeout")
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,127}", filename)
        or ".." in filename
        or filename.endswith((".", " "))
    ):
        raise UploadRejected("unsafe_filename")
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in _MEDIA_TYPES:
        raise UploadRejected("unsupported_file_type")
    body = bytearray()
    async for chunk in stream:
        if not isinstance(chunk, bytes) or len(body) + len(chunk) > max_file_bytes:
            raise UploadRejected("file_size_limit")
        body.extend(chunk)
    if not body:
        raise UploadRejected("empty_file")
    data = bytes(body)
    del body
    media_type = _MEDIA_TYPES[suffix]
    supplied_type = content_type.split(";", 1)[0].strip().lower() if content_type else None
    permitted_types = {media_type, "application/octet-stream", None}
    if suffix == ".csv":
        permitted_types.add("text/plain")
    if supplied_type not in permitted_types:
        raise UploadRejected("media_type_mismatch")
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadRejected("signature_mismatch")
        if any(
            marker in data
            for marker in (b"/Encrypt", b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile")
        ):
            raise UploadRejected("active_or_encrypted_pdf")
    elif suffix in (".docx", ".xlsx"):
        if not data.startswith(b"PK\x03\x04"):
            raise UploadRejected("signature_mismatch")
        await asyncio.to_thread(_inspect_zip, data, suffix)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise UploadRejected("text_encoding") from None
        if any(ord(character) < 32 and character not in "\t\r\n" for character in text):
            raise UploadRejected("binary_text")
    try:
        async with asyncio.timeout(scanner_timeout_seconds):
            verdict = await (scanner or UnavailableScanner()).scan(data)
    except ScannerUnavailable:
        raise
    except Exception:
        raise ScannerUnavailable("Malware scanner is unavailable") from None
    if verdict == "infected":
        raise UploadRejected("malware_detected")
    if verdict != "clean":
        raise ScannerUnavailable("Malware scanner did not return a clean verdict")
    return ValidatedUpload(
        filename, suffix, media_type, hashlib.sha256(data).hexdigest(), len(data), data
    )


class ClamAVScanner:
    """Configured internal host only; clamd TCP itself has no authentication/TLS."""

    def __init__(
        self,
        host: str,
        port: int = 3310,
        *,
        timeout_seconds: float = 10,
        max_bytes: int = MAX_FILE_BYTES,
    ) -> None:
        if (
            not host
            or len(host) > 253
            or any(character.isspace() for character in host)
            or "/" in host
        ):
            raise ValueError("Invalid scanner host")
        if (
            not 1 <= port <= 65535
            or not 0 < timeout_seconds <= 60
            or not 1 <= max_bytes <= MAX_FILE_BYTES
        ):
            raise ValueError("Invalid scanner limits")
        self.host, self.port, self.timeout_seconds, self.max_bytes = (
            host,
            port,
            timeout_seconds,
            max_bytes,
        )

    async def scan(self, data: bytes) -> Literal["clean", "infected"]:
        if len(data) > self.max_bytes:
            raise UploadRejected("scanner_size_limit")
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                reader, writer = await asyncio.open_connection(self.host, self.port, limit=1024)
                writer.write(b"zINSTREAM\0")
                for offset in range(0, len(data), 65536):
                    chunk = data[offset : offset + 65536]
                    writer.write(struct.pack("!I", len(chunk)) + chunk)
                    await writer.drain()
                writer.write(b"\0\0\0\0")
                await writer.drain()
                result = (await reader.readuntil(b"\0")).removesuffix(b"\0")
                if result == b"stream: OK":
                    return "clean"
                if result.startswith(b"stream: ") and result.endswith(b" FOUND"):
                    return "infected"
                raise ScannerUnavailable("Malware scanner did not return a clean verdict")
        except ScannerUnavailable:
            raise
        except Exception:
            raise ScannerUnavailable("Malware scanner is unavailable") from None
        finally:
            if writer is not None:
                writer.close()
                try:
                    async with asyncio.timeout(1):
                        await writer.wait_closed()
                except Exception:
                    pass
