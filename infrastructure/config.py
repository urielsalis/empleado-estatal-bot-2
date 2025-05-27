import yaml
from pathlib import Path


def load_config() -> dict:
    """Load configuration from config.yml file."""
    config_path = Path("config/config.yml")
    if not config_path.exists():
        raise FileNotFoundError("config/config.yml not found in the config directory")
    
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_monitored_subreddits() -> list[str]:
    """Get list of all subreddits being monitored."""
    config = load_config()
    return config['reddit']['subreddits']


def get_distinguished_subreddits() -> list[str]:
    """Get list of subreddits where the bot is distinguished."""
    config = load_config()
    return config['reddit']['distinguishable'] 