import threading
import logging
from curl_cffi import requests
import gzip
import time
from datetime import datetime
import sqlite3
from .base_thread import BaseThread
from infrastructure.database import (
    get_posts_to_fetch, 
    mark_post_as_fetched, 
    increment_retry_and_schedule,
    delete_post
)

class NewspaperFetcherThread(BaseThread):
    def __init__(self, db_path: str, db_lock: threading.Lock, logger: logging.Logger):
        super().__init__(db_path, db_lock, logger)
    
    def process_cycle(self, conn):
        """Fetch and process newspaper articles."""
        with self.db_lock:
            try:
                # Get posts that are ready to be fetched
                posts = get_posts_to_fetch(conn)
                if posts:
                    self.logger.info(f"Found {len(posts)} posts ready to fetch")
                
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
                        
                        # Mark post as fetched and store content
                        try:
                            mark_post_as_fetched(conn, post_id, html_content)
                            self.logger.info(f"Successfully fetched and stored article for post {post_id}")
                        except sqlite3.Error as e:
                            self.logger.error(f"Database error while storing article for post {post_id}: {e}")
                            continue
                        
                    except Exception as e:
                        self.logger.error(f"Error fetching article from {url}: {e}")
                        
                        # Handle fetch failure with retry logic
                        retry_time = int(time.time()) + (10 * 60)  # 10 minutes from now
                        try:
                            retry_count = increment_retry_and_schedule(conn, post_id, retry_time)
                            self.logger.info(f"Scheduled retry for post {post_id} at {datetime.fromtimestamp(retry_time).isoformat()}")
                            
                            if retry_count > 3:
                                self.logger.info(f"Deleting post {post_id} after {retry_count} failed attempts")
                                try:
                                    delete_post(conn, post_id)
                                    self.logger.info(f"Deleted post {post_id} and its associated text")
                                except sqlite3.Error as e:
                                    self.logger.error(f"Database error while deleting post {post_id}: {e}")
                        except sqlite3.Error as e:
                            self.logger.error(f"Database error while handling retry for post {post_id}: {e}")
                            continue
            except sqlite3.Error as e:
                self.logger.error(f"Database error while fetching posts: {e}") 