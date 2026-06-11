# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException, Request, Query, BackgroundTasks, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import zipfile
import tempfile
import hashlib
import logging
from typing import List

import uuid
from database import init_db, log_visit, log_download, check_download_limits, get_stats, cast_vote, get_all_votes, get_book_download_counts
from books_manager import scan_books_folder, get_file_md5, BOOKS_DIR

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="RobotEdge Digital Library API", version="1.0")

# CORS middleware for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables/cache
books_cache = []
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "RobotEdge2026")
DOWNLOAD_LIMIT_DAILY = int(os.environ.get("DOWNLOAD_LIMIT_DAILY", "10"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Calculate admin token hash on startup
ADMIN_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode('utf-8')).hexdigest()

@app.on_event("startup")
async def startup_event():
    global books_cache
    logger.info("Initializing database...")
    init_db()
    
    logger.info("Scanning books directory and extracting cover previews...")
    books_cache = scan_books_folder()
    
    # Generate placeholder image if it doesn't exist
    placeholder_path = os.path.join(STATIC_DIR, "placeholder.png")
    if not os.path.exists(STATIC_DIR):
        os.makedirs(STATIC_DIR)
    if not os.path.exists(placeholder_path):
        # Create a small blank PNG as placeholder
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (150, 220), color='#0f172a')
            d = ImageDraw.Draw(img)
            d.text((20, 100), "Sin Portada", fill="#4b5563")
            img.save(placeholder_path)
        except Exception:
            # Fallback: create empty file
            with open(placeholder_path, 'wb') as f:
                f.write(b'')

# Helper to verify admin credentials
def get_client_ip(request: Request) -> str:
    # Handle reverse proxies like Cloudflare, Nginx, Hostinger load balancers
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

# Endpoints
@app.get("/api/books")
async def get_books(request: Request, refresh: bool = False):
    global books_cache
    if refresh:
        logger.info("Re-scanning books folder...")
        books_cache = scan_books_folder()
    
    # Get recommendation votes and download counts for the current IP
    ip = get_client_ip(request)
    votes = get_all_votes(ip)
    download_counts = get_book_download_counts()
    
    # Map cache items to expose hash, title, author, cover_url, size, votes, and downloads
    response_books = []
    for b in books_cache:
        book_hash = get_file_md5(b['filename'])
        book_votes = votes.get(book_hash, {'likes': 0, 'dislikes': 0, 'user_vote': 0})
        book_downloads = download_counts.get(b['title'], 0)
        response_books.append({
            'hash': book_hash,
            'title': b['title'],
            'author': b['author'],
            'cover_url': b['cover_url'],
            'size_mb': round(b['size_bytes'] / (1024 * 1024), 2),
            'likes': book_votes['likes'],
            'dislikes': book_votes['dislikes'],
            'user_vote': book_votes['user_vote'],
            'downloads': book_downloads
        })
    return response_books

@app.post("/api/books/{hash}/vote")
async def vote_book(hash: str, payload: dict, request: Request):
    vote_type = payload.get("vote_type")
    if vote_type not in [1, -1, 0]:
        raise HTTPException(status_code=400, detail="Voto inválido. Debe ser 1, -1 o 0.")
        
    ip = get_client_ip(request)
    cast_vote(ip, hash, vote_type)
    
    # Return updated vote stats for this book
    votes = get_all_votes(ip)
    book_votes = votes.get(hash, {'likes': 0, 'dislikes': 0, 'user_vote': 0})
    return {
        'success': True,
        'likes': book_votes['likes'],
        'dislikes': book_votes['dislikes'],
        'user_vote': book_votes['user_vote']
    }

@app.get("/api/download/status")
async def get_download_status(request: Request):
    ip = get_client_ip(request)
    limits = check_download_limits(ip, ind_limit=10, zip_limit=3)
    return {
        'limits': limits,
        'ip_address': ip
    }

@app.get("/api/download")
async def download_books(
    request: Request,
    background_tasks: BackgroundTasks,
    hashes: str = Query(..., description="Comma-separated book hashes to download")
):
    ip = get_client_ip(request)
    
    # Parse requested hashes
    hash_list = [h.strip() for h in hashes.split(",") if h.strip()]
    if not hash_list:
        raise HTTPException(status_code=400, detail="No se especificaron libros para descargar")
        
    # Match hashes against books in cache
    books_to_download = []
    for h in hash_list:
        matched_book = next((b for b in books_cache if get_file_md5(b['filename']) == h), None)
        if matched_book:
            books_to_download.append(matched_book)
            
    if not books_to_download:
        raise HTTPException(status_code=404, detail="Ninguno de los libros seleccionados fue encontrado")
        
    # Download single book (Individual Mode)
    if len(books_to_download) == 1:
        # Check individual rate limit
        limits = check_download_limits(ip, ind_limit=10, zip_limit=3)
        if limits['individual_left'] <= 0:
            raise HTTPException(
                status_code=429, 
                detail="Has superado tu límite de 10 descargas individuales diarias de la Comunidad RobotEdge. Vuelve mañana."
            )
            
        book = books_to_download[0]
        file_path = os.path.join(BOOKS_DIR, book['filename'])
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"El archivo '{book['filename']}' no está en el servidor")
            
        # Log download in SQLite
        log_download(ip, book['title'], is_zip=False, zip_id=None)
        
        return FileResponse(
            path=file_path,
            filename=book['filename'],
            media_type="application/pdf"
        )
        
    # Download multiple books in a ZIP (ZIP Mode)
    else:
        # Enforce max 5 books in a ZIP
        if len(books_to_download) > 5:
            raise HTTPException(
                status_code=400,
                detail="El archivo ZIP excede el límite permitido de 5 libros de la Comunidad RobotEdge."
            )
            
        # Check ZIP rate limit
        limits = check_download_limits(ip, ind_limit=10, zip_limit=3)
        if limits['zip_left'] <= 0:
            raise HTTPException(
                status_code=429, 
                detail="Has superado tu límite de 3 descargas ZIP diarias de la Comunidad RobotEdge. Vuelve mañana."
            )
            
        # Create temp ZIP file
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        temp_zip.close() # Close handle so zipfile can write to it safely
        
        try:
            with zipfile.ZipFile(temp_zip.name, "w", zipfile.ZIP_DEFLATED) as zf:
                for book in books_to_download:
                    file_path = os.path.join(BOOKS_DIR, book['filename'])
                    if os.path.exists(file_path):
                        # Save inside zip with its clean name
                        clean_name = f"{book['title']} - {book['author']}.pdf"
                        clean_name = re.sub(r'[/\\?%*:|"<>]', '_', clean_name) # sanitize name
                        zf.write(file_path, clean_name)
                        
            # Generate a unique ZIP transaction identifier
            zip_id = str(uuid.uuid4())
            
            # Log each selected book inside the ZIP individually
            for book in books_to_download:
                log_download(ip, book['title'], is_zip=True, zip_id=zip_id)
            
            # Setup background task to delete temp zip after download finishes
            def delete_temp_file(path):
                try:
                    os.unlink(path)
                    logger.info(f"Cleaned up temporary download ZIP: {path}")
                except Exception as e:
                    logger.error(f"Error deleting temp ZIP: {e}")
                    
            background_tasks.add_task(delete_temp_file, temp_zip.name)
            
            return FileResponse(
                path=temp_zip.name,
                filename="Libros_Comunidad_RobotEdge.zip",
                media_type="application/zip"
            )
        except Exception as e:
            logger.error(f"Error compiling download ZIP: {e}")
            raise HTTPException(status_code=500, detail="Error al generar el archivo comprimido")

@app.get("/api/books/{hash}/view")
async def view_book_pdf(hash: str):
    matched_book = next((b for b in books_cache if get_file_md5(b['filename']) == hash), None)
    if not matched_book:
        raise HTTPException(status_code=404, detail="Libro no encontrado")
        
    file_path = os.path.join(BOOKS_DIR, matched_book['filename'])
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="El archivo no está en el servidor")
        
    return FileResponse(
        path=file_path,
        media_type="application/pdf"
    )

@app.post("/api/stats/visit")
async def post_visit(request: Request):
    ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    log_visit(ip, user_agent)
    return {"status": "success"}

@app.post("/api/admin/login")
async def admin_login(payload: dict):
    password = payload.get("password")
    if password == ADMIN_PASSWORD:
        return {"success": True, "token": ADMIN_TOKEN}
    return JSONResponse(status_code=401, content={"success": False, "message": "Contraseña de administrador incorrecta"})

@app.get("/api/admin/stats")
async def admin_stats(token: str = Query(...)):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Acceso denegado: token inválido")
    return get_stats()

# Serve Frontend static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Serve index.html at root
@app.get("/")
async def read_index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

# Serve admin dashboard at /admin
@app.get("/admin")
async def read_admin():
    return FileResponse(os.path.join(BASE_DIR, "admin.html"))
