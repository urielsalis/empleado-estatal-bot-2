import threading
import time
import logging
from abc import ABC, abstractmethod
from infrastructure.database import get_db_connection

class BaseThread(threading.Thread, ABC):
    def __init__(
        self,
        db_path: str,
        db_lock: threading.Lock,
        logger: logging.Logger,
        interval: int = 60,
        error_interval: int = 60
    ):
        super().__init__()
        self.daemon = True  # Thread will exit when main program exits
        self._stop_event = threading.Event()
        self.db_path = db_path
        self.db_lock = db_lock
        self.interval = interval
        self.error_interval = error_interval
        self.conn = None
        self.logger = logger

    def stop(self):
        """Stop the thread gracefully."""
        self._stop_event.set()

    @abstractmethod
    def process_cycle(self) -> None:
        """Implement the main processing logic for each cycle."""
        pass

    def run(self):
        """Main thread loop that handles the common thread lifecycle."""
        self.logger.info("Starting thread")
        
        # Create database connection once at thread start
        self.conn = get_db_connection(self.db_path)
        
        try:
            while not self._stop_event.is_set():
                try:
                    self.logger.debug("Starting processing cycle...")
                    self.process_cycle()
                    self.logger.debug("Processing cycle completed")
                    time.sleep(self.interval)
                except Exception as e:
                    self.logger.error(f"Error: {e}")
                    time.sleep(self.error_interval)
        finally:
            if self.conn:
                self.conn.close()
            self.logger.info("Thread stopped") 