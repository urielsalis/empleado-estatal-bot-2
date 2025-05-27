# Empleado Estatal Bot

A Reddit bot that monitors and processes posts from specified subreddits, extracts content from news articles, and posts it as comments.


## Installation

1. Clone the repository:
```bash
git clone https://github.com/urielsalis/empleado-estatal-bot-2.git
cd empleado-estatal-bot-2
```

2. Configure the bot:
   - Copy `config/config.example.yaml` to `config/config.yaml`
   - Fill in your Reddit API credentials
   - Configure subreddits and other settings

## Usage

Run the bot:
```bash
uv run main.py
```

## Development

### Running Tests
```bash
uv run pytest
```

See state machine in [POST_STATES.md](docs/POST_STATES.md)

