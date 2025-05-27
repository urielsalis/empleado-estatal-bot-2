import threading
import logging
from curl_cffi import requests
import gzip
import time
from datetime import datetime
from .base_thread import BaseThread

class NewspaperFetcherThread(BaseThread):
    def __init__(self, db_path: str, db_lock: threading.Lock, logger: logging.Logger):
        super().__init__(db_path, db_lock, logger)
    
    def process_cycle(self):
        """Fetch and process newspaper articles."""
        with self.db_lock:
            # Get posts that are ready to be fetched
            cursor = self.conn.cursor()
            current_time = int(time.time())
            cursor.execute("""
                SELECT id, url 
                FROM posts 
                WHERE fetched_at_utc IS NULL
                AND fetch_at_utc <= ?
                LIMIT 10
            """, (current_time,))
            posts = cursor.fetchall()
            
            for post_id, url in posts:
                try:
                    self.logger.info(f"Fetching article from {url}")
                    
                    # Download the article HTML with realistic user agent
                    response = requests.get(url, impersonate="chrome")
                    response.raise_for_status()  # Raise exception for bad status codes
                    
                    # Check if content is gzipped (magic numbers: 0x1f 0x8b 0x08)
                    content = response.content
                    if content.startswith(b'\x1f\x8b\x08'):
                        self.logger.info(f"Detected gzipped content for {url}, decompressing...")
                        content = gzip.decompress(content)
                    
                    html_content = content.decode('utf-8', errors='replace')
                    
                    # Store the raw HTML
                    cursor.execute("""
                        INSERT INTO texts (post_id, raw_text)
                        VALUES (?, ?)
                    """, (post_id, html_content))
                    
                    # Update the post's fetched timestamp
                    cursor.execute("""
                        UPDATE posts 
                        SET fetched_at_utc = ?,
                            fetch_at_utc = NULL
                        WHERE id = ?
                    """, (current_time, post_id))
                    
                    self.conn.commit()
                    self.logger.info(f"Successfully fetched article for post {post_id}")
                    
                except Exception as e:
                    self.logger.error(f"Error fetching article from {url}: {e}")
                    
                    # Increment retry count and check if we should delete
                    cursor.execute("""
                        UPDATE posts 
                        SET retry_count = retry_count + 1
                        WHERE id = ?
                        RETURNING retry_count
                    """, (post_id,))
                    new_retry_count = cursor.fetchone()[0]
                    
                    if new_retry_count > 3:
                        # Delete the post and its associated text
                        cursor.execute("DELETE FROM texts WHERE post_id = ?", (post_id,))
                        cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
                        self.logger.info(f"Deleted post {post_id} after {new_retry_count} failed attempts")
                    else:
                        # Set fetch_at_utc to 10 minutes from now
                        retry_time = current_time + (10 * 60)
                        cursor.execute("""
                            UPDATE posts 
                            SET fetch_at_utc = ?
                            WHERE id = ?
                        """, (retry_time, post_id))
                        self.logger.info(f"Scheduled retry for post {post_id} at {datetime.fromtimestamp(retry_time).isoformat()}")
                    
                    self.conn.commit()
                    continue 