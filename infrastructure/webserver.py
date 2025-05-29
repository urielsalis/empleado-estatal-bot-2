import time
from typing import Dict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import uvicorn
import threading
from pathlib import Path
import logging

from infrastructure.database import get_db_connection
from infrastructure.config import get_monitored_subreddits, get_distinguished_subreddits

app = FastAPI(title="Bot Stats Dashboard")
templates = Jinja2Templates(directory="templates")

# Cache for stats
stats_cache: Dict[str, int] = {}
last_cache_update = 0
CACHE_TTL = 60  # 1 minute

logger = logging.getLogger(__name__)

def get_stats_from_db() -> Dict[str, int]:
    """Get current stats from the database."""
    db_path = Path("data/bot.db")
    if not db_path.exists():
        return {}
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get basic stats
    cursor.execute("SELECT stat_name, stat_value FROM post_stats")
    stats = dict(cursor.fetchall())
    
    # Get remaining posts to fetch
    cursor.execute("""
        SELECT COUNT(*) 
        FROM posts 
        WHERE fetched_at_utc IS NULL
    """)
    stats['remaining_to_fetch'] = cursor.fetchone()[0]
    
    # Calculate remaining posts to process
    cursor.execute("""
        SELECT COUNT(*) 
        FROM posts 
        WHERE fetched_at_utc IS NOT NULL 
        AND processed_at_utc IS NULL
    """)
    stats['remaining_to_process'] = cursor.fetchone()[0]
    
    # Calculate remaining posts to post
    cursor.execute("""
        SELECT COUNT(*) 
        FROM posts 
        WHERE processed_at_utc IS NOT NULL 
        AND posted_at_utc IS NULL
    """)
    stats['remaining_to_post'] = cursor.fetchone()[0]
    
    # Calculate skipped posts (posts that were fetched but not processed)
    cursor.execute("""
        SELECT COUNT(*) 
        FROM posts 
        WHERE fetched_at_utc IS NOT NULL 
        AND processed_at_utc IS NULL 
        AND retry_count >= 3
    """)
    stats['remaining_skipped'] = cursor.fetchone()[0]
    
    return stats

def update_cache():
    """Update the stats cache periodically."""
    global stats_cache, last_cache_update
    while True:
        try:
            stats_cache = get_stats_from_db()
            last_cache_update = time.time()
        except Exception as e:
            logger.error(f"Error updating stats cache: {e}")
        time.sleep(CACHE_TTL)

@app.get("/", response_class=HTMLResponse)
async def stats_page(request: Request):
    """Render the stats dashboard."""
    global stats_cache, last_cache_update
    
    try:
        # Update cache if it's expired
        if time.time() - last_cache_update > CACHE_TTL:
            stats_cache = get_stats_from_db()
            last_cache_update = time.time()
        
        # Create a copy of stats for display
        display_stats = stats_cache.copy()
        
        # Format timestamps
        if 'oldest_post' in display_stats and display_stats['oldest_post']:
            try:
                display_stats['oldest_post'] = time.strftime(
                    '%Y-%m-%d %H:%M:%S', 
                    time.localtime(int(display_stats['oldest_post']))
                )
            except (ValueError, TypeError):
                display_stats['oldest_post'] = 'N/A'
                
        if 'newest_post' in display_stats and display_stats['newest_post']:
            try:
                display_stats['newest_post'] = time.strftime(
                    '%Y-%m-%d %H:%M:%S', 
                    time.localtime(int(display_stats['newest_post']))
                )
            except (ValueError, TypeError):
                display_stats['newest_post'] = 'N/A'
        
        # Get subreddit information
        monitored_subreddits = get_monitored_subreddits()
        distinguished_subreddits = get_distinguished_subreddits()
        
        return templates.TemplateResponse(
            "stats.html",
            {
                "request": request,
                "stats": display_stats,
                "last_update": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_cache_update)),
                "monitored_subreddits": monitored_subreddits,
                "distinguished_subreddits": distinguished_subreddits
            }
        )
    except Exception as e:
        logger.error(f"Error rendering stats page: {e}")
        return HTMLResponse(
            content="<html><body><h1>Error Loading Stats</h1><p>Please try again later.</p></body></html>",
            status_code=500
        )

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    """Redirect all 404s to the main page."""
    return RedirectResponse(url="/")

@app.exception_handler(500)
async def custom_500_handler(request: Request, exc: HTTPException):
    """Handle 500 errors gracefully."""
    return HTMLResponse(
        content="<html><body><h1>Internal Server Error</h1><p>Please try again later.</p></body></html>",
        status_code=500
    )

def start_webserver(host: str = "0.0.0.0", port: int = 8000):
    """Start the webserver in a separate thread."""
    # Start cache update thread
    cache_thread = threading.Thread(target=update_cache, daemon=True)
    cache_thread.start()
    
    # Configure uvicorn with security settings
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="error",  # Reduce logging
        access_log=False,   # Disable access logs
        proxy_headers=True, # Handle proxy headers properly
        forwarded_allow_ips="*",  # Allow forwarded headers from any IP
        server_header=False,      # Remove server header
        date_header=False,        # Remove date header
    )
    
    # Start the webserver
    server = uvicorn.Server(config)
    server.run() 