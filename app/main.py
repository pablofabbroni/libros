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

from database import init_db, log_visit, log_download, check_download_limit, get_stats
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
async def get_books(refresh: bool = False):
    global books_cache
    if refresh:
        logger.info("Re-scanning books folder...")
        books_cache = scan_books_folder()
    
    # Map cache items to expose hash, title, author, cover_url, and file size in MB
    response_books = []
    for b in books_cache:
        response_books.append({
            'hash': get_file_md5(b['filename']),
            'title': b['title'],
            'author': b['author'],
            'cover_url': b['cover_url'],
            'size_mb': round(b['size_bytes'] / (1024 * 1024), 2)
        })
    return response_books

@app.get("/api/download/status")
async def get_download_status(request: Request):
    ip = get_client_ip(request)
    limit_left = check_download_limit(ip, DOWNLOAD_LIMIT_DAILY)
    return {
        'limit_left': limit_left,
        'limit_total': DOWNLOAD_LIMIT_DAILY,
        'ip_address': ip
    }

@app.get("/api/download")
async def download_books(
    request: Request,
    background_tasks: BackgroundTasks,
    hashes: str = Query(..., description="Comma-separated book hashes to download")
):
    ip = get_client_ip(request)
    limit_left = check_download_limit(ip, DOWNLOAD_LIMIT_DAILY)
    
    # Parse requested hashes
    hash_list = [h.strip() for h in hashes.split(",") if h.strip()]
    if not hash_list:
        raise HTTPException(status_code=400, detail="No se especificaron libros para descargar")
        
    # Check rate limit (only for public users, not administrators, but here it applies by default)
    if limit_left <= 0:
        raise HTTPException(
            status_code=429, 
            detail="Has superado tu límite de 10 descargas diarias de la Comunidad RobotEdge. Inténtalo de nuevo mañana."
        )
        
    # Match hashes against books in cache
    books_to_download = []
    for h in hash_list:
        matched_book = next((b for b in books_cache if get_file_md5(b['filename']) == h), None)
        if matched_book:
            books_to_download.append(matched_book)
            
    if not books_to_download:
        raise HTTPException(status_code=404, detail="Ninguno de los libros seleccionados fue encontrado")
        
    # Download single book
    if len(books_to_download) == 1:
        book = books_to_download[0]
        file_path = os.path.join(BOOKS_DIR, book['filename'])
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"El archivo '{book['filename']}' no está en el servidor")
            
        # Log download in SQLite
        log_download(ip, book['title'], is_zip=False)
        
        return FileResponse(
            path=file_path,
            filename=book['filename'],
            media_type="application/pdf"
        )
        
    # Download multiple books in a ZIP
    else:
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
                        
            # Log single bulk download event
            log_download(ip, f"ZIP Múltiple ({len(books_to_download)} libros)", is_zip=True)
            
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
