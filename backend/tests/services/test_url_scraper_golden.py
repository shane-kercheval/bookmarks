"""
Golden file / snapshot tests for extraction regression detection.

These tests extract metadata and content from realistic HTML pages and save the
output to files in tests/artifacts/extracted/. Changes to extraction logic will
appear as git diffs in these output files for review.

The tests perform basic assertions but the primary purpose is generating output
files that can be reviewed for extraction quality and regression detection.

HTML test pages:
- article_blog.html: Blog post with rich metadata (og tags, twitter cards)
- documentation.html: Technical documentation page
- product_page.html: E-commerce product page
"""
import json
from pathlib import Path

import pytest

from services.url_scraper import extract_html_content, extract_html_metadata

# Paths
ARTIFACTS_DIR = Path(__file__).parent.parent / 'artifacts'
HTML_DIR = ARTIFACTS_DIR / 'html'
EXTRACTED_DIR = ARTIFACTS_DIR / 'html_extracted'


@pytest.fixture(scope='module', autouse=True)
def ensure_extracted_dir() -> None:
    """Ensure the extracted output directory exists."""
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)


def _save_metadata(name: str, title: str | None, description: str | None) -> None:
    """Save extracted metadata to JSON file."""
    output = {
        'title': title,
        'description': description,
    }
    output_path = EXTRACTED_DIR / f'{name}_metadata.json'
    output_path.write_text(json.dumps(output, indent=2) + '\n')


def _save_content(name: str, content: str | None) -> None:
    """Save extracted content to text file."""
    output_path = EXTRACTED_DIR / f'{name}_content.txt'
    if content:
        output_path.write_text(content + '\n')
    else:
        output_path.write_text('(no content extracted)\n')


class TestGoldenFileExtraction:
    """Golden file tests that save extraction output for git diff review."""

    def test__extract__article_blog(self) -> None:
        """Extract from article/blog page and save output."""
        html_path = HTML_DIR / 'article_blog.html'
        html = html_path.read_text()

        # Extract
        metadata = extract_html_metadata(html)
        content = extract_html_content(html)

        # Save outputs for git diff review
        _save_metadata('article_blog', metadata.title, metadata.description)
        _save_content('article_blog', content)

        # Basic assertions - extraction should succeed
        assert metadata.title is not None, "Should extract title from article"
        assert metadata.description is not None, "Should extract description from article"
        assert content is not None, "Should extract content from article"

        # Sanity checks on content quality
        assert 'async' in metadata.title.lower() or 'python' in metadata.title.lower()
        assert len(content) > 500, "Article should have substantial content"

    def test__extract__documentation(self) -> None:
        """Extract from documentation page and save output."""
        html_path = HTML_DIR / 'documentation.html'
        html = html_path.read_text()

        # Extract
        metadata = extract_html_metadata(html)
        content = extract_html_content(html)

        # Save outputs for git diff review
        _save_metadata('documentation', metadata.title, metadata.description)
        _save_content('documentation', content)

        # Basic assertions
        assert metadata.title is not None, "Should extract title from docs"
        assert metadata.description is not None, "Should extract description from docs"
        assert content is not None, "Should extract content from docs"

        # Sanity checks
        assert 'fastapi' in metadata.title.lower() or 'installation' in metadata.title.lower()
        assert len(content) > 200, "Documentation should have content"

    def test__extract__product_page(self) -> None:
        """Extract from product page and save output."""
        html_path = HTML_DIR / 'product_page.html'
        html = html_path.read_text()

        # Extract
        metadata = extract_html_metadata(html)
        content = extract_html_content(html)

        # Save outputs for git diff review
        _save_metadata('product_page', metadata.title, metadata.description)
        _save_content('product_page', content)

        # Basic assertions
        assert metadata.title is not None, "Should extract title from product page"
        assert metadata.description is not None, "Should extract description from product page"
        # Product pages may or may not have extractable content depending on structure
        # Content extraction is best-effort

        # Sanity checks
        assert 'sony' in metadata.title.lower() or 'headphone' in metadata.title.lower()
