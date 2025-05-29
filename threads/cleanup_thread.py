import threading
import logging
from .base_thread import BaseThread
from infrastructure.database import cleanup_old_posts

logger = logging.getLogger(__name__)

class CleanupThread(BaseThread):
    def __init__(self, db_path: str, db_lock: threading.Lock, logger: logging.Logger):
        # Run cleanup every hour
        super().__init__(db_path, db_lock, logger, interval=3600)
    
    def process_cycle(self, conn):
        """Run the cleanup process."""
        with self.db_lock:
            cleanup_old_posts(conn) 