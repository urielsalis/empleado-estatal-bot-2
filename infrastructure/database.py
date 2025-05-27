import os
import sqlite3
from pathlib import Path
import logging
import time

logger = logging.getLogger(__name__)

def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Create a new database connection with proper settings for thread safety."""
    conn = sqlite3.connect(db_path, timeout=30.0)  # 30 second timeout
    conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging
    conn.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
    return conn

def cleanup_old_posts(conn: sqlite3.Connection) -> None:
    """Delete posts that were posted more than 1 day ago or have no text content."""
    try:
        # Calculate timestamp for 1 day ago
        one_day_ago = int(time.time()) - (24 * 60 * 60)
        
        cursor = conn.cursor()
        
        # Delete old posted entries
        cursor.execute("""
            DELETE FROM posts 
            WHERE posted_at_utc IS NOT NULL 
            AND posted_at_utc < ?
        """, (one_day_ago,))
        
        old_deleted = cursor.rowcount
        
        # Delete posts with no text content
        cursor.execute("""
            DELETE FROM posts 
            WHERE fetched_at_utc IS NOT NULL 
            AND processed_at_utc IS NULL 
            AND id IN (
                SELECT post_id 
                FROM texts 
                WHERE text IS NULL
            )
        """)
        
        no_text_deleted = cursor.rowcount
        
        if old_deleted > 0 or no_text_deleted > 0:
            logger.info(f"Cleaned up {old_deleted} old posted entries and {no_text_deleted} posts with no text content")
        
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to clean up posts: {e}")
        raise

def init_db() -> str:
    """Initialize the database and return the path to the DB file as a string."""
    # Use DATA_DIR environment variable if set, otherwise default to 'data'
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    data_dir.mkdir(exist_ok=True)
    
    db_path = data_dir / "bot.db"
    logger.info(f"Initializing database at: {db_path}")
    
    try:
        conn = get_db_connection(str(db_path))
        logger.info("Database connection established successfully.")
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to the database: {e}")
        raise
    
    # Create tables if they don't exist
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reddit_id TEXT UNIQUE,
                subreddit TEXT,
                url TEXT,
                created_utc INTEGER,
                fetch_at_utc INTEGER DEFAULT NULL,
                fetched_at_utc INTEGER DEFAULT NULL,
                processed_at_utc INTEGER DEFAULT NULL,
                posted_at_utc INTEGER DEFAULT NULL,
                retry_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS texts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER,
                text TEXT DEFAULT NULL,
                raw_text TEXT DEFAULT NULL,
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        """)
        conn.commit()
        logger.info("Database tables created or already exist.")
        
        
    except sqlite3.Error as e:
        logger.error(f"Failed to create tables: {e}")
        raise
    finally:
        conn.close()
    
    return str(db_path)

def insert_post(conn: sqlite3.Connection, reddit_id: str, subreddit: str, url: str, created_utc: int) -> None:
    """Insert a new post if it doesn't exist."""
    try:
        current_time = int(time.time())
        conn.execute(
            "INSERT OR IGNORE INTO posts (reddit_id, subreddit, url, created_utc, fetch_at_utc) VALUES (?, ?, ?, ?, ?)",
            (reddit_id, subreddit, url, created_utc, current_time)
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error while inserting post {reddit_id}: {e}")
        raise 