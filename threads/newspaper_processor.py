import threading
import logging
from .base_thread import BaseThread
from utils.newspaper_processor import extract_article_text
from infrastructure.config import load_config

class NewspaperProcessorThread(BaseThread):
    def __init__(self, db_path: str, db_lock: threading.Lock, logger: logging.Logger):
        super().__init__(db_path, db_lock, logger)
        self.config = load_config()
        self.signature = self.config['newspaper_processor']['signature']
    
    def process_cycle(self):
        """Process newspaper articles."""
        with self.db_lock:
            # Get posts that have been fetched but not processed
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT p.id, t.raw_text 
                FROM posts p
                JOIN texts t ON p.id = t.post_id
                WHERE p.processed_at_utc IS NULL 
                AND t.raw_text IS NOT NULL
                LIMIT 10
            """)
            posts = cursor.fetchall()
            
            for post_id, raw_text in posts:
                try:
                    self.logger.info(f"Processing article for post {post_id}")
                    
                    # Process the raw text
                    processed_text = extract_article_text(raw_text, signature=self.signature)
                    if not processed_text:
                        self.logger.warning(f"Could not extract text from post {post_id}")
                        # Delete the row
                        cursor.execute("""
                            DELETE FROM texts 
                            WHERE post_id = ?
                        """, (post_id))
                        cursor.execute("""
                            DELETE FROM posts 
                            WHERE id = ?
                        """, (post_id))
                        self.conn.commit()
                        continue
                    
                    # Update the processed text
                    cursor.execute("""
                        UPDATE texts 
                        SET text = ? 
                        WHERE post_id = ?
                    """, (processed_text, post_id))
                    
                    # Mark the post as processed
                    cursor.execute("""
                        UPDATE posts 
                        SET processed_at_utc = strftime('%s', 'now')
                        WHERE id = ?
                    """, (post_id,))
                    
                    self.conn.commit()
                    self.logger.info(f"Successfully processed article for post {post_id}")
                    
                except Exception as e:
                    self.logger.error(f"Error processing article for post {post_id}: {e}")
                    continue
