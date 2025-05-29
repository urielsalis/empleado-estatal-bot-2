import threading
import logging
import sqlite3
from .base_thread import BaseThread
from utils.newspaper_processor import extract_article_text
from infrastructure.config import load_config
from infrastructure.database import get_posts_to_process, mark_post_as_processed, delete_post

class NewspaperProcessorThread(BaseThread):
    def __init__(self, db_path: str, db_lock: threading.Lock, logger: logging.Logger):
        super().__init__(db_path, db_lock, logger)
        self.config = load_config()
        self.signature = self.config['newspaper_processor']['signature']
    
    def process_cycle(self, conn):
        """Process newspaper articles."""
        with self.db_lock:
            try:
                # Get posts that have been fetched but not processed
                posts = get_posts_to_process(conn)
                
                for post_id, raw_text in posts:
                    try:
                        self.logger.info(f"Processing article for post {post_id}")
                        
                        # Process the raw text
                        processed_text = extract_article_text(raw_text, signature=self.signature)
                        if not processed_text:
                            self.logger.warning(f"Could not extract text from post {post_id}")
                            try:
                                delete_post(conn, post_id)
                                self.logger.info(f"Deleted post {post_id} due to failed text extraction")
                            except sqlite3.Error as e:
                                self.logger.error(f"Database error while deleting post {post_id}: {e}")
                            continue
                        
                        # Mark post as processed and store the processed text
                        try:
                            mark_post_as_processed(conn, post_id, processed_text)
                            self.logger.info(f"Successfully processed article for post {post_id}")
                        except sqlite3.Error as e:
                            self.logger.error(f"Database error while marking post {post_id} as processed: {e}")
                            continue
                        
                    except Exception as e:
                        self.logger.error(f"Error processing article for post {post_id}: {e}")
                        continue
            except sqlite3.Error as e:
                self.logger.error(f"Database error while fetching posts to process: {e}")
