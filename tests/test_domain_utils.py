import pytest
from utils.domain_utils import compile_domain_patterns, is_domain_banned

@pytest.fixture(scope="module")
def banned_patterns():
    banned_domains = [
        "*.blocked.com",
        "blocked2.com"
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