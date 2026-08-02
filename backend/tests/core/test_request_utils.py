"""Unit tests for client-IP header-precedence, fallback, and source attribution."""
from fastapi import Request

from core.request_utils import resolve_client_ip


def _request(
    headers: dict[str, str] | None = None,
    client: tuple[str, int] | None = None,
) -> Request:
    """Build a minimal ASGI Request with the given headers and client peer."""
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw_headers, "client": client})


def test__prefers_x_real_ip_over_forwarded_for() -> None:
    """X-Real-IP (edge-set, non-spoofable) wins over a client-settable XFF."""
    request = _request({"X-Real-IP": "1.1.1.1", "X-Forwarded-For": "2.2.2.2"})
    assert resolve_client_ip(request)[0] == "1.1.1.1"


def test__blank_x_real_ip_falls_through_to_forwarded_for() -> None:
    """A present-but-blank X-Real-IP is ignored, falling through to XFF."""
    request = _request({"X-Real-IP": "   ", "X-Forwarded-For": "2.2.2.2, 3.3.3.3"})
    assert resolve_client_ip(request)[0] == "2.2.2.2"


def test__uses_first_forwarded_for_entry_when_no_real_ip() -> None:
    """Without X-Real-IP, the first X-Forwarded-For entry is used."""
    request = _request({"X-Forwarded-For": "2.2.2.2, 3.3.3.3"})
    assert resolve_client_ip(request)[0] == "2.2.2.2"


def test__blank_forwarded_for_falls_through_to_client_host() -> None:
    """A present-but-blank XFF entry is ignored, falling through to the peer."""
    request = _request({"X-Forwarded-For": " , "}, client=("9.9.9.9", 5000))
    assert resolve_client_ip(request)[0] == "9.9.9.9"


def test__falls_back_to_client_host_when_no_headers() -> None:
    """With no proxy headers, the direct connection peer is used."""
    request = _request(client=("9.9.9.9", 5000))
    assert resolve_client_ip(request)[0] == "9.9.9.9"


def test__returns_none_when_no_signal() -> None:
    """No headers and no client peer yields None."""
    request = _request(client=None)
    assert resolve_client_ip(request)[0] is None


def test__resolve_reports_x_real_ip_source() -> None:
    """resolve_client_ip flags X-Real-IP as the source when present."""
    request = _request({"X-Real-IP": "1.1.1.1", "X-Forwarded-For": "2.2.2.2"})
    assert resolve_client_ip(request) == ("1.1.1.1", "x-real-ip")


def test__resolve_reports_forwarded_for_source() -> None:
    """Without X-Real-IP, the source is the (spoofable) X-Forwarded-For fallback."""
    request = _request({"X-Forwarded-For": "2.2.2.2, 3.3.3.3"})
    assert resolve_client_ip(request) == ("2.2.2.2", "x-forwarded-for")


def test__resolve_reports_socket_source() -> None:
    """With no proxy headers, the source is the direct connection peer."""
    request = _request(client=("9.9.9.9", 5000))
    assert resolve_client_ip(request) == ("9.9.9.9", "socket")


def test__resolve_reports_none_source_when_no_signal() -> None:
    """No headers and no peer yields (None, "none")."""
    request = _request(client=None)
    assert resolve_client_ip(request) == (None, "none")
