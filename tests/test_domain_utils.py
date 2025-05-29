import pytest
from utils.domain_utils import compile_domain_patterns, is_domain_banned

@pytest.fixture(scope="module")
def banned_patterns():
    banned_domains = [
        "*.blocked.com",
        "blocked2.com",
        "*.jpg",
        "*.ru"
    ]
    return compile_domain_patterns(banned_domains)

def pytest_case_runner(test_cases, banned_patterns):
    for url, expected in test_cases:
        assert is_domain_banned(url, banned_patterns) == expected, (
            f"URL {url} should {'be' if expected else 'not be'} banned"
        )

def test_blocked_com_and_blocked2_com(banned_patterns):
    test_cases = [
        ("https://blocked.com/page", False),  # root domain not matched by wildcard
        ("https://blocked.com/another/path?query=1", False),
        ("https://www.blocked.com/page", True),
        ("https://sub.blocked.com/page", True),
        ("https://deep.sub.blocked.com/page", True),
        ("https://blocked2.com/page", True),  # exact match
        ("https://blocked2.com/another/path?query=1", True),  # any path on blocked2.com
        ("https://www.blocked2.com/page", False),  # not matched by wildcard or exact
        ("https://allowed.com/page", False),
        ("https://fakeblocked.com/page", False),
        ("https://blocked.com.org/page", False),
        ("https://blocked.com/image.jpg", True),
        ("https://blocked.com/image.html", False),
        ("https://blocked.ru/image.html", True),
        ("https://blocked.com/image.ru", True),
    ]
    pytest_case_runner(test_cases, banned_patterns)

def test_case_insensitivity(banned_patterns):
    test_cases = [
        ("https://BLOCKED2.com/page", True),
        ("https://Blocked2.Com/page", True),
        ("https://blocked.COM/page", False),
        ("https://SUB.BLOCKED.com/page", True),
    ]
    pytest_case_runner(test_cases, banned_patterns)

def test_complex_urls(banned_patterns):
    test_cases = [
        ("https://sub.blocked.com:8080/path?query=123", True),
        ("https://user:pass@blocked2.com/page", True),
        ("https://blocked.com/path/with/multiple/levels", False),
        ("https://blocked2.com/path/with/multiple/levels", True),
        ("https://allowed.com/path?with=params&and=more", False),
    ]
    pytest_case_runner(test_cases, banned_patterns)

def test_file_extensions(banned_patterns):
    test_cases = [
        ("https://example.com/image.jpg", True),  # *.jpg pattern
        ("https://example.com/image.jpeg", False),  # *.jpeg pattern
        ("https://example.com/image.html", False),  # not banned extension
        ("https://example.com/image.jpg?query=1", True),  # with query params
        ("https://example.com/image.jpg#fragment", True),  # with fragment
        ("https://example.com/path/to/image.jpg", True),  # deep path
        ("https://example.com/image.JPG", True),  # case insensitive
        ("https://example.com/image.jpg/", True),  # trailing slash
        ("https://example.com/image.jpg.txt", False),  # not actually a jpg
        ("https://example.com/image.jpg.jpg", True),  # double extension
    ]
    pytest_case_runner(test_cases, banned_patterns)

def test_mixed_patterns(banned_patterns):
    test_cases = [
        ("https://blocked.com/image.jpg", True),  # both domain and extension banned
        ("https://allowed.com/image.jpg", True),  # only extension banned
        ("https://blocked.com/image.html", False),  # only domain banned
        ("https://allowed.com/image.html", False),  # neither banned
        ("https://www.blocked.com/image.jpg", True),  # wildcard domain + banned extension
        ("https://sub.blocked.com/image.jpg", True),  # wildcard domain + banned extension
    ]
    pytest_case_runner(test_cases, banned_patterns) 