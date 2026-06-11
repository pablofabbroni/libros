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

def log_download(ip_address: str, book_title: str, is_zip: bool = False):
    ip_hash = get_ip_hash(ip_address)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO downloads (ip_hash, book_title, is_zip) VALUES (?, ?, ?)", 
        (ip_hash, book_title, 1 if is_zip else 0)
    )
    conn.commit()
    conn.close()

def check_download_limit(ip_address: str, daily_limit: int = 10) -> int:
    """
    Returns the number of downloads left for this IP.
    """
    ip_hash = get_ip_hash(ip_address)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Count downloads in the last 24 hours
    twenty_four_hours_ago = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT COUNT(id) FROM downloads WHERE ip_hash = ? AND timestamp > ?", (ip_hash, twenty_four_hours_ago))
    downloads_count = cursor.fetchone()[0]
    conn.close()
    
    return max(0, daily_limit - downloads_count)

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Total visits
    cursor.execute("SELECT COUNT(id) FROM visits")
    total_visits = cursor.fetchone()[0]
    
    # Unique visitors (IP hashes)
    cursor.execute("SELECT COUNT(DISTINCT ip_hash) FROM visits")
    unique_visitors = cursor.fetchone()[0]
    
    # Total downloads
    cursor.execute("SELECT COUNT(id) FROM downloads")
    total_downloads = cursor.fetchone()[0]
    
    # Top 10 most downloaded books (excluding zip download tags if any, or aggregate them)
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
        'top_books': top_books
    }
