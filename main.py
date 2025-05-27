import logging
import signal
import sys
import threading
import os
from logging.handlers import TimedRotatingFileHandler

from infrastructure.config import load_config, get_monitored_subreddits, get_distinguished_subreddits
from infrastructure.database import init_db
from infrastructure.reddit import get_reddit_client, get_banned_domains
from threads.reddit_fetch import RedditFetchThread
from threads.reddit_post import RedditPostThread
from threads.newspaper_processor import NewspaperProcessorThread
from threads.newspaper_fetcher import NewspaperFetcherThread
from threads.cleanup_thread import CleanupThread

# ANSI color codes
class Colors:
    RESET = '\033[0m'
    WHITE = '\033[37m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RED = '\033[31m'

class CustomFormatter(logging.Formatter):
    def __init__(self):
        super().__init__()
        self.datefmt = '%Y-%m-%d %H:%M:%S'
        self.thread_colors = {
            'RedditFetchThread': Colors.BLUE,
            'NewspaperFetcherThread': Colors.MAGENTA,
            'NewspaperProcessorThread': Colors.CYAN,
            'RedditPostThread': Colors.GREEN,
            'CleanupThread': Colors.YELLOW,
            'main': Colors.WHITE,
        }
        self.level_colors = {
            'DEBUG': Colors.CYAN,
            'INFO': Colors.GREEN,
            'WARNING': Colors.YELLOW,
            'ERROR': Colors.RED,
            'CRITICAL': Colors.RED,
        }

    def format(self, record):
        timestamp = self.formatTime(record, self.datefmt)
        thread_color = self.thread_colors.get(record.name, Colors.WHITE)
        level_color = self.level_colors.get(record.levelname, Colors.WHITE)
        
        return (
            f"{Colors.WHITE}{timestamp}{Colors.RESET} - "
            f"{thread_color}{record.name}{Colors.RESET} - "
            f"{level_color}{record.levelname}{Colors.RESET} - "
            f"{Colors.WHITE}{record.getMessage()}{Colors.RESET}"
        )

# Configure logging
# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Create a rotating file handler that writes to a daily log file and deletes old logs
log_filename = "logs/bot.log"  # Base filename
file_handler = TimedRotatingFileHandler(
    filename=log_filename,
    when='midnight',  # Rotate at midnight
    interval=1,  # Every day
    backupCount=7,  # Keep 7 days of logs
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
file_handler.setLevel(logging.DEBUG)  # File handler will capture all logs

# Console handler with colors
console_handler = logging.StreamHandler()
console_handler.setFormatter(CustomFormatter())
console_handler.setLevel(logging.INFO)  # Console will only show INFO and above

# Create a logger for each thread type
def get_thread_logger(name):
    logger = logging.getLogger(name)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)  # Set root logger to DEBUG to capture all levels
    return logger

# Main logger
logger = get_thread_logger('main')

def signal_handler(signum, frame):
    logger.info("\nShutting down threads...")
    sys.exit(0)


def main():
    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded successfully!")
        logger.info(f"Bot username: {config['reddit']['username']}")
        
        # Initialize Reddit client
        reddit = get_reddit_client()
        logger.info("Reddit client initialized successfully!")
        
        # Get subreddits info
        monitored = get_monitored_subreddits()
        distinguished = get_distinguished_subreddits()
        logger.info(f"Monitoring {len(monitored)} subreddits")
        logger.info(f"Distinguished in {len(distinguished)} subreddits")
        
        # Initialize database and get db_path
        db_path = init_db()  # This will create the database and tables if they don't exist
        logger.info("Database initialized successfully!")
        
        # Create database lock
        db_lock = threading.Lock()
        
        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start threads
        logger.info("Starting worker threads...")
        fetch_thread = RedditFetchThread(
            reddit_client=reddit,
            db_path=db_path,
            db_lock=db_lock,
            logger=get_thread_logger('RedditFetchThread'),
            subreddits=monitored,
            banned_domains=get_banned_domains()
        )
        newspaper_fetcher_thread = NewspaperFetcherThread(
            db_path=db_path,
            db_lock=db_lock,
            logger=get_thread_logger('NewspaperFetcherThread')
        )
        processor_thread = NewspaperProcessorThread(
            db_path=db_path,
            db_lock=db_lock,
            logger=get_thread_logger('NewspaperProcessorThread')
        )
        post_thread = RedditPostThread(
            reddit=reddit,
            db_path=db_path,
            db_lock=db_lock,
            logger=get_thread_logger('RedditPostThread')
        )
        cleanup_thread = CleanupThread(
            db_path=db_path,
            db_lock=db_lock,
            logger=get_thread_logger('CleanupThread')
        )
        
        fetch_thread.start()
        newspaper_fetcher_thread.start()
        processor_thread.start()
        post_thread.start()
        cleanup_thread.start()
        
        # Keep main thread alive
        while True:
            signal.pause()
            
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
