import logging
from .base_thread import BaseThread
from utils.newspaper_processor import extract_article_text
from infrastructure.config import load_config
from infrastructure.database import get_posts_to_process, mark_post_as_processed, delete_post

class NewspaperProcessorThread(BaseThread):
    def __init__(self, logger: logging.Logger):
        super().__init__(logger)
        self.config = load_config()
        self.signature = self.config['newspaper_processor']['signature']
    
    def process_cycle(self):
        """Process newspaper articles."""
        try:
            # Get posts that have been fetched but not processed
            posts = get_posts_to_process()
            if posts:
                self.logger.info(f"Found {len(posts)} posts to process")
                
                for post_id, raw_text in posts:
                    try:
                        # Process the article text
                        processed_text = extract_article_text(raw_text, self.signature)
                        
                        if processed_text:
                            # Mark post as processed and store the processed text
                            mark_post_as_processed(post_id, processed_text)
                            self.logger.info(f"Successfully processed post {post_id}")
                        else:
                            # If no text could be extracted, delete the post
                            delete_post(post_id)
                            self.logger.info(f"Deleted post {post_id} due to no extractable text")
                            
                    except Exception as e:
                        self.logger.error(f"Error processing post {post_id}: {e}")
                        continue
                        
        except Exception as e:
            self.logger.error(f"Error in process cycle: {e}")
            raise
