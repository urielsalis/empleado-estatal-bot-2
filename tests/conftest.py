"""
Test configuration and fixtures.
"""

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def test_db_path(tmp_path: Path) -> str:
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    return str(db_path)


@pytest.fixture
def test_db(test_db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Create a test database connection."""
    conn = sqlite3.connect(test_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    # Create test tables
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reddit_id TEXT UNIQUE,
            subreddit TEXT,
            url TEXT,
            created_utc INTEGER,
            fetched_at_utc INTEGER DEFAULT NULL,
            processed_at_utc INTEGER DEFAULT NULL,
            posted_at_utc INTEGER DEFAULT NULL
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS texts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            text TEXT DEFAULT NULL,
            raw_text TEXT DEFAULT NULL,
            FOREIGN KEY (post_id) REFERENCES posts (id)
        )
    """
    )
    conn.commit()

    yield conn

    conn.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.fixture
def test_config() -> dict:
    """Return a test configuration."""
    return {
        "reddit": {
            "username": "test_bot",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "user_agent": "test_user_agent",
        },
        "subreddits": {
            "monitored": ["test_subreddit"],
            "distinguished": ["test_subreddit"],
        },
    }
