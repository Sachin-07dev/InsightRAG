"""Tenant-scoped object/cache keys, atomic quotas and signed worker identities.

These adapters do not establish authorization. Inputs must come from trusted
identity/policy code, and workers must reauthorize current DB state before use.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import math
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from redis.asyncio import Redis


class ControlUnavailable(RuntimeError):
    """A required protection is unavailable; callers must not proceed."""


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Request quota exceeded")
        self.retry_after = retry_after


class JobEnvelopeRejected(ValueError):
    """Invalid, expired or replayed worker envelope."""


def _purpose(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_.:-]{0,63}", value):
        raise ValueError("Invalid protection purpose")
    return value


def cache_key(
    organization_id: UUID,
    user_id: UUID,
    policy_revision: int,
    resource_id: UUID,
    version_id: UUID,
    purpose: str,
) -> str:
    if not all(
        isinstance(value, UUID) for value in (organization_id, user_id, resource_id, version_id)
    ):
        raise ValueError("Cache identities must be UUIDs")
    if type(policy_revision) is not int or policy_revision < 0:
        raise ValueError("Invalid authorization revision")
    identity = [
        str(organization_id),
        str(user_id),
        policy_revision,
        str(resource_id),
        str(version_id),
        _purpose(purpose),
    ]
    digest = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
    return f"cache:v1:{organization_id}:{digest}"


def object_key(
    organization_id: UUID, workspace_id: UUID, resource_id: UUID, version_id: UUID
) -> str:
    # UUID values, rather than filenames or model text, define physical identity.
    values = [organization_id, workspace_id, resource_id, version_id]
    if not all(isinstance(value, UUID) for value in values):
        raise ValueError("Object identities must be UUIDs")
    return (
        f"organizations/{organization_id}/workspaces/{workspace_id}/"
        f"resources/{resource_id}/versions/{version_id}/source"
    )


def assert_object_scope(key: str, organization_id: UUID, workspace_id: UUID) -> None:
    """Validate the complete generated grammar, not a permissive prefix match."""
    parts = key.split("/")
    try:
        if len(parts) != 9 or parts[0::2] != [
            "organizations",
            "workspaces",
            "resources",
            "versions",
            "source",
        ]:
            raise ValueError
        parsed = [UUID(value) for value in parts[1::2]]
        if key != object_key(*parsed) or parsed[0] != organization_id or parsed[1] != workspace_id:
            raise ValueError
    except (ValueError, TypeError):
        raise PermissionError("Object scope denied") from None


_QUOTA_SCRIPT = """
local stamp = redis.call('TIME')
local now = tonumber(stamp[1])
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local period = math.floor(now / window)
local stored = tonumber(redis.call('HGET', KEYS[1], 'period'))
if stored ~= period then
  redis.call('HSET', KEYS[1], 'period', period, 'count', 0)
end
redis.call('EXPIRE', KEYS[1], window + 1)
local count = tonumber(redis.call('HGET', KEYS[1], 'count'))
local retry_after = math.max(1, (period + 1) * window - now)
if count >= limit then return {0, retry_after} end
redis.call('HINCRBY', KEYS[1], 'count', 1)
return {1, retry_after}
"""


class RateLimiter:
    def __init__(self, redis: Redis | None, *, timeout_seconds: float = 2) -> None:
        if not 0 < timeout_seconds <= 10:
            raise ValueError("Invalid quota timeout")
        self.redis = redis
        self.timeout_seconds = timeout_seconds

    async def check(
        self,
        organization_id: UUID,
        user_id: UUID,
        *,
        limit: int,
        window_seconds: int = 60,
        purpose: str = "api",
    ) -> None:
        if not isinstance(organization_id, UUID) or not isinstance(user_id, UUID):
            raise ValueError("Quota identities must be UUIDs")
        if not 1 <= limit <= 1_000_000 or not 1 <= window_seconds <= 3600:
            raise ValueError("Invalid quota limits")
        key = f"quota:v1:{organization_id}:{user_id}:{_purpose(purpose)}"
        if self.redis is None:
            raise ControlUnavailable("Rate limiting is unavailable")
        try:
            async with asyncio.timeout(self.timeout_seconds):
                result = await cast(
                    Awaitable[object], self.redis.eval(_QUOTA_SCRIPT, 1, key, window_seconds, limit)
                )
            if not isinstance(result, list) or len(result) != 2 or result[0] not in (0, 1):
                raise ValueError("Unexpected quota result")
            allowed, retry_after = int(result[0]), int(result[1])
            if not 1 <= retry_after <= window_seconds:
                raise ValueError("Unexpected quota interval")
        except Exception:
            raise ControlUnavailable("Rate limiting is unavailable") from None
        if not allowed:
            raise RateLimitExceeded(retry_after)


@dataclass(frozen=True)
class JobClaims:
    organization_id: UUID
    user_id: UUID
    job_id: UUID
    resource_id: UUID
    policy_revision: int
    issued_at: int
    expires_at: int
    nonce: UUID


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid encoding")
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


class SignedJobEnvelope:
    """HMAC protects identity claims, not permission freshness or idempotent effects."""

    def __init__(
        self,
        signing_key: bytes,
        *,
        clock: Callable[[], float] = time.time,
        lifetime_seconds: int = 300,
    ) -> None:
        if len(signing_key) < 32 or not 1 <= lifetime_seconds <= 300:
            raise ValueError("A >=32-byte signing key and bounded lifetime are required")
        self._key, self._clock, self._lifetime = signing_key, clock, lifetime_seconds

    def issue(
        self,
        organization_id: UUID,
        user_id: UUID,
        job_id: UUID,
        resource_id: UUID,
        policy_revision: int,
    ) -> str:
        if not all(
            isinstance(value, UUID) for value in (organization_id, user_id, job_id, resource_id)
        ):
            raise ValueError("Job identities must be UUIDs")
        if type(policy_revision) is not int or policy_revision < 0:
            raise ValueError("Invalid authorization revision")
        now = int(self._clock())
        payload = json.dumps(
            {
                "v": 1,
                "org": str(organization_id),
                "usr": str(user_id),
                "job": str(job_id),
                "res": str(resource_id),
                "revision": policy_revision,
                "iat": now,
                "exp": now + self._lifetime,
                "nonce": str(uuid4()),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return f"{_encode(payload)}.{_encode(hmac.digest(self._key, payload, 'sha256'))}"

    def verify(self, token: str) -> JobClaims:
        try:
            if len(token) > 4096 or token.count(".") != 1:
                raise ValueError
            body, signature = token.split(".")
            payload, supplied_mac = _decode(body), _decode(signature)
            if not hmac.compare_digest(supplied_mac, hmac.digest(self._key, payload, "sha256")):
                raise ValueError
            value = json.loads(payload)
            if (
                set(value) != {"v", "org", "usr", "job", "res", "revision", "iat", "exp", "nonce"}
                or value["v"] != 1
            ):
                raise ValueError
            for field in ("revision", "iat", "exp"):
                if type(value[field]) is not int or value[field] < 0:
                    raise ValueError
            now = int(self._clock())
            if (
                value["iat"] > now + 5
                or now >= value["exp"]
                or not 0 < value["exp"] - value["iat"] <= self._lifetime
            ):
                raise ValueError
            return JobClaims(
                UUID(value["org"]),
                UUID(value["usr"]),
                UUID(value["job"]),
                UUID(value["res"]),
                value["revision"],
                value["iat"],
                value["exp"],
                UUID(value["nonce"]),
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            raise JobEnvelopeRejected("Invalid or expired worker envelope") from None

    async def verify_once(self, token: str, redis: Redis | None) -> JobClaims:
        claims = self.verify(token)
        if redis is None:
            raise ControlUnavailable("Worker replay protection is unavailable")
        ttl = math.ceil(claims.expires_at - self._clock())
        if ttl <= 0:
            raise JobEnvelopeRejected("Invalid or expired worker envelope")
        key = f"job-replay:v1:{claims.organization_id}:{claims.nonce}"
        try:
            async with asyncio.timeout(2):
                accepted = await redis.set(key, "1", nx=True, ex=ttl)
        except Exception:
            raise ControlUnavailable("Worker replay protection is unavailable") from None
        if not accepted:
            raise JobEnvelopeRejected("Worker envelope already consumed")
        return claims
