import os
import sqlite3
from pathlib import Path
import logging
import time

logger = logging.getLogger(__name__)

def _get_current_time() -> int:
    """Helper function to get current UTC timestamp."""
    return int(time.time())

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
        one_day_ago = _get_current_time() - (24 * 60 * 60)
        
        cursor = conn.cursor()
        
        # Delete old posts and their associated texts in a single transaction
        cursor.executescript(f"""
            BEGIN TRANSACTION;
            
            -- Delete old posted entries and their texts
            DELETE FROM texts 
            WHERE post_id IN (
                SELECT id FROM posts 
                WHERE posted_at_utc IS NOT NULL 
                AND posted_at_utc < {one_day_ago}
            );
            
            DELETE FROM posts 
            WHERE posted_at_utc IS NOT NULL 
            AND posted_at_utc < {one_day_ago};
            
            -- Delete posts with no text content and their texts
            DELETE FROM texts 
            WHERE post_id IN (
                SELECT id FROM posts 
                WHERE fetched_at_utc IS NOT NULL 
                AND processed_at_utc IS NULL 
                AND id IN (
                    SELECT post_id 
                    FROM texts 
                    WHERE text IS NULL
                )
            );
            
            DELETE FROM posts 
            WHERE fetched_at_utc IS NOT NULL 
            AND processed_at_utc IS NULL 
            AND id IN (
                SELECT post_id 
                FROM texts 
                WHERE text IS NULL
            );
            
            COMMIT;
        """)
        
        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old posts and their associated texts")
        
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS post_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_name TEXT UNIQUE,
                stat_value INTEGER DEFAULT 0,
                last_updated_utc INTEGER
            )
        """)
        
        # Initialize default statistics if they don't exist
        default_stats = [
            ('total_posts', 0),
            ('posts_fetched', 0),
            ('content_fetched', 0),
            ('posts_processed', 0),
            ('posts_posted', 0),
            ('oldest_post', 0),
            ('newest_post', 0)
        ]
        
        for stat_name, initial_value in default_stats:
            conn.execute("""
                INSERT OR IGNORE INTO post_stats (stat_name, stat_value, last_updated_utc)
                VALUES (?, ?, ?)
            """, (stat_name, initial_value, _get_current_time()))
            
        conn.commit()
        logger.info("Database tables created or already exist.")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to create tables: {e}")
        raise
    finally:
        conn.close()
    
    return str(db_path)

def _update_stat(conn: sqlite3.Connection, stat_name: str, increment: int = 1) -> None:
    """Internal function to update a statistic."""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE post_stats 
        SET stat_value = stat_value + ?,
            last_updated_utc = ?
        WHERE stat_name = ?
    """, (increment, _get_current_time(), stat_name))

def insert_post(conn: sqlite3.Connection, reddit_id: str, subreddit: str, url: str, created_utc: int) -> None:
    """Insert a new post if it doesn't exist."""
    cursor = conn.cursor()
    
    # Insert the post
    cursor.execute(
        "INSERT OR IGNORE INTO posts (reddit_id, subreddit, url, created_utc, fetch_at_utc) VALUES (?, ?, ?, ?, ?)",
        (reddit_id, subreddit, url, created_utc, _get_current_time())
    )
    
    # If a new post was inserted (rowcount > 0), update stats
    if cursor.rowcount > 0:
        _update_stat(conn, 'total_posts')
        
        # Update oldest/newest post if needed
        cursor.execute("""
            UPDATE post_stats 
            SET stat_value = CASE 
                WHEN stat_name = 'oldest_post' AND (stat_value = 0 OR stat_value > ?) THEN ?
                WHEN stat_name = 'newest_post' AND (stat_value = 0 OR stat_value < ?) THEN ?
                ELSE stat_value 
            END,
            last_updated_utc = ?
            WHERE stat_name IN ('oldest_post', 'newest_post')
        """, (created_utc, created_utc, created_utc, created_utc, _get_current_time()))
    
    conn.commit()

def get_posts_to_fetch(conn: sqlite3.Connection, limit: int = 10) -> list[tuple[int, str]]:
    """Get posts that are ready to be fetched."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url 
        FROM posts 
        WHERE fetched_at_utc IS NULL
        AND fetch_at_utc <= ?
        LIMIT ?
    """, (_get_current_time(), limit))
    return cursor.fetchall()

def mark_post_as_fetched(conn: sqlite3.Connection, post_id: int, html_content: str) -> None:
    """Mark a post as fetched and store its HTML content."""
    current_time = _get_current_time()
    cursor = conn.cursor()
    
    # Store the raw HTML, update post status, and increment counter in a single transaction
    cursor.executescript(f"""
        BEGIN TRANSACTION;
        
        -- Store the raw HTML
        INSERT INTO texts (post_id, raw_text)
        VALUES ({post_id}, '{html_content.replace("'", "''")}');
        
        -- Update the post's fetched timestamp
        UPDATE posts 
        SET fetched_at_utc = {current_time},
            fetch_at_utc = NULL
        WHERE id = {post_id};
        
        COMMIT;
    """)
    
    # Update stats after successful transaction
    _update_stat(conn, 'posts_fetched')

def increment_retry_and_schedule(conn: sqlite3.Connection, post_id: int, retry_time: int) -> int:
    """Increment retry count and schedule next retry in a single query."""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE posts 
        SET retry_count = retry_count + 1,
            fetch_at_utc = ?
        WHERE id = ?
        RETURNING retry_count
    """, (retry_time, post_id))
    return cursor.fetchone()[0]

def delete_post(conn: sqlite3.Connection, post_id: int) -> None:
    """Delete a post and its associated text."""
    cursor = conn.cursor()
    cursor.executescript(f"""
        BEGIN TRANSACTION;
        
        DELETE FROM texts WHERE post_id = {post_id};
        DELETE FROM posts WHERE id = {post_id};
        
        COMMIT;
    """)

def get_posts_to_process(conn: sqlite3.Connection, limit: int = 10) -> list[tuple[int, str]]:
    """Get posts that have been fetched but not processed."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, t.raw_text 
        FROM posts p
        JOIN texts t ON p.id = t.post_id
        WHERE p.processed_at_utc IS NULL 
        AND t.raw_text IS NOT NULL
        LIMIT ?
    """, (limit,))
    return cursor.fetchall()

def mark_post_as_processed(conn: sqlite3.Connection, post_id: int, processed_text: str) -> None:
    """Mark a post as processed and store its processed text."""
    current_time = _get_current_time()
    cursor = conn.cursor()
    
    # Update processed text and mark post as processed in a single transaction
    cursor.executescript(f"""
        BEGIN TRANSACTION;
        
        -- Update the processed text
        UPDATE texts 
        SET text = '{processed_text.replace("'", "''")}'
        WHERE post_id = {post_id};
        
        -- Mark the post as processed
        UPDATE posts 
        SET processed_at_utc = {current_time}
        WHERE id = {post_id};
        
        COMMIT;
    """)
    
    # Update stats after successful transaction
    _update_stat(conn, 'posts_processed')

def get_posts_to_post(conn: sqlite3.Connection, limit: int = 10) -> list[tuple[int, str, str, str]]:
    """Get posts that have been processed but not posted yet."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.reddit_id, p.subreddit, t.text
        FROM posts p
        JOIN texts t ON p.id = t.post_id
        WHERE p.processed_at_utc IS NOT NULL 
        AND p.posted_at_utc IS NULL
        AND t.text IS NOT NULL
        LIMIT ?
    """, (limit,))
    return cursor.fetchall()

def mark_post_as_posted(conn: sqlite3.Connection, post_id: int) -> None:
    """Mark a post as posted."""
    cursor = conn.cursor()
    
    # Mark post as posted in a single transaction
    cursor.execute("""
        UPDATE posts 
        SET posted_at_utc = ?
        WHERE id = ?
    """, (_get_current_time(), post_id))
    
    # Update stats after successful transaction
    _update_stat(conn, 'posts_posted') 