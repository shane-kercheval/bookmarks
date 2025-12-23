"""
Tests for URL scraper service.

Tests cover:
- fetch_url: HTTP fetching with mocked responses (success, timeout, errors, non-HTML)
- extract_html_metadata: Pure function tests for title/description extraction with various HTML
    structures
- extract_html_content: Content extraction using trafilatura
- extract_pdf_metadata: PDF metadata extraction
- extract_pdf_content: PDF text extraction
"""
import json
import unittest.mock
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from services.url_scraper import (
    DEFAULT_TIMEOUT,
    USER_AGENT,
    ExtractedMetadata,
    FetchResult,
    SSRFBlockedError,
    extract_html_content,
    extract_html_metadata,
    extract_pdf_content,
    extract_pdf_metadata,
    fetch_url,
    is_private_ip,
    scrape_url,
    validate_url_not_private,
)


class TestFetchUrl:
    """Tests for fetch_url function."""

    @pytest.mark.asyncio
    async def test__fetch_url__success(self) -> None:
        """Successful fetch returns HTML content and metadata."""
        html = '<html><head><title>Test</title></head><body>Content</body></html>'
        mock_response = AsyncMock()
        mock_response.text = html
        mock_response.url = 'https://example.com/page'
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {'content-type': 'text/html; charset=utf-8'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com')

            assert result.content == html
            assert result.final_url == 'https://example.com/page'
            assert result.status_code == 200
            assert result.content_type == 'text/html; charset=utf-8'
            assert result.error is None

            # Verify client was created with correct params
            mock_client_class.assert_called_once_with(
                follow_redirects=True,
                timeout=DEFAULT_TIMEOUT,
                headers={'User-Agent': USER_AGENT},
                http2=True,
            )

    @pytest.mark.asyncio
    async def test__fetch_url__timeout(self) -> None:
        """Timeout returns error info without raising."""
        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com')

            assert result.content is None
            assert result.final_url == 'https://example.com'
            assert result.status_code is None
            assert result.error == "Request timed out"

    @pytest.mark.asyncio
    async def test__fetch_url__connection_error(self) -> None:
        """Connection error returns error info without raising."""
        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com')

            assert result.content is None
            assert result.error is not None
            assert "Request failed" in result.error

    @pytest.mark.asyncio
    async def test__fetch_url__unsupported_content_type(self) -> None:
        """Unsupported content type (not HTML or PDF) returns error."""
        mock_response = AsyncMock()
        mock_response.url = 'https://example.com/image.png'
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.content = b'fake image bytes'
        mock_response.headers = {'content-type': 'image/png'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com/image.png')

            assert result.content is None
            assert result.status_code == 200
            assert result.content_type == 'image/png'
            assert "Unsupported content type" in result.error

    @pytest.mark.asyncio
    async def test__fetch_url__pdf_content_type(self) -> None:
        """PDF content type returns bytes content."""
        pdf_bytes = b'%PDF-1.4 fake pdf content'
        mock_response = AsyncMock()
        mock_response.url = 'https://example.com/paper.pdf'
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.content = pdf_bytes
        mock_response.headers = {'content-type': 'application/pdf'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com/paper.pdf')

            assert result.content == pdf_bytes
            assert result.status_code == 200
            assert result.content_type == 'application/pdf'
            assert result.is_pdf is True
            assert result.is_html is False
            assert result.error is None

    @pytest.mark.asyncio
    async def test__fetch_url__custom_timeout(self) -> None:
        """Custom timeout is passed to client."""
        mock_response = AsyncMock()
        mock_response.text = '<html></html>'
        mock_response.url = 'https://example.com'
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {'content-type': 'text/html'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            await fetch_url('https://example.com', timeout=30.0)

            mock_client_class.assert_called_once_with(
                follow_redirects=True,
                timeout=30.0,
                headers={'User-Agent': USER_AGENT},
                http2=True,
            )

    @pytest.mark.asyncio
    async def test__fetch_url__redirect_captured(self) -> None:
        """Final URL after redirects is captured."""
        mock_response = AsyncMock()
        mock_response.text = '<html></html>'
        mock_response.url = 'https://www.example.com/final-page'  # Redirected URL
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {'content-type': 'text/html'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com/old-page')

            assert result.final_url == 'https://www.example.com/final-page'

    @pytest.mark.asyncio
    async def test__fetch_url__404_not_found(self) -> None:
        """404 response returns error instead of error page HTML."""
        mock_response = AsyncMock()
        mock_response.text = '<html><title>404 Not Found</title></html>'
        mock_response.url = 'https://example.com/missing'
        mock_response.status_code = 404
        mock_response.is_success = False
        mock_response.headers = {'content-type': 'text/html'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com/missing')

            assert result.content is None  # Should NOT return error page HTML
            assert result.status_code == 404
            assert result.error == "HTTP 404"
            assert result.final_url == 'https://example.com/missing'

    @pytest.mark.asyncio
    async def test__fetch_url__403_forbidden(self) -> None:
        """403 response (auth-gated content) returns error."""
        mock_response = AsyncMock()
        mock_response.url = 'https://example.com/private'
        mock_response.status_code = 403
        mock_response.is_success = False
        mock_response.headers = {'content-type': 'text/html'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com/private')

            assert result.content is None
            assert result.status_code == 403
            assert "403" in result.error

    @pytest.mark.asyncio
    async def test__fetch_url__500_server_error(self) -> None:
        """500 response returns error instead of error page."""
        mock_response = AsyncMock()
        mock_response.url = 'https://example.com/broken'
        mock_response.status_code = 500
        mock_response.is_success = False
        mock_response.headers = {'content-type': 'text/html'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com/broken')

            assert result.content is None
            assert result.status_code == 500
            assert "500" in result.error


class TestExtractMetadata:
    """Tests for extract_metadata function - pure function, no mocking needed."""

    def test__extract_metadata__title_tag(self) -> None:
        """Extracts title from <title> tag."""
        html = '<html><head><title>Page Title</title></head></html>'
        result = extract_html_metadata(html)
        assert result.title == 'Page Title'

    def test__extract_metadata__title_with_whitespace(self) -> None:
        """Title is stripped of whitespace."""
        html = '<html><head><title>  Page Title  \n</title></head></html>'
        result = extract_html_metadata(html)
        assert result.title == 'Page Title'

    def test__extract_metadata__og_title_fallback(self) -> None:
        """Falls back to og:title when <title> is missing."""
        html = '''
        <html><head>
            <meta property="og:title" content="OG Title">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.title == 'OG Title'

    def test__extract_metadata__twitter_title_fallback(self) -> None:
        """Falls back to twitter:title when other titles are missing."""
        html = '''
        <html><head>
            <meta name="twitter:title" content="Twitter Title">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.title == 'Twitter Title'

    def test__extract_metadata__title_priority(self) -> None:
        """<title> tag takes priority over meta tags."""
        html = '''
        <html><head>
            <title>Primary Title</title>
            <meta property="og:title" content="OG Title">
            <meta name="twitter:title" content="Twitter Title">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.title == 'Primary Title'

    def test__extract_metadata__meta_description(self) -> None:
        """Extracts description from meta description tag."""
        html = '''
        <html><head>
            <meta name="description" content="Page description here.">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.description == 'Page description here.'

    def test__extract_metadata__og_description_fallback(self) -> None:
        """Falls back to og:description when meta description is missing."""
        html = '''
        <html><head>
            <meta property="og:description" content="OG Description">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.description == 'OG Description'

    def test__extract_metadata__twitter_description_fallback(self) -> None:
        """Falls back to twitter:description when other descriptions are missing."""
        html = '''
        <html><head>
            <meta name="twitter:description" content="Twitter Description">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.description == 'Twitter Description'

    def test__extract_metadata__description_priority(self) -> None:
        """Meta description takes priority over og/twitter."""
        html = '''
        <html><head>
            <meta name="description" content="Primary Description">
            <meta property="og:description" content="OG Description">
            <meta name="twitter:description" content="Twitter Description">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.description == 'Primary Description'

    def test__extract_metadata__missing_title(self) -> None:
        """Returns None for title when not found."""
        html = '<html><head></head></html>'
        result = extract_html_metadata(html)
        assert result.title is None

    def test__extract_metadata__missing_description(self) -> None:
        """Returns None for description when not found."""
        html = '<html><head><title>Title</title></head></html>'
        result = extract_html_metadata(html)
        assert result.description is None

    def test__extract_metadata__empty_html(self) -> None:
        """Handles empty HTML gracefully."""
        result = extract_html_metadata('')
        assert result.title is None
        assert result.description is None

    def test__extract_metadata__malformed_html(self) -> None:
        """Handles malformed HTML gracefully."""
        html = '<html><head><title>Title'  # Missing closing tags
        result = extract_html_metadata(html)
        assert result.title == 'Title'

    def test__extract_metadata__empty_content_attribute(self) -> None:
        """Handles empty content attributes."""
        html = '''
        <html><head>
            <meta name="description" content="">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.description is None

    def test__extract_metadata__full_page(self) -> None:
        """Extracts metadata from a realistic HTML page."""
        html = '''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Article Title - Site Name</title>
            <meta name="description" content="This is a great article about testing.">
            <meta property="og:title" content="Article Title">
            <meta property="og:description" content="OG description for sharing.">
        </head>
        <body>
            <article>
                <h1>Article Title</h1>
                <p>Article content here...</p>
            </article>
        </body>
        </html>
        '''
        result = extract_html_metadata(html)
        assert result.title == 'Article Title - Site Name'
        assert result.description == 'This is a great article about testing.'


class TestExtractContent:
    """Tests for extract_content function using trafilatura."""

    def test__extract_content__article(self) -> None:
        """Extracts readable content from article-style page."""
        html = '''
        <!DOCTYPE html>
        <html>
        <head><title>Test Article</title></head>
        <body>
            <nav>Navigation menu</nav>
            <article>
                <h1>Main Heading</h1>
                <p>This is the first paragraph of the article. It contains important content.</p>
                <p>This is the second paragraph with more information.</p>
            </article>
            <footer>Footer content</footer>
        </body>
        </html>
        '''
        result = extract_html_content(html)
        # trafilatura should extract the main content
        assert result is not None
        assert 'paragraph' in result.lower() or 'important content' in result.lower()

    def test__extract_content__minimal_html(self) -> None:
        """Returns None for minimal HTML without substantial content."""
        html = '<html><head><title>Title</title></head><body></body></html>'
        result = extract_html_content(html)
        # trafilatura may return None for pages without substantial content
        assert result is None or result == ''

    def test__extract_content__empty_html(self) -> None:
        """Handles empty HTML gracefully."""
        result = extract_html_content('')
        assert result is None


class TestEncodingHandling:
    """Tests for handling different character encodings."""

    def test__extract_metadata__utf8_characters(self) -> None:
        """Handles UTF-8 encoded characters in metadata."""
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Café résumé naïve</title>
            <meta name="description" content="日本語テスト Chinese: 中文 Emoji: 🎉">
        </head>
        </html>
        '''
        result = extract_html_metadata(html)
        assert result.title == 'Café résumé naïve'
        assert '日本語' in result.description
        assert '中文' in result.description

    def test__extract_metadata__html_entities(self) -> None:
        """Handles HTML entities in metadata."""
        html = '''
        <html><head>
            <title>Tom &amp; Jerry&#39;s &quot;Adventure&quot;</title>
            <meta name="description" content="Less &lt; Greater &gt; Ampersand &amp;">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.title == "Tom & Jerry's \"Adventure\""
        assert '<' in result.description
        assert '>' in result.description

    def test__extract_metadata__iso_8859_1_declaration(self) -> None:
        """Handles ISO-8859-1 charset declaration."""
        # Note: The actual bytes would be different, but BeautifulSoup handles
        # the charset declaration and converts appropriately
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="ISO-8859-1">
            <title>Piña Colada</title>
            <meta name="description" content="Crème brûlée">
        </head>
        </html>
        '''
        result = extract_html_metadata(html)
        assert result.title is not None
        assert result.description is not None

    def test__extract_content__utf8_article(self) -> None:
        """Extracts content with UTF-8 characters correctly."""
        html = '''
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"><title>Test</title></head>
        <body>
            <article>
                <h1>Интернационализация</h1>
                <p>This article discusses café culture in São Paulo, including the famous
                pão de queijo and açaí bowls that tourists love to try.</p>
                <p>Japanese text: 日本語のテキスト is also supported.</p>
            </article>
        </body>
        </html>
        '''
        result = extract_html_content(html)
        assert result is not None
        # Content should preserve unicode characters
        assert 'café' in result or 'culture' in result

    def test__extract_metadata__special_quotes(self) -> None:
        """Handles smart quotes and special punctuation."""
        html = '''
        <html><head>
            <title>"Smart Quotes" and 'Apostrophes' — Em Dash</title>
            <meta name="description" content="It's a "test" with … ellipsis">
        </head></html>
        '''
        result = extract_html_metadata(html)
        assert result.title is not None
        assert 'Smart Quotes' in result.title
        assert result.description is not None


class TestDataclasses:
    """Tests for dataclass structure (basic sanity checks)."""

    def test__fetch_result__fields(self) -> None:
        """FetchResult has expected fields."""
        result = FetchResult(
            content='<html></html>',
            final_url='https://example.com',
            status_code=200,
            content_type='text/html',
            error=None,
        )
        assert result.content == '<html></html>'
        assert result.final_url == 'https://example.com'
        assert result.status_code == 200
        assert result.content_type == 'text/html'
        assert result.error is None

    def test__extracted_metadata__fields(self) -> None:
        """ExtractedMetadata has expected fields."""
        metadata = ExtractedMetadata(title='Title', description='Description')
        assert metadata.title == 'Title'
        assert metadata.description == 'Description'


class TestSSRFProtection:
    """Tests for SSRF protection functions."""

    # --- is_private_ip tests ---

    def test__is_private_ip__localhost_ipv4(self) -> None:
        """127.0.0.1 is private."""
        assert is_private_ip('127.0.0.1') is True

    def test__is_private_ip__localhost_ipv6(self) -> None:
        """::1 is private."""
        assert is_private_ip('::1') is True

    def test__is_private_ip__10_network(self) -> None:
        """10.x.x.x addresses are private."""
        assert is_private_ip('10.0.0.1') is True
        assert is_private_ip('10.255.255.255') is True

    def test__is_private_ip__172_16_network(self) -> None:
        """172.16.x.x - 172.31.x.x addresses are private."""
        assert is_private_ip('172.16.0.1') is True
        assert is_private_ip('172.31.255.255') is True

    def test__is_private_ip__192_168_network(self) -> None:
        """192.168.x.x addresses are private."""
        assert is_private_ip('192.168.0.1') is True
        assert is_private_ip('192.168.255.255') is True

    def test__is_private_ip__link_local(self) -> None:
        """169.254.x.x (link-local) addresses are private."""
        assert is_private_ip('169.254.0.1') is True

    def test__is_private_ip__public_addresses(self) -> None:
        """Public IP addresses are not private."""
        assert is_private_ip('8.8.8.8') is False
        assert is_private_ip('1.1.1.1') is False
        assert is_private_ip('93.184.216.34') is False  # example.com

    def test__is_private_ip__invalid_ip(self) -> None:
        """Invalid IP strings are treated as private (blocked)."""
        assert is_private_ip('not-an-ip') is True
        assert is_private_ip('') is True

    # --- validate_url_not_private tests ---

    def test__validate_url_not_private__public_url(self) -> None:
        """Public URLs pass validation."""
        # This should not raise
        validate_url_not_private('https://example.com')

    def test__validate_url_not_private__localhost(self) -> None:
        """Localhost URLs are blocked."""
        with pytest.raises(SSRFBlockedError, match="localhost"):
            validate_url_not_private('http://localhost:8080/api')

    def test__validate_url_not_private__localhost_localdomain(self) -> None:
        """localhost.localdomain is blocked."""
        with pytest.raises(SSRFBlockedError, match="localhost"):
            validate_url_not_private('http://localhost.localdomain/api')

    def test__validate_url_not_private__private_ip_direct(self) -> None:
        """Direct private IP addresses are blocked."""
        with pytest.raises(SSRFBlockedError, match="private"):
            validate_url_not_private('http://192.168.1.1/')

    def test__validate_url_not_private__loopback_ip(self) -> None:
        """127.0.0.1 is blocked."""
        with pytest.raises(SSRFBlockedError, match="private"):
            validate_url_not_private('http://127.0.0.1:3000/')

    def test__validate_url_not_private__no_hostname(self) -> None:
        """URLs without hostname raise ValueError."""
        with pytest.raises(ValueError, match="no hostname"):
            validate_url_not_private('file:///etc/passwd')

    def test__validate_url_not_private__unresolvable_hostname(self) -> None:
        """Unresolvable hostnames raise ValueError."""
        with pytest.raises(ValueError, match="Could not resolve"):
            validate_url_not_private('http://this-domain-definitely-does-not-exist-12345.com/')

    # --- fetch_url SSRF protection integration tests ---

    @pytest.mark.asyncio
    async def test__fetch_url__blocks_localhost(self) -> None:
        """fetch_url blocks localhost URLs."""
        result = await fetch_url('http://localhost:8080/api')
        assert result.content is None
        assert result.error is not None
        assert 'localhost' in result.error.lower()

    @pytest.mark.asyncio
    async def test__fetch_url__blocks_private_ip(self) -> None:
        """fetch_url blocks private IP addresses."""
        result = await fetch_url('http://192.168.1.1/')
        assert result.content is None
        assert result.error is not None
        assert 'private' in result.error.lower() or 'blocked' in result.error.lower()

    @pytest.mark.asyncio
    async def test__fetch_url__blocks_loopback(self) -> None:
        """fetch_url blocks 127.0.0.1."""
        result = await fetch_url('http://127.0.0.1:3000/')
        assert result.content is None
        assert result.error is not None

    @pytest.mark.asyncio
    async def test__fetch_url__blocks_redirect_to_private(self) -> None:
        """fetch_url blocks redirects to private addresses."""
        mock_response = AsyncMock()
        mock_response.url = 'http://192.168.1.1/internal'  # Redirected to private IP
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {'content-type': 'text/html'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            # Mock validate_url_not_private to pass for initial URL only
            with patch('services.url_scraper.validate_url_not_private') as mock_validate:
                # First call (initial URL) passes, second call (redirect) fails
                mock_validate.side_effect = [
                    None,  # Initial URL passes
                    SSRFBlockedError("Blocked request to private address"),
                ]

                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client_class.return_value = mock_client

                result = await fetch_url('https://attacker.com/redirect')

                assert result.content is None
                assert result.error is not None
                assert 'blocked' in result.error.lower() or 'redirect' in result.error.lower()

    @pytest.mark.asyncio
    async def test__fetch_url__allows_public_urls(self) -> None:
        """fetch_url allows public URLs (with mocked response)."""
        mock_response = AsyncMock()
        mock_response.text = '<html><title>Test</title></html>'
        mock_response.url = 'https://example.com'
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {'content-type': 'text/html'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await fetch_url('https://example.com')

            assert result.content is not None
            assert result.error is None


# =============================================================================
# PDF Extraction Tests
# =============================================================================

# Paths for PDF test artifacts
ARTIFACTS_DIR = Path(__file__).parent.parent / 'artifacts'
PDFS_DIR = ARTIFACTS_DIR / 'pdfs'
PDFS_EXTRACTED_DIR = ARTIFACTS_DIR / 'pdfs_extracted'


class TestExtractPdfMetadata:
    """Tests for extract_pdf_metadata function."""

    def test__extract_pdf_metadata__returns_expected_metadata(self) -> None:
        """Compare extracted metadata against stored artifact."""
        pdf_bytes = (PDFS_DIR / 'arxiv_paper.pdf').read_bytes()
        expected = json.loads(
            (PDFS_EXTRACTED_DIR / 'arxiv_paper_metadata.json').read_text(),
        )

        result = extract_pdf_metadata(pdf_bytes)

        assert result.title == expected['title']
        assert result.description == expected['description']

    def test__extract_pdf_metadata__handles_malformed_pdf(self) -> None:
        """Malformed PDF returns None values, doesn't raise."""
        result = extract_pdf_metadata(b'not a pdf')

        assert result.title is None
        assert result.description is None

    def test__extract_pdf_metadata__handles_empty_bytes(self) -> None:
        """Empty bytes returns None values, doesn't raise."""
        result = extract_pdf_metadata(b'')

        assert result.title is None
        assert result.description is None


class TestExtractPdfContent:
    """Tests for extract_pdf_content function."""

    def test__extract_pdf_content__returns_expected_content(self) -> None:
        """Compare extracted content against stored artifact."""
        pdf_bytes = (PDFS_DIR / 'arxiv_paper.pdf').read_bytes()
        expected = (PDFS_EXTRACTED_DIR / 'arxiv_paper_content.txt').read_text()

        result = extract_pdf_content(pdf_bytes)

        assert result == expected.rstrip('\n')

    def test__extract_pdf_content__handles_malformed_pdf(self) -> None:
        """Malformed PDF returns None, doesn't raise."""
        result = extract_pdf_content(b'not a pdf')

        assert result is None

    def test__extract_pdf_content__handles_empty_bytes(self) -> None:
        """Empty bytes returns None, doesn't raise."""
        result = extract_pdf_content(b'')

        assert result is None

    def test__extract_pdf_content__strips_null_bytes(self) -> None:
        """
        Null bytes are stripped from extracted content.

        PostgreSQL cannot store null bytes (0x00) in text columns as it uses
        null-terminated strings internally. PDFs may contain null bytes in
        extracted text, so they must be removed.
        """
        # Mock PdfReader to return text containing null bytes
        with patch('services.url_scraper.PdfReader') as mock_reader_class:
            mock_page = unittest.mock.MagicMock()
            mock_page.extract_text.return_value = 'Hello\x00World\x00Test'

            mock_reader = unittest.mock.MagicMock()
            mock_reader.pages = [mock_page]
            mock_reader_class.return_value = mock_reader

            result = extract_pdf_content(b'fake pdf bytes')

            assert result == 'HelloWorldTest'
            assert '\x00' not in result

    def test__extract_pdf_content__preserves_other_control_characters(self) -> None:
        """
        Other control characters (like 0x01) are preserved.

        Only null bytes (0x00) are invalid for PostgreSQL. Other control
        characters are valid UTF-8 and should be preserved.
        """
        with patch('services.url_scraper.PdfReader') as mock_reader_class:
            mock_page = unittest.mock.MagicMock()
            # Include various control characters that should be preserved
            mock_page.extract_text.return_value = 'Hello\x01World\x02Test\x1F'

            mock_reader = unittest.mock.MagicMock()
            mock_reader.pages = [mock_page]
            mock_reader_class.return_value = mock_reader

            result = extract_pdf_content(b'fake pdf bytes')

            # Control characters should be preserved (they're valid UTF-8)
            assert result == 'Hello\x01World\x02Test\x1F'
            assert '\x01' in result
            assert '\x02' in result
            assert '\x1F' in result


# =============================================================================
# scrape_url Tests
# =============================================================================


class TestScrapeUrl:
    """Tests for scrape_url high-level function."""

    @pytest.mark.asyncio
    async def test__scrape_url__extracts_html_content_and_metadata(self) -> None:
        """scrape_url extracts content and metadata from HTML pages."""
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Page</title>
            <meta name="description" content="Test description">
        </head>
        <body><article><p>Test content paragraph.</p></article></body>
        </html>
        '''
        mock_response = AsyncMock()
        mock_response.text = html
        mock_response.url = 'https://example.com/'
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {'content-type': 'text/html; charset=utf-8'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await scrape_url('https://example.com')

            assert result.error is None
            assert result.metadata is not None
            assert result.metadata.title == 'Test Page'
            assert result.metadata.description == 'Test description'
            assert result.final_url == 'https://example.com/'
            assert result.content_type == 'text/html; charset=utf-8'

    @pytest.mark.asyncio
    async def test__scrape_url__extracts_pdf_content_and_metadata(self) -> None:
        """scrape_url extracts content and metadata from PDF files."""
        pdf_bytes = (PDFS_DIR / 'arxiv_paper.pdf').read_bytes()
        expected_metadata = json.loads(
            (PDFS_EXTRACTED_DIR / 'arxiv_paper_metadata.json').read_text(),
        )

        mock_response = AsyncMock()
        mock_response.content = pdf_bytes
        mock_response.url = 'https://arxiv.org/pdf/test.pdf'
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {'content-type': 'application/pdf'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await scrape_url('https://arxiv.org/pdf/test.pdf')

            assert result.error is None
            assert result.text is not None
            assert result.metadata is not None
            assert result.metadata.title == expected_metadata['title']
            assert result.final_url == 'https://arxiv.org/pdf/test.pdf'
            assert result.content_type == 'application/pdf'

    @pytest.mark.asyncio
    async def test__scrape_url__propagates_fetch_errors(self) -> None:
        """scrape_url propagates errors from fetch_url."""
        mock_response = AsyncMock()
        mock_response.url = 'https://example.com'
        mock_response.status_code = 404
        mock_response.is_success = False
        mock_response.headers = {'content-type': 'text/html'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await scrape_url('https://example.com')

            assert result.error == 'HTTP 404'
            assert result.text is None
            assert result.metadata is None

    @pytest.mark.asyncio
    async def test__scrape_url__handles_unsupported_content_type(self) -> None:
        """scrape_url returns error for unsupported content types."""
        mock_response = AsyncMock()
        mock_response.url = 'https://example.com/image.png'
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.content = b'fake image'
        mock_response.headers = {'content-type': 'image/png'}

        with patch('services.url_scraper.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await scrape_url('https://example.com/image.png')

            assert 'Unsupported content type' in result.error
            assert result.text is None
            assert result.metadata is None
