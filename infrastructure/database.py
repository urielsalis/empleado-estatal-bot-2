import os
import sqlite3
from pathlib import Path
import logging
import time
import threading

logger = logging.getLogger(__name__)

# Thread-local storage for database connections
_thread_local = threading.local()

# Global reentrant lock for write operations
_write_rlock = threading.RLock()

# Global database path
_db_path = None

def _get_current_time() -> int:
    """Helper function to get current UTC timestamp."""
    return int(time.time())

def init_db() -> str:
    """Initialize the database and return the path to the DB file as a string."""
    global _db_path
    
    # Use DATA_DIR environment variable if set, otherwise default to 'data'
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    data_dir.mkdir(exist_ok=True)
    
    _db_path = str(data_dir / "bot.db")
    logger.info(f"Initializing database at: {_db_path}")
    
    # Create tables if they don't exist
    conn = get_db_connection()
    with _write_rlock:
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
                ('posts_skipped', 0),
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
    
    return _db_path

def get_db_connection() -> sqlite3.Connection:
    """Get or create a database connection for the current thread."""
    if not _db_path:
        raise RuntimeError("Database not initialized. Call init_db() first.")
        
    if not hasattr(_thread_local, 'connection'):
        conn = sqlite3.connect(_db_path, timeout=30.0)  # 30 second timeout
        conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging
        conn.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
        conn.execute("PRAGMA synchronous=NORMAL")  # Slightly faster writes
        conn.execute("PRAGMA cache_size=-2000")  # Use 2MB of memory for cache
        _thread_local.connection = conn
        logger.info(f"Created new database connection for thread {threading.current_thread().name}")
    return _thread_local.connection

def close_db_connection() -> None:
    """Close the database connection for the current thread."""
    if hasattr(_thread_local, 'connection'):
        try:
            _thread_local.connection.close()
            del _thread_local.connection
            logger.info(f"Closed database connection for thread {threading.current_thread().name}")
        except Exception as e:
            logger.error(f"Error closing connection: {e}")

def _update_stat(stat_name: str, increment: int = 1) -> None:
    """Internal function to update a statistic."""
    conn = get_db_connection()
    with _write_rlock:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE post_stats 
            SET stat_value = stat_value + ?,
                last_updated_utc = ?
            WHERE stat_name = ?
        """, (increment, _get_current_time(), stat_name))
        conn.commit()

def cleanup_old_posts() -> None:
    """Delete posts that were posted more than 1 day ago or have no text content."""
    conn = get_db_connection()
    with _write_rlock:
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
            
            conn.commit()
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old posts and their associated texts")
            
        except sqlite3.Error as e:
            logger.error(f"Failed to clean up posts: {e}")
            raise

def insert_post(reddit_id: str, subreddit: str, url: str, created_utc: int) -> None:
    """Insert a new post if it doesn't exist."""
    conn = get_db_connection()
    with _write_rlock:
        current_time = _get_current_time()
        cursor = conn.cursor()
        
        try:
            # Insert the post and update stats in a single transaction
            cursor.executescript(f"""
                BEGIN TRANSACTION;
                
                -- Insert the post
                INSERT OR IGNORE INTO posts (reddit_id, subreddit, url, created_utc, fetch_at_utc) 
                VALUES ('{reddit_id}', '{subreddit}', '{url}', {created_utc}, {current_time});
                
                -- If a new post was inserted, update stats
                UPDATE post_stats 
                SET stat_value = stat_value + 1,
                    last_updated_utc = {current_time}
                WHERE stat_name = 'total_posts'
                AND EXISTS (
                    SELECT 1 FROM posts 
                    WHERE reddit_id = '{reddit_id}' 
                    AND id = last_insert_rowid()
                );
                
                -- Update oldest/newest post if needed
                UPDATE post_stats 
                SET stat_value = CASE 
                    WHEN stat_name = 'oldest_post' AND (stat_value = 0 OR stat_value > {created_utc}) THEN {created_utc}
                    WHEN stat_name = 'newest_post' AND (stat_value = 0 OR stat_value < {created_utc}) THEN {created_utc}
                    ELSE stat_value 
                END,
                last_updated_utc = {current_time}
                WHERE stat_name IN ('oldest_post', 'newest_post');
                
                COMMIT;
            """)
            
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to insert post: {e}")
            raise

def get_posts_to_fetch(limit: int = 10) -> list[tuple[int, str]]:
    """Get posts that are ready to be fetched."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url 
        FROM posts 
        WHERE fetched_at_utc IS NULL
        AND fetch_at_utc <= ?
        LIMIT ?
    """, (_get_current_time(), limit))
    return cursor.fetchall()

def mark_post_as_fetched(post_id: int, html_content: str) -> None:
    """Mark a post as fetched and store its HTML content."""
    conn = get_db_connection()
    with _write_rlock:
        current_time = _get_current_time()
        cursor = conn.cursor()
        
        try:
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
                
                -- Update stats
                UPDATE post_stats 
                SET stat_value = stat_value + 1,
                    last_updated_utc = {current_time}
                WHERE stat_name = 'posts_fetched';
                
                COMMIT;
            """)
            
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to mark post {post_id} as fetched: {e}")
            raise

def increment_retry_and_schedule(post_id: int, retry_time: int) -> int:
    """Increment retry count and schedule next retry in a single query."""
    conn = get_db_connection()
    with _write_rlock:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE posts 
            SET retry_count = retry_count + 1,
                fetch_at_utc = ?
            WHERE id = ?
            RETURNING retry_count
        """, (retry_time, post_id))
        conn.commit()
        return cursor.fetchone()[0]

def delete_post(post_id: int) -> None:
    """Delete a post and its associated text."""
    conn = get_db_connection()
    with _write_rlock:
        cursor = conn.cursor()
        cursor.executescript(f"""
            BEGIN TRANSACTION;
            
            DELETE FROM texts WHERE post_id = {post_id};
            DELETE FROM posts WHERE id = {post_id};
            
            COMMIT;
        """)
        conn.commit()

def get_posts_to_process(limit: int = 10) -> list[tuple[int, str]]:
    """Get posts that have been fetched but not processed."""
    conn = get_db_connection()
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

def mark_post_as_processed(post_id: int, processed_text: str) -> None:
    """Mark a post as processed and store its processed text."""
    conn = get_db_connection()
    with _write_rlock:
        current_time = _get_current_time()
        cursor = conn.cursor()
        
        try:
            # Store the processed text and update post status in a single transaction
            cursor.executescript(f"""
                BEGIN TRANSACTION;
                
                -- Update the text
                UPDATE texts 
                SET text = '{processed_text.replace("'", "''")}'
                WHERE post_id = {post_id};
                
                -- Update the post's processed timestamp
                UPDATE posts 
                SET processed_at_utc = {current_time}
                WHERE id = {post_id};
                
                -- Update stats
                UPDATE post_stats 
                SET stat_value = stat_value + 1,
                    last_updated_utc = {current_time}
                WHERE stat_name = 'posts_processed';
                
                COMMIT;
            """)
            
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error while marking post {post_id} as processed: {e}")
            raise

def get_posts_to_post(limit: int = 10) -> list[tuple[int, str, str, str]]:
    """Get posts that have been processed but not posted yet."""
    conn = get_db_connection()
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

def mark_post_as_posted(post_id: int) -> None:
    """Mark a post as posted."""
    conn = get_db_connection()
    with _write_rlock:
        current_time = _get_current_time()
        cursor = conn.cursor()
        
        try:
            cursor.executescript(f"""
                BEGIN TRANSACTION;
                
                -- Update the post's posted timestamp
                UPDATE posts 
                SET posted_at_utc = {current_time}
                WHERE id = {post_id};
                
                -- Update stats
                UPDATE post_stats 
                SET stat_value = stat_value + 1,
                    last_updated_utc = {current_time}
                WHERE stat_name = 'posts_posted';
                
                COMMIT;
            """)
            
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to mark post {post_id} as posted: {e}")
            raise

def mark_post_as_skipped() -> None:
    """Increment the posts_skipped stat."""
    with _write_rlock:
        try:
            _update_stat('posts_skipped')
        except sqlite3.Error as e:
            logger.error(f"Failed to increment posts_skipped stat: {e}")
            raise

def handle_fetch_retry(post_id: int, retry_time: int) -> bool:
    """Handle a fetch retry for a post. Returns True if post was skipped, False otherwise."""
    conn = get_db_connection()
    with _write_rlock:
        try:
            # First commit any pending transaction
            conn.commit()
            
            # Increment retry count and schedule next retry
            retry_count = increment_retry_and_schedule(post_id, retry_time)
            
            # Log the retry time
            retry_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(retry_time))
            logger.info(f"Post {post_id} will be retried at {retry_time_str} (retry count: {retry_count})")
            
            # If max retries reached, delete the post and increment skipped stat
            if retry_count > 3:
                delete_post(post_id)
                _update_stat('posts_skipped')
                return True
                
            return False
        except sqlite3.Error as e:
            logger.error(f"Failed to handle fetch retry for post {post_id}: {e}")
            raise 