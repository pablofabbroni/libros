# -*- coding: utf-8 -*-
import os
import re
import unicodedata
import hashlib
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("books_manager")

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    logger.warning("fitz (PyMuPDF) is not installed. PDF covers cannot be extracted.")

# Environment configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOOKS_DIR = os.environ.get("BOOKS_DIR", "app/books")
COVERS_DIR = os.environ.get("COVERS_DIR", os.path.join(BASE_DIR, "static", "covers"))

def normalize(text):
    if not text:
        return ""
    text = text.lower()
    # Remove accents/diacritics
    text = "".join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    # Remove special characters
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    # Remove extra spaces
    text = " ".join(text.split())
    return text

def parse_filename(filename):
    """
    Parses filename to extract Title and Author.
    Example: "Antes de renunciar a tu empleo - Robert Kiyosaki.pdf"
    """
    name_no_ext = os.path.splitext(filename)[0]
    # Remove numbered prefixes like "010-", "010 ", "129_", etc.
    name_no_ext = re.sub(r"^\d+[-_\s]+", "", name_no_ext).strip()
    
    # Split title and author by hyphen
    if " - " in name_no_ext:
        parts = name_no_ext.split(" - ")
        title = parts[0].strip()
        author = parts[1].strip()
    elif "-" in name_no_ext:
        parts = name_no_ext.split("-")
        if len(parts) == 2:
            title = parts[0].strip()
            author = parts[1].strip()
        else:
            title = name_no_ext
            author = ""
    else:
        title = name_no_ext
        author = ""
        
    # Formatting cleanups
    author = author.replace("_", " & ").replace("-", " & ")
    author = re.sub(r"\s+", " ", author).strip()
    author = re.sub(r"(?i)\s+copia.*", "", author).strip()
    title = re.sub(r"(?i)\s+copia.*", "", title).strip()
    
    # Title corrections
    if title.lower() == "100eu startup !ponte en marcha!":
        title = "100€ Startup ¡Ponte en marcha!"
    elif title.lower() == "7riquezas":
        title = "7 Riquezas"
    elif title.lower() == "20conceptos":
        title = "20 Conceptos"
        
    # Title capitalization
    def title_case(s):
        if not s:
            return ""
        words = s.split()
        res = []
        for w in words:
            if w.upper() in ['MBA', 'ABC', 'A4', 'SEO', 'PC', 'CEO']:
                res.append(w.upper())
            elif w.lower() in ['de', 'la', 'el', 'en', 'y', 'un', 'una', 'los', 'las', 'del', 'para', 'con', 'por', 'sobre', 'al', 'se', 'su', 'sus', 'e', 'o']:
                res.append(w.lower())
            else:
                res.append(w.capitalize())
        if res:
            res[0] = res[0].capitalize()
        return " ".join(res)
        
    title = title_case(title)
    author = title_case(author)
    
    if not author:
        author = "Varios Autores"
        
    return title, author

def get_file_md5(filename):
    return hashlib.md5(filename.encode('utf-8')).hexdigest()

def extract_pdf_cover(pdf_path, cover_path):
    if not fitz:
        return False
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count > 0:
            page = doc.load_page(0) # First page
            # Render page to low-resolution pixmap (100 DPI is enough for card thumbnails)
            pix = page.get_pixmap(dpi=100)
            pix.save(cover_path)
            doc.close()
            return True
        doc.close()
    except Exception as e:
        logger.error(f"Failed to extract cover for {pdf_path}: {e}")
    return False

def scan_books_folder():
    """
    Scans the BOOKS_DIR directory, filters out duplicate files,
    creates covers for unique PDFs, and returns the sorted books index list.
    """
    if not os.path.exists(BOOKS_DIR):
        logger.error(f"Books directory '{BOOKS_DIR}' does not exist!")
        return []
        
    if not os.path.exists(COVERS_DIR):
        os.makedirs(COVERS_DIR)
        
    all_files = os.listdir(BOOKS_DIR)
    
    # Filter only PDF files, excluding temporary or hidden files (like Mac ._ files)
    pdf_files = [
        f for f in all_files 
        if f.lower().endswith('.pdf') and not f.startswith('._') and not f.startswith('.')
    ]
    
    # Group by normalized title to detect and eliminate duplicate copies
    groups = {} # norm_title -> list of (filename, file_size)
    
    for f in pdf_files:
        path = os.path.join(BOOKS_DIR, f)
        title, _ = parse_filename(f)
        norm_title = normalize(title)
        
        if not norm_title:
            continue
            
        if norm_title not in groups:
            groups[norm_title] = []
        groups[norm_title].append((f, os.path.getsize(path)))
        
    unique_books = []
    
    for norm_title, file_list in groups.items():
        # Pick the best file from duplicates group:
        # 1. Prefer files without "copia" in filename
        # 2. Prefer files with larger file size (likely complete / higher quality)
        # 3. Alphabetically first as fallback
        
        file_list.sort(key=lambda x: (
            "copia" in x[0].lower(), # False comes first (0 < 1)
            -x[1],                   # Largest size first
            x[0].lower()             # Alphabetical fallback
        ))
        
        best_filename = file_list[0][0]
        pdf_path = os.path.join(BOOKS_DIR, best_filename)
        title, author = parse_filename(best_filename)
        
        # Cover filename using MD5 hash of filename to prevent path character bugs
        cover_hash = get_file_md5(best_filename)
        cover_name = f"{cover_hash}.png"
        cover_path = os.path.join(COVERS_DIR, cover_name)
        
        # Extract cover if not already cached
        has_cover = False
        if os.path.exists(cover_path):
            has_cover = True
        else:
            if extract_pdf_cover(pdf_path, cover_path):
                has_cover = True
                logger.info(f"Extracted cover preview for: {best_filename}")
                
        cover_url = f"/static/covers/{cover_name}" if has_cover else "/static/placeholder.png"
        
        unique_books.append({
            'filename': best_filename,
            'title': title,
            'author': author,
            'cover_url': cover_url,
            'size_bytes': os.path.getsize(pdf_path)
        })
        
    # Sort books alphabetically by title
    unique_books.sort(key=lambda x: x['title'].lower())
    logger.info(f"Indexed {len(unique_books)} unique books (filtered out {len(pdf_files) - len(unique_books)} duplicates).")
    return unique_books
