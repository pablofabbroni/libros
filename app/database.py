# -*- coding: utf-8 -*-
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "stats.db"))

def init_db():
    # Ensure directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table to track visits
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_hash TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        user_agent TEXT
    )
    """)
    
    # Table to track downloads
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS downloads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_hash TEXT NOT NULL,
        book_title TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_zip INTEGER DEFAULT 0
    )
    """)
    
    # Check if zip_id column exists, if not, add it
    cursor.execute("PRAGMA table_info(downloads)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'zip_id' not in columns:
        cursor.execute("ALTER TABLE downloads ADD COLUMN zip_id TEXT")
        
    # Table to track recommendations/votes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_hash TEXT NOT NULL,
        book_hash TEXT NOT NULL,
        vote_type INTEGER NOT NULL, -- 1 for thumbs up, -1 for thumbs down
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ip_hash, book_hash)
    )
    """)
    
    conn.commit()
    conn.close()

def get_ip_hash(ip_address: str) -> str:
    # Use simple SHA256 hashing to protect user privacy (GDPR compliance)
    return hashlib.sha256(ip_address.encode('utf-8')).hexdigest()

def log_visit(ip_address: str, user_agent: str = ""):
    ip_hash = get_ip_hash(ip_address)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Let's prevent double counting visits from the same IP within 1 hour
    one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT id FROM visits WHERE ip_hash = ? AND timestamp > ?", (ip_hash, one_hour_ago))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO visits (ip_hash, user_agent) VALUES (?, ?)", (ip_hash, user_agent))
        conn.commit()
    conn.close()

def log_download(ip_address: str, book_title: str, is_zip: bool = False, zip_id: str = None):
    ip_hash = get_ip_hash(ip_address)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO downloads (ip_hash, book_title, is_zip, zip_id) VALUES (?, ?, ?, ?)", 
        (ip_hash, book_title, 1 if is_zip else 0, zip_id)
    )
    conn.commit()
    conn.close()

def check_download_limits(ip_address: str, ind_limit: int = 10, zip_limit: int = 3) -> dict:
    """
    Returns the number of downloads left for this IP (individual and ZIP).
    """
    ip_hash = get_ip_hash(ip_address)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    twenty_four_hours_ago = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Count individual downloads (zip_id is null) in the last 24h
    cursor.execute("SELECT COUNT(id) FROM downloads WHERE ip_hash = ? AND timestamp > ? AND zip_id IS NULL", (ip_hash, twenty_four_hours_ago))
    ind_count = cursor.fetchone()[0]
    
    # Count unique ZIP downloads (distinct zip_id) in the last 24h
    cursor.execute("SELECT COUNT(DISTINCT zip_id) FROM downloads WHERE ip_hash = ? AND timestamp > ? AND zip_id IS NOT NULL", (ip_hash, twenty_four_hours_ago))
    zip_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'individual_left': max(0, ind_limit - ind_count),
        'individual_limit': ind_limit,
        'zip_left': max(0, zip_limit - zip_count),
        'zip_limit': zip_limit
    }

def check_download_limit(ip_address: str, daily_limit: int = 10) -> int:
    """
    Backward compatibility wrapper.
    """
    return check_download_limits(ip_address, daily_limit)['individual_left']

def cast_vote(ip_address: str, book_hash: str, vote_type: int):
    """
    Cast or change a vote.
    vote_type: 1 (recommend), -1 (dislike), 0 (remove vote)
    """
    ip_hash = get_ip_hash(ip_address)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if vote_type == 0:
        cursor.execute("DELETE FROM votes WHERE ip_hash = ? AND book_hash = ?", (ip_hash, book_hash))
    else:
        cursor.execute("""
            INSERT INTO votes (ip_hash, book_hash, vote_type) 
            VALUES (?, ?, ?)
            ON CONFLICT(ip_hash, book_hash) 
            DO UPDATE SET vote_type = excluded.vote_type
        """, (ip_hash, book_hash, vote_type))
        
    conn.commit()
    conn.close()

def get_all_votes(ip_address: str = None) -> dict:
    """
    Returns aggregated votes { book_hash: { likes: int, dislikes: int, user_vote: int } }
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Aggregated likes and dislikes
    cursor.execute("""
        SELECT book_hash,
               SUM(CASE WHEN vote_type = 1 THEN 1 ELSE 0 END) as likes,
               SUM(CASE WHEN vote_type = -1 THEN 1 ELSE 0 END) as dislikes
        FROM votes
        GROUP BY book_hash
    """)
    votes_dict = {}
    for row in cursor.fetchall():
        votes_dict[row[0]] = {
            'likes': row[1],
            'dislikes': row[2],
            'user_vote': 0
        }
        
    # Current user's votes
    if ip_address:
        ip_hash = get_ip_hash(ip_address)
        cursor.execute("SELECT book_hash, vote_type FROM votes WHERE ip_hash = ?", (ip_hash,))
        for row in cursor.fetchall():
            b_hash = row[0]
            v_type = row[1]
            if b_hash in votes_dict:
                votes_dict[b_hash]['user_vote'] = v_type
            else:
                votes_dict[b_hash] = {
                    'likes': 0,
                    'dislikes': 0,
                    'user_vote': v_type
                }
                
    conn.close()
    return votes_dict

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Total visits
    cursor.execute("SELECT COUNT(id) FROM visits")
    total_visits = cursor.fetchone()[0]
    
    # Unique visitors
    cursor.execute("SELECT COUNT(DISTINCT ip_hash) FROM visits")
    unique_visitors = cursor.fetchone()[0]
    
    # Total downloads (transactions: individual + unique zip_ids)
    cursor.execute("SELECT COUNT(id) FROM downloads WHERE zip_id IS NULL")
    ind_downloads = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT zip_id) FROM downloads WHERE zip_id IS NOT NULL")
    zip_downloads = cursor.fetchone()[0]
    
    total_downloads = ind_downloads + zip_downloads
    
    # Total books downloaded (all rows in downloads table)
    cursor.execute("SELECT COUNT(id) FROM downloads")
    total_books = cursor.fetchone()[0]
    
    # Top 10 most downloaded books
    cursor.execute("""
        SELECT book_title, COUNT(id) as dl_count 
        FROM downloads 
        GROUP BY book_title 
        ORDER BY dl_count DESC 
        LIMIT 10
    """)
    top_books = [{'title': row[0], 'count': row[1]} for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'total_visits': total_visits,
        'unique_visitors': unique_visitors,
        'total_downloads': total_downloads,
        'total_books': total_books,
        'top_books': top_books
    }

def get_book_download_counts() -> dict:
    """
    Returns a dictionary of book_title -> count of downloads.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT book_title, COUNT(id) FROM downloads GROUP BY book_title")
    counts = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return counts
