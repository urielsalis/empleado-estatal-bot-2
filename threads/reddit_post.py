import time
import praw
import logging
from .base_thread import BaseThread
from infrastructure.config import load_config
from infrastructure.database import get_posts_to_post, mark_post_as_posted

class RedditPostThread(BaseThread):
    def __init__(self, reddit: praw.Reddit, logger: logging.Logger):
        super().__init__(logger)
        self.reddit = reddit
        self.config = load_config()
        self.max_length = self.config['newspaper_processor']['max_length']
        self.distinguishable_subreddits = self.config['reddit']['distinguishable']
        self.coverage_subreddits = self.config['newspaper_processor']['coverage']
    
    def split_text(self, text: str, subreddit: str) -> list[str]:
        """Split text into chunks that fit within Reddit's comment length limit."""
        if len(text) <= self.max_length:
            return [text]
            
        chunks = []
        continuation_msg = "\n> ***(continues in next comment)***"
        continuation_msg_len = len(continuation_msg)
        
        while text:
            # If remaining text is shorter than max_length, add it as the last chunk
            if len(text) <= self.max_length:
                chunks.append(text)
                break
                
            # Find the last newline before max_length - continuation_msg_len
            # to ensure we have room for the continuation message
            split_point = text.rfind('\n', 0, self.max_length - continuation_msg_len)
            
            # If no newline found, try to split at the last space
            if split_point == -1:
                split_point = text.rfind(' ', 0, self.max_length - continuation_msg_len)
                
            # If still no good split point, force split at max_length - continuation_msg_len
            if split_point == -1:
                split_point = self.max_length - continuation_msg_len
                
            # Add the chunk with continuation message and continue with remaining text
            chunk = text[:split_point].strip() + continuation_msg
            chunks.append(chunk)
            text = text[split_point:].strip()
            
        # Add CoverageAnalysisBot summoning to the last chunk if subreddit is in coverage list
        if subreddit in self.coverage_subreddits:
            chunks[-1] += "\n\nSummoning u/CoverageAnalysisBot"
            
        return chunks
    
    def process_cycle(self):
        """Process and post content to Reddit."""
        try:
            # Get posts that have been processed but not posted yet
            posts = get_posts_to_post()
            
            for post_id, reddit_id, subreddit, processed_text in posts:
                try:
                    self.logger.info(f"Found post to comment on: {reddit_id} in r/{subreddit}")
                    
                    # Split the text into chunks
                    text_chunks = self.split_text(processed_text, subreddit)
                    self.logger.info(f"Split text into {len(text_chunks)} chunks")
                    
                    # Get the Reddit submission
                    submission = self.reddit.submission(id=reddit_id)
                    
                    # Post the first comment
                    current_comment = submission.reply(text_chunks[0])
                    self.logger.info(f"Posted first comment on submission {reddit_id}")
                    
                    # Pin the first comment if the subreddit is in the distinguishable list
                    if subreddit in self.distinguishable_subreddits:
                        try:
                            current_comment.mod.distinguish(sticky=True)
                            self.logger.info(f"Pinned first comment on submission {reddit_id}")
                        except Exception as e:
                            self.logger.error(f"Failed to pin comment on submission {reddit_id}: {e}")
                    
                    # If there are more chunks, post them as replies to the previous comment
                    for chunk in text_chunks[1:]:
                        current_comment = current_comment.reply(chunk)
                        self.logger.info(f"Posted continuation comment on submission {reddit_id}")
                        # Add a small delay between comments to avoid rate limiting
                        time.sleep(2)
                    
                    # Mark the post as posted
                    mark_post_as_posted(post_id)
                    self.logger.info(f"Successfully marked post {post_id} as posted")
                    
                except Exception as e:
                    self.logger.error(f"Error processing post {post_id}: {e}")
                    continue
        except Exception as e:
            self.logger.error(f"Error in post cycle: {e}")
            raise
