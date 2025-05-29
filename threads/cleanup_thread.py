import logging
from .base_thread import BaseThread
from infrastructure.database import cleanup_old_posts

logger = logging.getLogger(__name__)

class CleanupThread(BaseThread):
    def __init__(self, logger: logging.Logger):
        # Run cleanup every hour
        super().__init__(logger, interval=3600)
    
    def process_cycle(self):
        """Run the cleanup process."""
        cleanup_old_posts() 