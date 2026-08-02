"""Request-level helpers shared across routers."""
from fastapi import Request


def resolve_client_ip(request: Request) -> tuple[str | None, str]:
    """
    Resolve the client IP *and* report which signal it came from.

    Prefers ``X-Real-IP``, which Railway's edge sets to the client's remote IP
    and which clients cannot set themselves (Railway docs → Public Networking →
    Specs & Limits → Request Headers documents ``X-Real-IP`` as *the* client-IP
    header; it does not list ``X-Forwarded-For``). Falls back to
    ``X-Forwarded-For`` (first entry) and then the direct connection so local dev
    and non-Railway hosts still resolve.

    Spoofability boundary: only the ``X-Real-IP`` path is spoof-resistant. The
    ``X-Forwarded-For`` fallback is client-settable, so callers using this for
    abuse mitigation get a hard guarantee only when ``X-Real-IP`` is present.
    Confirmed against production (2026-06-21): Railway's edge sets ``X-Real-IP``
    to the true client IP and overwrites any client-supplied value (an observed
    ``/public/*`` request resolved ``ip_source=x-real-ip`` to the real IP, and a
    forged ``X-Real-IP`` was overwritten — the 429 log recorded the real IP, not
    the forged value), so the per-IP limit keys on a trustworthy address.

    Returning the source alongside the address lets abuse logging record whether
    that spoof-resistant header was actually present on a throttled request —
    without it, a per-IP 429 cannot be told apart from one keyed on a forged
    address.

    Returns:
        ``(ip, source)`` where ``source`` is one of ``"x-real-ip"``,
        ``"x-forwarded-for"``, ``"socket"``, or ``"none"`` (nothing resolved).
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip(), "x-real-ip"

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first, "x-forwarded-for"

    if request.client:
        return request.client.host, "socket"

    return None, "none"
