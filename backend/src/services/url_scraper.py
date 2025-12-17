"""URL scraping service for fetching and extracting metadata from web pages."""
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

USER_AGENT = 'Mozilla/5.0 (compatible; Bookmarks/1.0)'
DEFAULT_TIMEOUT = 10.0


class SSRFBlockedError(Exception):
    """Raised when a URL targets a private/internal network address."""

    pass


def is_private_ip(ip_str: str) -> bool:
    """
    Check if an IP address is private, loopback, or otherwise internal.

    Args:
        ip_str: IP address string (IPv4 or IPv6).

    Returns:
        True if the IP is private/internal, False if public.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        # If we can't parse it, block it to be safe
        return True


def validate_url_not_private(url: str) -> None:
    """
    Validate that a URL does not target a private/internal network.

    Resolves the hostname to check the actual IP address, preventing
    DNS rebinding attacks where a hostname resolves to an internal IP.

    Args:
        url: The URL to validate.

    Raises:
        SSRFBlockedError: If the URL targets a private network.
        ValueError: If the URL is malformed.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname

    if not hostname:
        raise ValueError(f"Invalid URL (no hostname): {url}")

    # Block common localhost variants
    if hostname.lower() in ('localhost', 'localhost.localdomain'):
        raise SSRFBlockedError(f"Blocked request to localhost: {url}")

    # Try to resolve hostname to IP addresses
    try:
        # getaddrinfo returns list of (family, type, proto, canonname, sockaddr)
        # sockaddr is (ip, port) for IPv4 or (ip, port, flow, scope) for IPv6
        addrinfo = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addrinfo:
            ip_str = sockaddr[0]
            if is_private_ip(ip_str):
                raise SSRFBlockedError(
                    f"Blocked request to private/internal address: {url} resolves to {ip_str}",
                )
    except socket.gaierror as e:
        # DNS resolution failed - could be legitimate or could be an attack
        # We'll let it fail naturally when httpx tries to connect
        raise ValueError(f"Could not resolve hostname: {hostname}") from e


@dataclass
class FetchResult:
    """Result of fetching a URL."""

    html: str | None
    final_url: str
    status_code: int | None
    content_type: str | None
    error: str | None


@dataclass
class ExtractedMetadata:
    """Extracted title and description from HTML."""

    title: str | None
    description: str | None


async def fetch_url(url: str, timeout: float = DEFAULT_TIMEOUT) -> FetchResult:  # noqa: ASYNC109, PLR0911
    """
    Fetch raw HTML from a URL.

    Best-effort fetch that returns error info on failure rather than raising.
    Follows redirects and captures the final URL.

    Security: Validates that the URL does not target private/internal networks
    to prevent SSRF attacks.

    Args:
        url:
            The URL to fetch.
        timeout:
            Request timeout in seconds.

    Returns:
        FetchResult containing HTML content or error information.
    """
    # SSRF protection: validate URL doesn't target internal networks
    try:
        validate_url_not_private(url)
    except (SSRFBlockedError, ValueError) as e:
        return FetchResult(
            html=None,
            final_url=url,
            status_code=None,
            content_type=None,
            error=str(e),
        )

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={'User-Agent': USER_AGENT},
            http2=True,
        ) as client:
            response = await client.get(url)

            # SSRF protection: validate final URL after redirects
            final_url_str = str(response.url)
            try:
                validate_url_not_private(final_url_str)
            except (SSRFBlockedError, ValueError) as e:
                return FetchResult(
                    html=None,
                    final_url=final_url_str,
                    status_code=response.status_code,
                    content_type=None,
                    error=f"Redirect blocked: {e}",
                )

            # Check for successful response (2xx status codes)
            if not response.is_success:
                return FetchResult(
                    html=None,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=response.headers.get('content-type', ''),
                    error=f"HTTP {response.status_code}",
                )

            content_type = response.headers.get('content-type', '')

            # Check if response is HTML
            if 'text/html' not in content_type.lower():
                return FetchResult(
                    html=None,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=content_type,
                    error=f"Non-HTML content type: {content_type}",
                )

            return FetchResult(
                html=response.text,
                final_url=str(response.url),
                status_code=response.status_code,
                content_type=content_type,
                error=None,
            )
    except httpx.TimeoutException:
        return FetchResult(
            html=None,
            final_url=url,
            status_code=None,
            content_type=None,
            error="Request timed out",
        )
    except httpx.RequestError as e:
        return FetchResult(
            html=None,
            final_url=url,
            status_code=None,
            content_type=None,
            error=f"Request failed: {e}",
        )


def extract_metadata(html: str) -> ExtractedMetadata:
    """
    Extract title and description from HTML.

    Pure function with no I/O. Uses BeautifulSoup for parsing.

    Title extraction priority:
    1. <title> tag
    2. <meta property="og:title">
    3. <meta name="twitter:title">

    Description extraction priority:
    1. <meta name="description">
    2. <meta property="og:description">
    3. <meta name="twitter:description">

    Args:
        html:
            Raw HTML string to parse.

    Returns:
        ExtractedMetadata with title and description (may be None if not found).
    """
    soup = BeautifulSoup(html, 'lxml')

    # Extract title
    title = None
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        title = title_tag.string.strip()
    if not title:
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
    if not title:
        twitter_title = soup.find('meta', attrs={'name': 'twitter:title'})
        if twitter_title and twitter_title.get('content'):
            title = twitter_title['content'].strip()

    # Extract description
    description = None
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        description = meta_desc['content'].strip()
    if not description:
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            description = og_desc['content'].strip()
    if not description:
        twitter_desc = soup.find('meta', attrs={'name': 'twitter:description'})
        if twitter_desc and twitter_desc.get('content'):
            description = twitter_desc['content'].strip()

    return ExtractedMetadata(title=title, description=description)


def extract_content(html: str) -> str | None:
    """
    Extract main readable content from HTML using trafilatura.

    Pure function with no I/O. Returns plain text extracted from the page,
    stripping navigation, scripts, styles, and other non-content elements.

    Args:
        html:
            Raw HTML string to parse.

    Returns:
        Extracted plain text content, or None if extraction fails.
    """
    return trafilatura.extract(html)
