import logging
import time
from typing import List
import praw
from utils.domain_utils import compile_domain_patterns, is_domain_banned
from infrastructure.database import insert_post, mark_post_as_skipped
from .base_thread import BaseThread

class RedditFetchThread(BaseThread):
    def __init__(
        self,
        reddit_client: praw.Reddit,
        logger: logging.Logger,
        subreddits: List[str],
        banned_domains: List[str],
        interval: int = 300
    ):
        super().__init__(logger, interval)
        self.reddit = reddit_client
        self.subreddits = subreddits
        self.banned_patterns = compile_domain_patterns(banned_domains)

    def is_domain_banned(self, url: str) -> bool:
        """Check if a URL's domain is in the banned list."""
        return is_domain_banned(url, self.banned_patterns)

    def process_cycle(self):
        """Process new submissions from Reddit."""
        
        # Join subreddits with + for multi-subreddit stream
        subreddit_str = "+".join(self.subreddits)
        subreddit = self.reddit.subreddit(subreddit_str)
        
        # Use PRAW's submission stream to monitor new submissions
        for submission in subreddit.stream.submissions(skip_existing=True):
            if self._stop_event.is_set():
                break
                
            try:
                # Calculate timestamp for 1 day ago
                one_day_ago = int(time.time()) - (24 * 60 * 60)

                # Skip if no URL
                if not submission.url:
                    continue
                    
                # Skip if domain is banned
                if self.is_domain_banned(submission.url):
                    self.logger.info(f"Skipping banned domain: {submission.url}")
                    mark_post_as_skipped()
                    continue
                
                # Skip if post is older than 1 day
                if submission.created_utc < one_day_ago:
                    self.logger.info(f"Skipping old post: {submission.id} (created {submission.created_utc})")
                    mark_post_as_skipped()
                    continue
                    
                # Insert post if it doesn't exist
                self.logger.info(f"Inserting post: {submission.id}")
                insert_post(
                    reddit_id=submission.id,
                    subreddit=submission.subreddit.display_name,
                    url=submission.url,
                    created_utc=int(submission.created_utc)
                )
                    
            except Exception as e:
                self.logger.error(f"Error processing submission {submission.id}: {str(e)}")
                continue
