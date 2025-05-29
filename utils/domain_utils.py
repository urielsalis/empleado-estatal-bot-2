import re
from urllib.parse import urlparse
from typing import List, Tuple


def compile_domain_patterns(patterns: List[str]) -> Tuple[List[str], List[re.Pattern], List[str]]:
    """Compile domain patterns into exact and wildcard lists.
    Returns (exact_domains, wildcard_patterns, file_extensions)
    """
    exact_domains = []
    wildcard_patterns = []
    file_extensions = []
    for pattern in patterns:
        if pattern.startswith('*.'):
            ext_candidate = pattern[2:]
            # Add to file extensions
            file_extensions.append(ext_candidate.lower())
            # Add to wildcard domain patterns
            base = ext_candidate
            wildcard_patterns.append(re.compile(rf"^([^.]+\.)+{re.escape(base)}$", re.IGNORECASE))
        else:
            # Exact domain
            exact_domains.append(pattern.lower())
    return exact_domains, wildcard_patterns, file_extensions


def is_domain_banned(url: str, banned_patterns: Tuple[List[str], List[re.Pattern], List[str]]) -> bool:
    """Check if the URL's domain is in the banned list (exact or wildcard)."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower().rstrip('/')  # Remove trailing slash
        # Always remove user:pass if present
        if '@' in domain:
            domain = domain.split('@')[-1]
        # Remove port number if present
        if ':' in domain:
            domain = domain.split(':')[0]
        exact_domains, wildcard_patterns, file_extensions = banned_patterns
        # Check exact match
        if domain in exact_domains:
            return True
        # Check wildcard patterns
        for pattern in wildcard_patterns:
            if pattern.match(domain):
                return True
        # Check file extensions
        for ext in file_extensions:
            if path.endswith(f'.{ext}'):
                return True
        return False
    except Exception:
        return False 