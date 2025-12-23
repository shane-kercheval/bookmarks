# PDF Scraping Support Implementation Plan

**Created**: 2025-12-21
**Status**: Draft
**Goal**: Enable the URL scraper to extract text content and metadata from PDF files (e.g., arxiv papers)

## Overview

Currently, `url_scraper.py` only supports HTML content, rejecting PDFs with "Non-HTML content type" error. This plan adds PDF support using `pypdf` for text and metadata extraction.

## Design Decisions

- **Library**: `pypdf` - lightweight, pure Python, BSD license, good text extraction for academic PDFs
- **Content format**: Plain text blob (used for search, not rendering)
- **No image extraction**: Text only
- **No size limit in scraper**: Content length limits are defined in `schemas/bookmark.py` (`MAX_CONTENT_LENGTH`). The scraper returns complete extracted text; truncation (if any) is the caller's responsibility. This matches existing HTML behavior.
- **Metadata is best-effort**: PDF metadata (title, subject) is often missing or junk - expect None frequently
- **No backward compatibility**: Optimize for clean design. Rename `FetchResult.html` → `.content` directly without deprecated aliases.
- **No complex fallbacks**: If PDF metadata is missing, return None. No fallback to filename or first heading extraction.

## Clarifications (Agent Q&A)

**Q: Content length validation gap - scraped content bypasses schema validation?**
A: Correct. This is existing behavior for HTML too. The scraper returns complete text; the service layer decides what to store. Addressing this is out of scope for PDF support - it's a separate concern that applies to both HTML and PDF equally.

**Q: Should we rename `extracted/` → `html_extracted/`?**
A: Yes. The rename ensures consistent naming: `html/` + `html_extracted/`, `pdfs/` + `pdfs_extracted/`. Without it, we'd have `html/`, `extracted/`, `pdfs/`, `pdfs_extracted/` which is inconsistent.

**Q: Backward compatibility for `FetchResult.html`?**
A: No deprecated aliases. Rename directly to `.content`. Update all callers. Clean design over legacy support.

**Q: Final URL tracking - store original or final after redirects?**
A: Store `final_url` after redirects. This matches existing HTML behavior and is the correct approach (the final URL is where the content actually lives).

**Q: PDF metadata fallbacks (extract title from first heading, filename, etc.)?**
A: No. Keep it simple. Metadata is best-effort - return None if missing. The service layer or user can provide title/description. Complex heuristics add maintenance burden for marginal benefit.

**Q: PDF without extractable text (scanned images)?**
A: Return None for content. No special warnings in ScrapedPage. This is acceptable - the scraper is best-effort. Callers handle None content appropriately.

**Q: Test PDF size concerns?**
A: Use real PDFs (e.g., arxiv paper). Download once, commit to `backend/tests/artifacts/pdfs/`. A few MB is negligible for repo size. Real PDFs catch real-world edge cases that programmatic PDFs would miss.

## Architecture

### New High-Level API

Add a `scrape_url()` function that provides a clean interface for callers. This separates fetching from extraction and routes to the correct extractor based on content type.

```python
@dataclass
class ScrapedPage:
    """Result of scraping a URL for content and metadata."""
    text: str | None
    metadata: ExtractedMetadata | None
    final_url: str
    content_type: str | None
    error: str | None

async def scrape_url(url: str, timeout: float = DEFAULT_TIMEOUT) -> ScrapedPage:
    """
    Fetch a URL and extract text content and metadata.

    Routes to appropriate extractor based on content type (HTML or PDF).
    This is the main entry point for callers.
    """
    result = await fetch_url(url, timeout)
    if result.error:
        return ScrapedPage(
            text=None,
            metadata=None,
            final_url=result.final_url,
            content_type=result.content_type,
            error=result.error,
        )

    if result.is_pdf:
        metadata = extract_pdf_metadata(result.content)
        text = extract_pdf_content(result.content)
    else:  # HTML
        metadata = extract_html_metadata(result.content)
        text = extract_html_content(result.content)

    return ScrapedPage(
        text=text,
        metadata=metadata,
        final_url=result.final_url,
        content_type=result.content_type,
        error=None,
    )
```

### Function Renames

For clarity, rename existing HTML functions:
- `extract_metadata` → `extract_html_metadata`
- `extract_content` → `extract_html_content`

### Updated FetchResult

```python
@dataclass
class FetchResult:
    """Result of fetching a URL (raw content before extraction)."""
    content: str | bytes | None  # str for HTML, bytes for PDF
    final_url: str
    status_code: int | None
    content_type: str | None
    error: str | None

    @property
    def is_pdf(self) -> bool:
        return bool(self.content_type and 'application/pdf' in self.content_type.lower())

    @property
    def is_html(self) -> bool:
        return bool(self.content_type and 'text/html' in self.content_type.lower())
```

### Layer Summary

```
Callers (bookmark_service)
    │
    ▼
scrape_url()  ◄── High-level API, returns ScrapedPage with text + metadata
    │
    ├── fetch_url()  ◄── HTTP fetch, returns raw content
    │
    ├── extract_html_metadata() / extract_html_content()  ◄── HTML extraction
    │
    └── extract_pdf_metadata() / extract_pdf_content()    ◄── PDF extraction
```

---

## Milestone 0: Rename Existing Functions and Artifacts

### Goal
Rename existing functions and test artifacts for consistency before adding PDF support.

### Success Criteria
- `extract_metadata` renamed to `extract_html_metadata`
- `extract_content` renamed to `extract_html_content`
- `backend/tests/artifacts/extracted/` renamed to `backend/tests/artifacts/html_extracted/`
- All tests pass after renames

### Key Changes

**1. Rename functions in `url_scraper.py`:**
- `extract_metadata` → `extract_html_metadata`
- `extract_content` → `extract_html_content`

**2. Update all callers** (likely `bookmark_service.py` and tests)

**3. Rename artifacts directory:**
```bash
git mv backend/tests/artifacts/extracted backend/tests/artifacts/html_extracted
```

**4. Update test imports and file paths**

### Testing Strategy
- Run `make tests` to ensure all tests pass after renames

### Dependencies
None

### Risk Factors
- May miss some callers; grep thoroughly

---

## Milestone 1: Add pypdf and PDF Extraction Functions

### Goal
Add `pypdf` library and implement pure functions for extracting metadata and text content from PDF bytes.

### Success Criteria
- `pypdf` added to project dependencies
- `extract_pdf_metadata(pdf_bytes)` returns title/description from PDF metadata
- `extract_pdf_content(pdf_bytes)` returns concatenated text from all pages
- Both functions handle malformed/empty PDFs gracefully (return None, don't raise)
- Unit tests pass with real PDF fixtures

### Key Changes

**1. Add dependency:**
```bash
uv add pypdf
```

**2. New functions in `url_scraper.py`:**

```python
def extract_pdf_metadata(pdf_bytes: bytes) -> ExtractedMetadata:
    """
    Extract title/description from PDF document metadata.

    Uses PDF metadata fields:
    - title: from /Title metadata
    - description: from /Subject metadata

    Note: PDF metadata is often missing or auto-generated junk.
    Expect None values frequently.
    """
    try:
        from pypdf import PdfReader
        from io import BytesIO

        reader = PdfReader(BytesIO(pdf_bytes))
        meta = reader.metadata

        title = meta.title if meta and meta.title else None
        description = meta.subject if meta and meta.subject else None

        return ExtractedMetadata(title=title, description=description)
    except Exception:
        return ExtractedMetadata(title=None, description=None)


def extract_pdf_content(pdf_bytes: bytes) -> str | None:
    """
    Extract text content from all PDF pages.

    Returns concatenated text from all pages, or None if extraction fails
    or PDF contains no extractable text (e.g., scanned images).
    """
    try:
        from pypdf import PdfReader
        from io import BytesIO

        reader = PdfReader(BytesIO(pdf_bytes))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        return "\n".join(text_parts) if text_parts else None
    except Exception:
        return None
```

**Note on imports**: The plan shows imports inside functions for clarity. During implementation, move imports to module level per project conventions.

### Testing Strategy

**Test artifacts approach (matching existing HTML pattern):**

1. Download 1-2 real PDFs with known content:
   - An arxiv paper (has academic content, may have metadata)
   - A simple document (for variety)

2. Store in `backend/tests/artifacts/pdfs/`:
   - `arxiv_paper.pdf`
   - `simple_document.pdf`

3. Extract and store expected results in `backend/tests/artifacts/pdfs_extracted/`:
   - `arxiv_paper_content.txt`
   - `arxiv_paper_metadata.json`
   - `simple_document_content.txt`
   - `simple_document_metadata.json`

4. Tests compare extraction output against stored artifacts, allowing diff tracking over time.

**Test cases:**
```python
def test__extract_pdf_metadata__returns_expected_metadata():
    """Compare extracted metadata against stored artifact."""
    pdf_bytes = (ARTIFACTS_DIR / "pdfs" / "arxiv_paper.pdf").read_bytes()
    expected = json.loads((ARTIFACTS_DIR / "pdfs_extracted" / "arxiv_paper_metadata.json").read_text())

    result = extract_pdf_metadata(pdf_bytes)

    assert result.title == expected["title"]
    assert result.description == expected["description"]

def test__extract_pdf_content__returns_expected_content():
    """Compare extracted content against stored artifact."""
    pdf_bytes = (ARTIFACTS_DIR / "pdfs" / "arxiv_paper.pdf").read_bytes()
    expected = (ARTIFACTS_DIR / "pdfs_extracted" / "arxiv_paper_content.txt").read_text()

    result = extract_pdf_content(pdf_bytes)

    assert result == expected

def test__extract_pdf_metadata__handles_malformed_pdf():
    """Malformed PDF returns None values, doesn't raise."""
    result = extract_pdf_metadata(b"not a pdf")
    assert result.title is None
    assert result.description is None

def test__extract_pdf_content__handles_malformed_pdf():
    """Malformed PDF returns None, doesn't raise."""
    result = extract_pdf_content(b"not a pdf")
    assert result is None
```

### Dependencies
- Milestone 0 (renames complete)

### Risk Factors
- Some PDFs have no extractable text (scanned images) - acceptable, return None
- Encrypted PDFs - caught by try/except, return None
- PDF metadata often missing - expected behavior

---

## Milestone 2: Modify fetch_url to Support PDF Content Type

### Goal
Update `fetch_url` to accept PDF responses and return binary content for PDFs.

### Success Criteria
- `fetch_url` returns `FetchResult` with bytes content for PDFs
- `fetch_url` returns `FetchResult` with str content for HTML (existing behavior)
- Unsupported content types still rejected with error
- `FetchResult.is_pdf` and `FetchResult.is_html` helpers work correctly
- Tests pass with mocked HTTP responses

### Key Changes

**1. Update `FetchResult` dataclass:**
```python
@dataclass
class FetchResult:
    content: str | bytes | None  # Renamed from 'html', type widened
    final_url: str
    status_code: int | None
    content_type: str | None
    error: str | None

    @property
    def is_pdf(self) -> bool:
        return bool(self.content_type and 'application/pdf' in self.content_type.lower())

    @property
    def is_html(self) -> bool:
        return bool(self.content_type and 'text/html' in self.content_type.lower())
```

**2. Update `fetch_url` content type handling (around line 172):**
```python
content_type = response.headers.get('content-type', '')

if 'application/pdf' in content_type.lower():
    return FetchResult(
        content=response.content,  # bytes for PDF
        final_url=str(response.url),
        status_code=response.status_code,
        content_type=content_type,
        error=None,
    )
elif 'text/html' in content_type.lower():
    return FetchResult(
        content=response.text,  # str for HTML
        final_url=str(response.url),
        status_code=response.status_code,
        content_type=content_type,
        error=None,
    )
else:
    return FetchResult(
        content=None,
        final_url=str(response.url),
        status_code=response.status_code,
        content_type=content_type,
        error=f"Unsupported content type: {content_type}",
    )
```

### Testing Strategy

**Mock httpx responses using test fixtures:**
```python
@pytest.fixture
def pdf_bytes():
    return (ARTIFACTS_DIR / "pdfs" / "arxiv_paper.pdf").read_bytes()

async def test__fetch_url__returns_pdf_bytes(respx_mock, pdf_bytes):
    respx_mock.get("https://example.com/paper.pdf").mock(
        return_value=httpx.Response(
            200,
            content=pdf_bytes,
            headers={"content-type": "application/pdf"},
        )
    )

    result = await fetch_url("https://example.com/paper.pdf")

    assert result.content == pdf_bytes
    assert result.is_pdf is True
    assert result.is_html is False
    assert result.error is None

async def test__fetch_url__returns_html_string(respx_mock):
    # Existing behavior preserved
    ...

async def test__fetch_url__rejects_unsupported_content_type(respx_mock):
    respx_mock.get("https://example.com/image.png").mock(
        return_value=httpx.Response(
            200,
            content=b"fake image",
            headers={"content-type": "image/png"},
        )
    )

    result = await fetch_url("https://example.com/image.png")

    assert result.content is None
    assert result.error == "Unsupported content type: image/png"
```

### Dependencies
- Milestone 1 (PDF extraction functions exist for testing)

### Risk Factors
- Breaking change: `FetchResult.html` renamed to `FetchResult.content`
- Need to update all callers that access `.html`

---

## Milestone 3: Add scrape_url High-Level Function

### Goal
Add `scrape_url()` as the main entry point that handles fetching and extraction routing.

### Success Criteria
- `scrape_url()` returns `ScrapedPage` with text and metadata
- Routes to HTML or PDF extraction based on content type
- Errors propagated correctly
- Integration tests pass

### Key Changes

**1. Add `ScrapedPage` dataclass and `scrape_url` function:**

```python
@dataclass
class ScrapedPage:
    """Result of scraping a URL for content and metadata."""
    text: str | None
    metadata: ExtractedMetadata | None
    final_url: str
    content_type: str | None
    error: str | None


async def scrape_url(url: str, timeout: float = DEFAULT_TIMEOUT) -> ScrapedPage:
    """
    Fetch a URL and extract text content and metadata.

    Routes to appropriate extractor based on content type (HTML or PDF).
    This is the main entry point for bookmark creation.

    Args:
        url: The URL to scrape.
        timeout: Request timeout in seconds.

    Returns:
        ScrapedPage with extracted text, metadata, and any error info.
    """
    result = await fetch_url(url, timeout)

    if result.error:
        return ScrapedPage(
            text=None,
            metadata=None,
            final_url=result.final_url,
            content_type=result.content_type,
            error=result.error,
        )

    if result.is_pdf:
        metadata = extract_pdf_metadata(result.content)
        text = extract_pdf_content(result.content)
    else:
        metadata = extract_html_metadata(result.content)
        text = extract_html_content(result.content)

    return ScrapedPage(
        text=text,
        metadata=metadata,
        final_url=result.final_url,
        content_type=result.content_type,
        error=None,
    )
```

### Testing Strategy

```python
async def test__scrape_url__extracts_pdf_content_and_metadata(respx_mock, pdf_bytes):
    respx_mock.get("https://arxiv.org/pdf/test.pdf").mock(
        return_value=httpx.Response(
            200,
            content=pdf_bytes,
            headers={"content-type": "application/pdf"},
        )
    )

    result = await scrape_url("https://arxiv.org/pdf/test.pdf")

    assert result.error is None
    assert result.text is not None
    assert result.metadata is not None
    assert "expected content" in result.text  # Based on fixture

async def test__scrape_url__extracts_html_content_and_metadata(respx_mock):
    html = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text=html, headers={"content-type": "text/html"})
    )

    result = await scrape_url("https://example.com")

    assert result.error is None
    assert result.metadata.title == "Test"

async def test__scrape_url__propagates_fetch_errors(respx_mock):
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(404, headers={"content-type": "text/html"})
    )

    result = await scrape_url("https://example.com")

    assert result.error == "HTTP 404"
    assert result.text is None
```

### Dependencies
- Milestone 2 (fetch_url returns PDF bytes)

### Risk Factors
- None significant

---

## Milestone 4: Update Bookmark Service to Use scrape_url

### Goal
Update the bookmark creation flow to use `scrape_url()` instead of calling fetch/extract separately.

### Success Criteria
- Bookmark service uses `scrape_url()` for URL scraping
- PDF bookmarks extract title/description/content correctly
- HTML bookmarks work as before
- End-to-end tests pass

### Key Changes

**1. Update `bookmark_service.py`:**

Find where `fetch_url`, `extract_metadata`, `extract_content` are called and replace with:

```python
from services.url_scraper import scrape_url

# In bookmark creation:
scraped = await scrape_url(url)

if scraped.error:
    # Handle error (log warning, continue with user-provided data)
    ...

# Use scraped.metadata.title, scraped.metadata.description if not provided by user
# Use scraped.text for content storage
```

### Testing Strategy

- Existing bookmark service tests should continue to pass
- Add test for creating bookmark with PDF URL (mocked)

```python
async def test__create_bookmark__with_pdf_url(db_session, respx_mock, pdf_bytes):
    respx_mock.get("https://arxiv.org/pdf/test.pdf").mock(
        return_value=httpx.Response(
            200,
            content=pdf_bytes,
            headers={"content-type": "application/pdf"},
        )
    )

    bookmark = await create_bookmark(
        db_session,
        user_id="user123",
        url="https://arxiv.org/pdf/test.pdf",
    )

    assert bookmark.content is not None  # Extracted PDF text
    # Title may be None if PDF has no metadata - that's expected
```

### Dependencies
- Milestone 3 (scrape_url exists)

### Risk Factors
- Need to find exact integration point in bookmark_service.py
- May need to handle case where PDF has no metadata (fallback to URL/filename for title?)

---

## Milestone 5: Documentation and Verification

### Goal
Verify everything works end-to-end and update documentation if needed.

### Success Criteria
- `make tests` passes
- Manual test with real arxiv PDF URL works
- Code review complete

### Key Changes
- Review and update docstrings if needed
- Manual smoke test with `https://arxiv.org/pdf/2509.01092`

### Testing Strategy
- Run full test suite
- Manual verification:
  1. Start the app locally
  2. Create a bookmark with an arxiv PDF URL
  3. Verify title/content extracted (or gracefully absent)
  4. Verify bookmark is searchable by PDF content

### Dependencies
- Milestones 0-4

### Risk Factors
- arxiv may have rate limiting or bot detection (User-Agent may help)
- Real PDFs may have unexpected edge cases

---

## Test Artifacts Setup

Before starting Milestone 1, set up the PDF test artifacts:

**1. Download test PDFs:**
```bash
# arxiv paper (small, has content)
curl -o backend/tests/artifacts/pdfs/arxiv_paper.pdf "https://arxiv.org/pdf/2509.01092"

# Or find another small public domain PDF
```

**2. Generate expected extraction results:**
```python
# One-time script to generate artifacts
from pypdf import PdfReader
from io import BytesIO
import json

pdf_path = "backend/tests/artifacts/pdfs/arxiv_paper.pdf"
pdf_bytes = open(pdf_path, "rb").read()

reader = PdfReader(BytesIO(pdf_bytes))

# Extract metadata
meta = reader.metadata
metadata = {
    "title": meta.title if meta else None,
    "description": meta.subject if meta else None,
}
with open("backend/tests/artifacts/pdfs_extracted/arxiv_paper_metadata.json", "w") as f:
    json.dump(metadata, f, indent=2)

# Extract content
text_parts = [page.extract_text() for page in reader.pages]
content = "\n".join(filter(None, text_parts))
with open("backend/tests/artifacts/pdfs_extracted/arxiv_paper_content.txt", "w") as f:
    f.write(content)
```

**3. Commit artifacts to repo** for deterministic, reproducible tests.

---

## Summary

| Milestone | Focus | Key Deliverable |
|-----------|-------|-----------------|
| 0 | Renames | `extract_html_*` functions, `html_extracted/` directory |
| 1 | PDF extraction | `extract_pdf_metadata`, `extract_pdf_content` + tests |
| 2 | fetch_url PDF | `FetchResult.content` (str\|bytes), `is_pdf` helper |
| 3 | scrape_url | High-level API returning `ScrapedPage` |
| 4 | Integration | Bookmark service uses `scrape_url()` |
| 5 | Verification | Full test suite, manual smoke test |
