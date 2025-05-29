import os
import sys
from utils.newspaper_processor import (
    extract_article_text, 
    replace_ru_domains,
    get_base_url,
    is_same_domain,
    convert_relative_urls
)

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Define a test signature
TEST_SIGNATURE = '<div id="firma"><hr><p><a href="https://www.reddit.com/user/urielsalis">Maintainer</a> | <a href="https://www.reddit.com/user/subtepass">Creator</a> | <a href="https://github.com/urielsalis/empleadoEstatalBot">Source Code</a></p></div>'


def test_extract_article_text_from_file():
    """Test extracting article text from a real HTML file and comparing with expected Markdown."""
    # Read the raw HTML file
    raw_html_path = os.path.join(os.path.dirname(__file__), 'data', 'raw_text.html')
    with open(raw_html_path, 'r', encoding='utf-8') as f:
        raw_html = f.read()
    
    # Read the expected processed text
    processed_text_path = os.path.join(os.path.dirname(__file__), 'data', 'processed_text.md')
    with open(processed_text_path, 'r', encoding='utf-8') as f:
        expected_text = f.read()
    
    # Process the HTML
    result = extract_article_text(raw_html, signature=TEST_SIGNATURE)

    # Save the result for manual inspection
    with open(os.path.join(os.path.dirname(__file__), 'data', 'temp.md'), 'w', encoding='utf-8') as f:
        f.write(result)

    assert result == expected_text


def test_basic_article():
    """Test processing a simple article with just a title and paragraph."""
    html = """
    <html>
        <head>
            <title>Test Article</title>
            <meta property="og:image" content="https://example.com/image.jpg">
        </head>
        <body>
            <article>
                <h1>Test Title</h1>
                <p>This is a test paragraph with some basic text.</p>
            </article>
        </body>
    </html>
    """
    result = extract_article_text(html, signature=TEST_SIGNATURE)
    assert "> # [Test Article](https://example.com/image.jpg)" in result
    assert "> Test Title" in result
    assert "> This is a test paragraph with some basic text." in result


def test_article_with_image():
    """Test processing an article with an image."""
    html = """
    <html>
        <body>
            <article>
                <h1>Image Test</h1>
                <img src="https://example.com/test.jpg" alt="Test Image">
                <p>This article has an image.</p>
            </article>
        </body>
    </html>
    """
    result = extract_article_text(html, signature=TEST_SIGNATURE)
    assert "> Image Test" in result
    assert "[Test Image](https://example.com/test.jpg)" in result
    assert "> This article has an image." in result


def test_article_with_links():
    """Test processing an article with various types of links."""
    html = """
    <html>
        <body>
            <article>
                <h1>Links Test</h1>
                <p>Here is a <a href="https://example.com">regular link</a>.</p>
                <p>Here is a <a href="/tema/test">topic link</a>.</p>
                <p>Here is a <a href="/tema/test" title="Test Title">topic link with title</a>.</p>
            </article>
        </body>
    </html>
    """
    result = extract_article_text(html, signature=TEST_SIGNATURE)
    assert "> Links Test" in result
    assert "> Here is a [regular link](https://example.com/)." in result
    assert "> Here is a topic link." in result
    assert "> Here is a topic link with title." in result


def test_article_with_blockquotes():
    """Test processing an article with blockquotes."""
    html = """
    <html>
        <body>
            <article>
                <h1>Blockquote Test</h1>
                <blockquote>
                    <p>This is a blockquote.</p>
                    <p>It has multiple paragraphs.</p>
                </blockquote>
            </article>
        </body>
    </html>
    """
    result = extract_article_text(html, signature=TEST_SIGNATURE)
    assert "> This is a blockquote." in result
    assert "> It has multiple paragraphs." in result


def test_article_with_lists():
    """Test processing an article with ordered and unordered lists."""
    html = """
    <html>
        <body>
            <article>
                <h1>Lists Test</h1>
                <ul>
                    <li>First item</li>
                    <li>Second item</li>
                </ul>
                <ol>
                    <li>Numbered item 1</li>
                    <li>Numbered item 2</li>
                </ol>
            </article>
        </body>
    </html>
    """
    result = extract_article_text(html, signature=TEST_SIGNATURE)
    assert "> Lists Test" in result
    assert "> * First item" in result
    assert "> * Second item" in result
    assert "> 1. Numbered item 1" in result
    assert "> 2. Numbered item 2" in result


def test_ru_domain_replacement():
    """Test replacing .ru domain links with example.com."""
    # Test basic .ru domain replacement
    text = "Here is a [link](https://example.ru/path) to a .ru site"
    expected = "Here is a [link](https://example.com) to a .ru site"
    assert replace_ru_domains(text) == expected

    # Test multiple .ru domains
    text = "Multiple links: [link1](https://site1.ru/path) and [link2](https://site2.ru/path)"
    expected = "Multiple links: [link1](https://example.com) and [link2](https://example.com)"
    assert replace_ru_domains(text) == expected

    # Test mixed domains
    text = "Mixed links: [ru](https://site.ru/path) and [com](https://site.com/path)"
    expected = "Mixed links: [ru](https://example.com) and [com](https://site.com/path)"
    assert replace_ru_domains(text) == expected

    # Test no .ru domains
    text = "No .ru links: [link1](https://site1.com/path) and [link2](https://site2.com/path)"
    assert replace_ru_domains(text) == text

    # Test empty text
    assert replace_ru_domains("") == ""

    # Test text without links
    text = "This is just plain text without any links"
    assert replace_ru_domains(text) == text


def test_article_with_ru_links():
    """Test processing an article with .ru domain links."""
    html = """
    <html>
        <body>
            <article>
                <h1>RU Links Test</h1>
                <p>Here is a <a href="https://example.ru/path">ru link</a>.</p>
                <p>Here is a <a href="https://example.com/path">com link</a>.</p>
                <p>Here is a <a href="https://subdomain.example.ru/path">subdomain ru link</a>.</p>
            </article>
        </body>
    </html>
    """
    result = extract_article_text(html, signature=TEST_SIGNATURE)
    assert "> RU Links Test" in result
    assert "> Here is a [ru link](https://example.com)." in result
    assert "> Here is a [com link](https://example.com/path)." in result
    assert "> Here is a [subdomain ru link](https://example.com)." in result


def test_signature_with_ru_links():
    """Test processing signature with .ru domain links."""
    signature = '<div id="firma"><hr><p><a href="https://site.ru/path">RU Link</a> | <a href="https://site.com/path">COM Link</a></p></div>'
    html = """
    <html>
        <body>
            <article>
                <h1>Test Article</h1>
                <p>Test content</p>
            </article>
        </body>
    </html>
    """
    result = extract_article_text(html, signature=signature)
    assert "[RU Link](https://example.com)" in result
    assert "[COM Link](https://site.com/path)" in result


def test_get_base_url():
    """Test extracting base URL from HTML content."""
    # Test with canonical URL
    html = """
    <html>
        <head>
            <link rel="canonical" href="https://example.com/article">
        </head>
    </html>
    """
    assert get_base_url(html) == "https://example.com/article"

    # Test with og:url
    html = """
    <html>
        <head>
            <meta property="og:url" content="https://example.com/og-article">
        </head>
    </html>
    """
    assert get_base_url(html) == "https://example.com/og-article"

    # Test with provided article_url
    html = "<html></html>"
    assert get_base_url(html, "https://example.com/provided") == "https://example.com/provided"

    # Test with no URL available
    html = "<html></html>"
    assert get_base_url(html) is None


def test_is_same_domain():
    """Test domain comparison functionality."""
    assert is_same_domain("https://example.com/path", "https://example.com/other") is True
    assert is_same_domain("https://example.com/path", "https://sub.example.com/path") is False
    assert is_same_domain("https://example.com/path", "https://example.org/path") is False
    assert is_same_domain("https://example.com/path", "http://example.com/path") is True
    assert is_same_domain("https://example.com:8080/path", "https://example.com/path") is True


def test_convert_relative_urls():
    """Test conversion of relative URLs to absolute URLs."""
    base_url = "https://example.com/article"
    
    # Test path-absolute URLs
    html = """
    <html>
        <body>
            <a href="/path/to/page">Link</a>
            <img src="/images/photo.jpg" alt="Photo">
        </body>
    </html>
    """
    result = convert_relative_urls(html, base_url)
    assert 'href="https://example.com/path/to/page"' in result
    assert 'src="https://example.com/images/photo.jpg"' in result

    # Test path-relative URLs
    html = """
    <html>
        <body>
            <a href="relative/page">Link</a>
            <img src="images/photo.jpg" alt="Photo">
        </body>
    </html>
    """
    result = convert_relative_urls(html, base_url)
    assert 'href="https://example.com/article/relative/page"' in result
    assert 'src="https://example.com/article/images/photo.jpg"' in result

    # Test with no base URL
    html = '<a href="/path">Link</a>'
    assert convert_relative_urls(html, None) == html

    # Test with already absolute URLs
    html = """
    <html>
        <body>
            <a href="https://other.com/path">Link</a>
            <img src="https://other.com/image.jpg" alt="Photo">
        </body>
    </html>
    """
    result = convert_relative_urls(html, base_url)
    assert 'href="https://other.com/path"' in result
    assert 'src="https://other.com/image.jpg"' in result


def test_article_with_relative_urls():
    """Test processing an article with relative URLs."""
    html = """
    <html>
        <head>
            <link rel="canonical" href="https://example.com/article">
        </head>
        <body>
            <article>
                <h1>Relative URLs Test</h1>
                <p>Here is a <a href="/path/to/page">path-absolute link</a>.</p>
                <p>Here is a <a href="relative/page">path-relative link</a>.</p>
                <img src="/images/photo.jpg" alt="Photo">
                <img src="images/other.jpg" alt="Other">
            </article>
        </body>
    </html>
    """
    result = extract_article_text(html, signature=TEST_SIGNATURE)
    assert "> Here is a [path-absolute link](https://example.com/path/to/page)." in result
    assert "> Here is a [path-relative link](https://example.com/article/relative/page)." in result
    assert "[Photo](https://example.com/images/photo.jpg)" in result
    assert "[Other](https://example.com/article/images/other.jpg)" in result


def test_article_with_domain_redirect():
    """Test processing an article where the domain has changed due to redirect."""
    html = """
    <html>
        <head>
            <link rel="canonical" href="https://redirected.com/article">
        </head>
        <body>
            <article>
                <h1>Redirect Test</h1>
                <p>Here is a <a href="/path/to/page">link</a>.</p>
                <img src="/images/photo.jpg" alt="Photo">
            </article>
        </body>
    </html>
    """
    result = extract_article_text(html, signature=TEST_SIGNATURE)
    assert "> Here is a [link](https://redirected.com/path/to/page)." in result
    assert "[Photo](https://redirected.com/images/photo.jpg)" in result
