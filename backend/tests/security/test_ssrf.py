"""
SSRF (Server-Side Request Forgery) security tests.

These tests verify that the URL scraping functionality properly blocks
requests to internal/private network addresses.

OWASP Reference: A10:2021 - Server-Side Request Forgery (SSRF)
"""
import pytest

from services.url_scraper import (
    SSRFBlockedError,
    fetch_url,
    is_private_ip,
    validate_url_not_private,
)


class TestPrivateIPDetection:
    """Test the is_private_ip function."""

    @pytest.mark.parametrize("ip", [
        "10.0.0.1",       # Private Class A
        "10.255.255.255", # Private Class A
        "172.16.0.1",     # Private Class B
        "172.31.255.255", # Private Class B
        "192.168.0.1",    # Private Class C
        "192.168.255.255", # Private Class C
        "127.0.0.1",      # Loopback
        "127.0.0.2",      # Loopback range
        "169.254.0.1",    # Link-local
        "224.0.0.1",      # Multicast
        "0.0.0.0",        # Unspecified
    ])
    def test__is_private_ip__detects_private_ipv4(self, ip: str) -> None:
        """Private/internal IPv4 addresses are detected."""
        assert is_private_ip(ip) is True

    @pytest.mark.parametrize("ip", [
        "::1",            # IPv6 loopback
        "fe80::1",        # IPv6 link-local
        "fc00::1",        # IPv6 unique local
        "fd00::1",        # IPv6 unique local
        "ff02::1",        # IPv6 multicast
    ])
    def test__is_private_ip__detects_private_ipv6(self, ip: str) -> None:
        """Private/internal IPv6 addresses are detected."""
        assert is_private_ip(ip) is True

    @pytest.mark.parametrize("ip", [
        "8.8.8.8",        # Google DNS
        "1.1.1.1",        # Cloudflare DNS
        "93.184.216.34",  # example.com
        "151.101.1.140",  # Reddit
    ])
    def test__is_private_ip__allows_public_ip(self, ip: str) -> None:
        """Public IP addresses are allowed."""
        assert is_private_ip(ip) is False


class TestURLValidation:
    """Test the validate_url_not_private function."""

    @pytest.mark.parametrize("url", [
        "http://localhost/",
        "http://localhost:8080/path",
        "http://localhost.localdomain/",
        "https://localhost/",
    ])
    def test__validate_url__blocks_localhost(self, url: str) -> None:
        """Localhost URLs are blocked."""
        with pytest.raises(SSRFBlockedError) as exc_info:
            validate_url_not_private(url)
        assert "localhost" in str(exc_info.value).lower()

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/",
        "http://127.0.0.1:8080/admin",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/router",
        "http://172.16.0.1/private",
    ])
    def test__validate_url__blocks_private_ips(self, url: str) -> None:
        """Private IP URLs are blocked."""
        with pytest.raises(SSRFBlockedError) as exc_info:
            validate_url_not_private(url)
        assert "private" in str(exc_info.value).lower() or "internal" in str(exc_info.value).lower()

    def test__validate_url__allows_public_urls(self) -> None:
        """Public URLs are allowed."""
        # Should not raise
        validate_url_not_private("https://example.com/")
        validate_url_not_private("https://www.google.com/")
        validate_url_not_private("https://api.github.com/")


class TestFetchURLSSRFProtection:
    """Test SSRF protection in the fetch_url function."""

    @pytest.mark.asyncio
    async def test__fetch_url__blocks_localhost(self) -> None:
        """fetch_url blocks localhost URLs."""
        result = await fetch_url("http://localhost:8000/")

        assert result.content is None
        assert result.error is not None
        assert "localhost" in result.error.lower()

    @pytest.mark.asyncio
    async def test__fetch_url__blocks_private_ip(self) -> None:
        """fetch_url blocks private IP URLs."""
        result = await fetch_url("http://192.168.1.1/")

        assert result.content is None
        assert result.error is not None
        assert "private" in result.error.lower() or "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test__fetch_url__blocks_loopback(self) -> None:
        """fetch_url blocks loopback IP URLs."""
        result = await fetch_url("http://127.0.0.1/")

        assert result.content is None
        assert result.error is not None

    @pytest.mark.asyncio
    async def test__fetch_url__blocks_metadata_endpoint(self) -> None:
        """fetch_url blocks cloud metadata endpoints."""
        # AWS metadata endpoint
        result = await fetch_url("http://169.254.169.254/latest/meta-data/")

        assert result.content is None
        assert result.error is not None
