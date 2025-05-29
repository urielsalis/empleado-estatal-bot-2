#!/usr/bin/env python3
import argparse
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
import json
import logging
from infrastructure.database import get_db_connection

logger = logging.getLogger(__name__)

def get_post_stats(db_path: str) -> Dict[str, Any]:
    """Get statistics about posts in the database."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        
        # Get all stats from post_stats table
        cursor.execute("""
            SELECT stat_name, stat_value, last_updated_utc
            FROM post_stats
        """)
        stats = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get raw text vs processed text count
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN raw_text IS NOT NULL THEN 1 ELSE 0 END) as raw_text_count,
                SUM(CASE WHEN text IS NOT NULL THEN 1 ELSE 0 END) as processed_text_count
            FROM texts
        """)
        raw_text_count, processed_text_count = cursor.fetchone()
        
        # Convert timestamps to human-readable format
        oldest_date = datetime.fromtimestamp(stats['oldest_post'], tz=timezone.utc) if stats['oldest_post'] else None
        newest_date = datetime.fromtimestamp(stats['newest_post'], tz=timezone.utc) if stats['newest_post'] else None
        
        return {
            "total_posts": stats['total_posts'],
            "states": {
                "fetched": {
                    "count": stats['posts_fetched'],
                    "pending": stats['total_posts'] - stats['posts_fetched']
                },
                "processed": {
                    "count": stats['posts_processed'],
                    "pending": stats['posts_fetched'] - stats['posts_processed']
                },
                "posted": {
                    "count": stats['posts_posted'],
                    "pending": stats['posts_processed'] - stats['posts_posted']
                },
                "texts": {
                    "raw": raw_text_count or 0,
                    "processed": processed_text_count or 0
                }
            },
            "timestamps": {
                "oldest_post": oldest_date.isoformat() if oldest_date else None,
                "newest_post": newest_date.isoformat() if newest_date else None
            }
        }
    finally:
        conn.close()

def get_post_text(db_path: str, post_id: Optional[int] = None, reddit_id: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """Get the raw and processed text of a post by ID or Reddit ID."""
    if not post_id and not reddit_id:
        raise ValueError("Either post_id or reddit_id must be provided")
        
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        
        if post_id:
            cursor.execute("""
                SELECT t.raw_text, t.text
                FROM texts t
                JOIN posts p ON t.post_id = p.id
                WHERE p.id = ?
            """, (post_id,))
        else:
            cursor.execute("""
                SELECT t.raw_text, t.text
                FROM texts t
                JOIN posts p ON t.post_id = p.id
                WHERE p.reddit_id = ?
            """, (reddit_id,))
            
        result = cursor.fetchone()
        if result:
            return result
        return None
    finally:
        conn.close()

def list_posts(db_path: str, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Dict[str, Any]]:
    """List all posts in the database with their IDs and metadata."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        
        # Build the query with optional limit and offset
        query = """
            SELECT 
                p.id,
                p.reddit_id,
                p.subreddit,
                p.url,
                p.created_utc,
                p.fetched_at_utc,
                p.fetch_at_utc,
                p.processed_at_utc,
                p.posted_at_utc,
                CASE WHEN t.raw_text IS NOT NULL THEN 1 ELSE 0 END as has_raw_text,
                CASE WHEN t.text IS NOT NULL THEN 1 ELSE 0 END as has_processed_text
            FROM posts p
            LEFT JOIN texts t ON p.id = t.post_id
            ORDER BY p.id DESC
        """
        
        params = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        if offset is not None:
            query += " OFFSET ?"
            params.append(offset)
            
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Convert rows to list of dictionaries
        posts = []
        for row in rows:
            post = {
                "id": row[0],
                "reddit_id": row[1],
                "subreddit": row[2],
                "url": row[3],
                "created_at": datetime.fromtimestamp(row[4], tz=timezone.utc).isoformat() if row[4] else None,
                "fetched_at": datetime.fromtimestamp(row[5], tz=timezone.utc).isoformat() if row[5] else None,
                "fetch_at": datetime.fromtimestamp(row[6], tz=timezone.utc).isoformat() if row[6] else None,
                "processed_at": datetime.fromtimestamp(row[7], tz=timezone.utc).isoformat() if row[7] else None,
                "posted_at": datetime.fromtimestamp(row[8], tz=timezone.utc).isoformat() if row[8] else None,
                "has_raw_text": bool(row[9]),
                "has_processed_text": bool(row[10])
            }
            posts.append(post)
            
        return posts
    finally:
        conn.close()

def reset_processed_at(db_path: str, post_id: Optional[int] = None, reddit_id: Optional[str] = None) -> bool:
    """Reset the processed_at_utc field for a specific post."""
    if not post_id and not reddit_id:
        raise ValueError("Either post_id or reddit_id must be provided")
        
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        
        if post_id:
            cursor.execute("""
                UPDATE posts 
                SET processed_at_utc = NULL
                WHERE id = ?
            """, (post_id,))
        else:
            cursor.execute("""
                UPDATE posts 
                SET processed_at_utc = NULL
                WHERE reddit_id = ?
            """, (reddit_id,))
            
        if cursor.rowcount == 0:
            return False
            
        conn.commit()
        return True
    finally:
        conn.close()

def reset_to_processed(db_path: str, post_id: Optional[int] = None, reddit_id: Optional[str] = None) -> bool:
    """Reset a post's state to processed but not posted by setting processed_at_utc to current time and clearing posted_at_utc."""
    if not post_id and not reddit_id:
        raise ValueError("Either post_id or reddit_id must be provided")
        
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        current_time = int(datetime.now(timezone.utc).timestamp())
        
        if post_id:
            cursor.execute("""
                UPDATE posts 
                SET processed_at_utc = ?,
                    posted_at_utc = NULL
                WHERE id = ?
            """, (current_time, post_id))
        else:
            cursor.execute("""
                UPDATE posts 
                SET processed_at_utc = ?,
                    posted_at_utc = NULL
                WHERE reddit_id = ?
            """, (current_time, reddit_id))
            
        if cursor.rowcount == 0:
            return False
            
        conn.commit()
        return True
    finally:
        conn.close()

def reset_post_state(db_path: str, post_id: Optional[int] = None, reddit_id: Optional[str] = None) -> bool:
    """Reset all default null fields and text fields for a post to their initial state."""
    if not post_id and not reddit_id:
        raise ValueError("Either post_id or reddit_id must be provided")
        
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        
        # First, get the post ID if we only have the reddit_id
        if reddit_id:
            cursor.execute("SELECT id FROM posts WHERE reddit_id = ?", (reddit_id,))
            result = cursor.fetchone()
            if not result:
                return False
            post_id = result[0]
        
        # Reset all timestamp fields to NULL
        cursor.execute("""
            UPDATE posts 
            SET fetched_at_utc = NULL,
                processed_at_utc = NULL,
                posted_at_utc = NULL
            WHERE id = ?
        """, (post_id,))
        
        # Delete any associated text entries
        cursor.execute("DELETE FROM texts WHERE post_id = ?", (post_id,))
            
        conn.commit()
        return True
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Tools for managing the bot's database")
    parser.add_argument("command", choices=["stats", "get-text", "list", "reset-processed", "reset-to-processed", "reset-post-state"],
                      help="Command to execute")
    parser.add_argument("--id", type=int, help="Post ID")
    parser.add_argument("--reddit-id", help="Reddit post ID")
    parser.add_argument("--limit", type=int, help="Limit number of results (for list command)")
    parser.add_argument("--offset", type=int, help="Offset for results (for list command)")
    parser.add_argument("--db", help="Path to the database file (default: data/bot.db)")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--raw", action="store_true", help="Show only raw text")
    parser.add_argument("--processed", action="store_true", help="Show only processed text")
    parser.add_argument("--compact", action="store_true", help="Show compact output (ID, Reddit ID, URL only)")
    
    args = parser.parse_args()
    
    # Determine database path
    db_path = args.db or os.path.join("data", "bot.db")
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return 1
    
    if args.command == "stats":
        # Get and display stats
        stats = get_post_stats(db_path)
        
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(f"Total Posts: {stats['total_posts']}")
            print("\nPost States:")
            print(f"  Fetched:    {stats['states']['fetched']['count']} (pending: {stats['states']['fetched']['pending']})")
            print(f"  Processed:  {stats['states']['processed']['count']} (pending: {stats['states']['processed']['pending']})")
            print(f"  Posted:     {stats['states']['posted']['count']} (pending: {stats['states']['posted']['pending']})")
            print("\nText States:")
            print(f"  Raw Text:      {stats['states']['texts']['raw']}")
            print(f"  Processed Text: {stats['states']['texts']['processed']}")
            print("\nTimestamps:")
            if stats['timestamps']['oldest_post']:
                print(f"  Oldest Post: {stats['timestamps']['oldest_post']}")
            if stats['timestamps']['newest_post']:
                print(f"  Newest Post: {stats['timestamps']['newest_post']}")
    
    elif args.command == "get-text":
        if not args.id and not args.reddit_id:
            print("Error: Either --id or --reddit-id must be provided")
            return 1
            
        text = get_post_text(db_path, args.id, args.reddit_id)
        if not text:
            print("Error: Post not found")
            return 1
            
        raw_text, processed_text = text
        
        if args.raw and args.processed:
            print("Error: Cannot specify both --raw and --processed")
            return 1
            
        if args.raw:
            print("Raw Text:")
            print(raw_text)
        elif args.processed:
            print("Processed Text:")
            print(processed_text)
        else:
            print("Raw Text:")
            print(raw_text)
            print("\nProcessed Text:")
            print(processed_text)
    
    elif args.command == "list":
        posts = list_posts(db_path, args.limit, args.offset)
        
        if args.json:
            print(json.dumps(posts, indent=2))
        elif args.compact:
            for post in posts:
                print(f"{post['id']}\t{post['reddit_id']}\t{post['url']}")
        else:
            for post in posts:
                print(f"\nPost ID: {post['id']}")
                print(f"Reddit ID: {post['reddit_id']}")
                print(f"Subreddit: {post['subreddit']}")
                print(f"URL: {post['url']}")
                print(f"Created: {post['created_at']}")
                print(f"Fetched: {post['fetched_at']}")
                print(f"Fetch: {post['fetch_at']}")
                print(f"Processed: {post['processed_at']}")
                print(f"Posted: {post['posted_at']}")
                print(f"Has Raw Text: {post['has_raw_text']}")
                print(f"Has Processed Text: {post['has_processed_text']}")
    
    elif args.command == "reset-processed":
        if not args.id and not args.reddit_id:
            print("Error: Either --id or --reddit-id must be provided")
            return 1
            
        success = reset_processed_at(db_path, args.id, args.reddit_id)
        if not success:
            print("Error: Post not found")
            return 1
            
        print("Successfully reset processed_at_utc")
    
    elif args.command == "reset-to-processed":
        if not args.id and not args.reddit_id:
            print("Error: Either --id or --reddit-id must be provided")
            return 1
            
        success = reset_to_processed(db_path, args.id, args.reddit_id)
        if not success:
            print("Error: Post not found")
            return 1
            
        print("Successfully reset post to processed state")
    
    elif args.command == "reset-post-state":
        if not args.id and not args.reddit_id:
            print("Error: Either --id or --reddit-id must be provided")
            return 1
            
        success = reset_post_state(db_path, args.id, args.reddit_id)
        if not success:
            print("Error: Post not found")
            return 1
            
        print("Successfully reset post state")
    
    else:
        parser.print_help()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 