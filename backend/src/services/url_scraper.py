"""URL scraping service for fetching and extracting metadata from web pages."""
from dataclasses import dataclass

import httpx
import trafilatura
from bs4 import BeautifulSoup

USER_AGENT = 'Mozilla/5.0 (compatible; Bookmarks/1.0)'
DEFAULT_TIMEOUT = 10.0


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


async def fetch_url(url: str, timeout: float = DEFAULT_TIMEOUT) -> FetchResult:  # noqa: ASYNC109
    """
    Fetch raw HTML from a URL.

    Best-effort fetch that returns error info on failure rather than raising.
    Follows redirects and captures the final URL.

    Args:
        url:
            The URL to fetch.
        timeout:
            Request timeout in seconds.

    Returns:
        FetchResult containing HTML content or error information.
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={'User-Agent': USER_AGENT},
            http2=True,
        ) as client:
            response = await client.get(url)

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
