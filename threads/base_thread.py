import threading
import time
import logging
from abc import ABC, abstractmethod
from infrastructure.database import close_db_connection

class BaseThread(threading.Thread, ABC):
    def __init__(
        self,
        logger: logging.Logger,
        interval: int = 60,
        error_interval: int = 60
    ):
        super().__init__()
        self.daemon = True  # Thread will exit when main program exits
        self._stop_event = threading.Event()
        self.interval = interval
        self.error_interval = error_interval
        self.logger = logger

    def stop(self):
        """Stop the thread gracefully."""
        self._stop_event.set()
        close_db_connection()

    @abstractmethod
    def process_cycle(self) -> None:
        """Implement the main processing logic for each cycle."""
        pass

    def run(self):
        """Main thread loop that handles the common thread lifecycle."""
        self.logger.info("Starting thread")
        
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
            close_db_connection()
            self.logger.info("Thread stopped") 