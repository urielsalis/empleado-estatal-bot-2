import logging
import time
from curl_cffi import requests
from .base_thread import BaseThread
from infrastructure.database import (
    get_posts_to_fetch, 
    mark_post_as_fetched, 
    handle_fetch_retry
)

class NewspaperFetcherThread(BaseThread):
    def __init__(self, logger: logging.Logger):
        super().__init__(logger)
    
    def process_cycle(self):
        """Fetch and process newspaper articles."""
        try:
            # Get posts that are ready to be fetched
            posts = get_posts_to_fetch()
            if posts:
                self.logger.info(f"Found {len(posts)} posts ready to fetch")
                
                for post_id, url in posts:
                    try:
                        # Fetch the article
                        self.logger.info(f"Fetching article from {url}")

                        response = requests.get(url, impersonate="chrome", timeout=10)
                        if response.status_code != 200:
                            self.logger.error(f"Failed to fetch {url}: {response.status_code}")
                            # Calculate retry time: 5 minutes * (2 ^ retry_count)
                            retry_time = int(time.time()) + (300 * (2 ** 0))  # Start with 5 minutes
                            if handle_fetch_retry(post_id, retry_time):
                                self.logger.info(f"Post {post_id} was skipped due to max retries")
                            continue
                            
                        # Store the raw text
                        raw_text = response.text
                        mark_post_as_fetched(post_id, raw_text)
                        
                        
                    except Exception as e:
                        self.logger.error(f"Error processing {url}: {e}")
                        # Calculate retry time: 5 minutes * (2 ^ retry_count)
                        retry_time = int(time.time()) + (300 * (2 ** 0))  # Start with 5 minutes
                        if handle_fetch_retry(post_id, retry_time):
                            self.logger.info(f"Post {post_id} was skipped due to max retries")
                        continue
                        
        except Exception as e:
            self.logger.error(f"Error in fetch cycle: {e}")
            raise 