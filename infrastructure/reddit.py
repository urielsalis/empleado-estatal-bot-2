import praw
from infrastructure.config import load_config


def get_reddit_client() -> praw.Reddit:
    """Initialize and return an authenticated Reddit client."""
    config = load_config()
    reddit_config = config['reddit']
    
    return praw.Reddit(
        client_id=reddit_config['client_id'],
        client_secret=reddit_config['secret_key'],
        username=reddit_config['username'],
        password=reddit_config['password'],
        user_agent="python:empleado-estatal-bot:v2.0.0 (by /u/urielsalis)"
    )


def get_subreddits() -> list[str]:
    """Get list of subreddits to monitor from config."""
    config = load_config()
    return config['reddit']['subreddits']


def get_banned_domains() -> list[str]:
    """Get list of banned domains from config."""
    config = load_config()
    return config['reddit']['banned_domains'] 