// State variables
let booksData = [];
let selectedHashes = new Set();
let dailyLimitIndLeft = 10;
let dailyLimitIndTotal = 10;
let dailyLimitZipLeft = 3;
let dailyLimitZipTotal = 3;
let currentSortMode = "default"; // "default", "recommended", "downloaded"

// DOM Elements
const searchInput = document.getElementById("search-input");
const limitBadgeInd = document.getElementById("limit-badge-ind");
const limitBadgeZip = document.getElementById("limit-badge-zip");
const booksGrid = document.getElementById("books-grid");
const loadingIndicator = document.getElementById("loading-indicator");
const noResults = document.getElementById("no-results");

const selectionBar = document.getElementById("selection-bar");
const selectionCount = document.getElementById("selection-count");
const selectionText = document.getElementById("selection-text");
const btnDownloadSelection = document.getElementById("btn-download-selection");
const btnDownloadText = document.getElementById("btn-download-text");
const btnClearSelection = document.getElementById("btn-clear-selection");

const errorModal = document.getElementById("error-modal");
const modalTitle = document.getElementById("modal-title");
const modalMessage = document.getElementById("modal-message");
const btnCloseModal = document.getElementById("btn-close-modal");

// Preview Modal Elements
const previewModal = document.getElementById("preview-modal");
const previewModalTitle = document.getElementById("preview-modal-title");
const pdfIframe = document.getElementById("pdf-iframe");
const btnClosePreview = document.getElementById("btn-close-preview");

// Init Page
document.addEventListener("DOMContentLoaded", () => {
    // 1. Log visit metrics
    fetch("/api/stats/visit", { method: "POST" })
        .catch(err => console.error("Error logging visit:", err));

    // 2. Fetch and render books
    fetchBooks();

    // 3. Fetch download limit status
    updateDownloadLimit();

    // 4. Setup Event Listeners
    searchInput.addEventListener("input", filterBooks);
    btnClearSelection.addEventListener("click", clearSelection);
    btnDownloadSelection.addEventListener("click", triggerDownload);
    btnCloseModal.addEventListener("click", hideModal);
    btnClosePreview.addEventListener("click", hidePreviewModal);

    // Setup Filter Tabs
    const tabs = document.querySelectorAll(".tab-btn");
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            currentSortMode = tab.dataset.sort;
            filterBooks();
        });
    });
});

// Fetch books index from backend
async function fetchBooks() {
    try {
        const response = await fetch("/api/books");
        if (!response.ok) throw new Error("Error cargando libros");
        
        booksData = await response.json();
        
        loadingIndicator.style.display = "none";
        booksGrid.style.display = "grid";
        
        filterBooks(); // Render with sorting applied
    } catch (err) {
        loggerError("No se pudieron cargar los libros. Revisa la conexión.", err);
    }
}

// Render book list
function renderBooks(books) {
    booksGrid.innerHTML = "";
    
    if (books.length === 0) {
        booksGrid.style.display = "none";
        noResults.style.display = "block";
        return;
    }
    
    noResults.style.display = "none";
    booksGrid.style.display = "grid";

    books.forEach(book => {
        const isSelected = selectedHashes.has(book.hash);
        
        const card = document.createElement("div");
        card.className = `book-card-item ${isSelected ? 'selected' : ''}`;
        card.dataset.hash = book.hash;
        
        card.innerHTML = `
            <div class="card-checkbox-wrapper">
                <input type="checkbox" class="card-checkbox" ${isSelected ? 'checked' : ''} data-hash="${book.hash}">
            </div>
            <div class="book-thumbnail-wrapper">
                <img src="${book.cover_url}" class="book-thumbnail" alt="${book.title}" loading="lazy">
                <div class="book-cover-overlay">
                    <button class="btn-read-online" data-hash="${book.hash}">📖 Leer Online</button>
                </div>
            </div>
            <h3 class="book-title-container">
                <div class="book-card-title" title="${book.title}">${book.title}</div>
            </h3>
            <p class="book-card-author" title="${book.author}">${book.author}</p>
            
            <button class="card-btn-read-online" data-hash="${book.hash}">📖 Leer Online</button>
            
            <!-- Panel de Recomendaciones -->
            <div class="book-voting-panel">
                <button class="vote-btn vote-up ${book.user_vote === 1 ? 'active' : ''}" title="Recomendar este libro">
                    👍 <span class="vote-count">${book.likes || 0}</span>
                </button>
                <button class="vote-btn vote-down ${book.user_vote === -1 ? 'active' : ''}" title="No recomendar este libro">
                    👎 <span class="vote-count">${book.dislikes || 0}</span>
                </button>
            </div>

            <div class="book-card-meta">
                <span class="book-size">${book.size_mb} MB</span>
                <span class="book-downloads-count">📥 ${book.downloads || 0} desc.</span>
            </div>
        `;
        
        // Add card select listener (clicking cover, details, or checkbox selects the card)
        card.addEventListener("click", (e) => {
            // Avoid triggering select if user clicked a vote button or the hover overlay buttons or read online buttons
            if (e.target.closest(".book-voting-panel") || e.target.closest(".vote-btn") || e.target.closest(".book-cover-overlay") || e.target.closest(".btn-read-online") || e.target.closest(".card-btn-read-online")) {
                return;
            }
            
            // Prevent event double-firing if user clicked checkbox directly
            if (e.target.classList.contains("card-checkbox")) {
                toggleBookSelection(book.hash);
                return;
            }
            
            toggleBookSelection(book.hash);
        });
        
        // Setup read online button listeners
        const btnRead = card.querySelector(".btn-read-online");
        if (btnRead) {
            btnRead.addEventListener("click", (e) => {
                e.stopPropagation();
                showPreviewModal(book.hash, book.title);
            });
        }

        const btnReadCard = card.querySelector(".card-btn-read-online");
        if (btnReadCard) {
            btnReadCard.addEventListener("click", (e) => {
                e.stopPropagation();
                showPreviewModal(book.hash, book.title);
            });
        }
        
        // Setup vote event listeners
        const btnUp = card.querySelector(".vote-up");
        const btnDown = card.querySelector(".vote-down");
        
        btnUp.addEventListener("click", (e) => {
            e.stopPropagation();
            const currentVote = book.user_vote;
            const newVote = currentVote === 1 ? 0 : 1;
            castBookVote(book.hash, newVote, e);
        });
        
        btnDown.addEventListener("click", (e) => {
            e.stopPropagation();
            const currentVote = book.user_vote;
            const newVote = currentVote === -1 ? 0 : -1;
            castBookVote(book.hash, newVote, e);
        });
        
        booksGrid.appendChild(card);
    });
}

// Toggle single book selection (locks at max 5)
function toggleBookSelection(hash) {
    if (selectedHashes.has(hash)) {
        selectedHashes.delete(hash);
    } else {
        if (selectedHashes.size >= 5) {
            showModal(
                "Límite de Selección", 
                "Solo puedes seleccionar un máximo de 5 libros para descargar agrupados en un archivo ZIP."
            );
            return;
        }
        selectedHashes.add(hash);
    }
    
    // Refresh GUI states
    updateCardsUI();
    updateSelectionBarUI();
}

// Synchronize UI class selected states
function updateCardsUI() {
    const cards = booksGrid.querySelectorAll(".book-card-item");
    cards.forEach(card => {
        const hash = card.dataset.hash;
        const checkbox = card.querySelector(".card-checkbox");
        
        if (selectedHashes.has(hash)) {
            card.classList.add("selected");
            if (checkbox) checkbox.checked = true;
        } else {
            card.classList.remove("selected");
            if (checkbox) checkbox.checked = false;
        }
    });
}

// Update floating actions bar at the bottom
function updateSelectionBarUI() {
    const count = selectedHashes.size;
    if (count > 0) {
        selectionCount.textContent = count;
        selectionText.textContent = count === 1 ? "libro seleccionado" : "libros seleccionados";
        btnDownloadText.textContent = count === 1 ? "Descargar PDF" : "Descargar ZIP";
        selectionBar.classList.add("active");
    } else {
        selectionBar.classList.remove("active");
    }
}

// Clear all selected checkboxes
// Preview modal management
function showPreviewModal(hash, title) {
    previewModalTitle.textContent = title;
    pdfIframe.src = `/api/books/${hash}/view`;
    previewModal.classList.add("active");
}

function hidePreviewModal() {
    previewModal.classList.remove("active");
    pdfIframe.src = "";
}

function clearSelection() {
    selectedHashes.clear();
    updateCardsUI();
    updateSelectionBarUI();
}

// Search & filter matching logic (with active sorting)
function filterBooks() {
    const query = normalize(searchInput.value);
    
    let filtered = booksData;
    if (query) {
        filtered = booksData.filter(book => {
            const titleNorm = normalize(book.title);
            const authorNorm = normalize(book.author);
            return titleNorm.includes(query) || authorNorm.includes(query);
        });
    }
    
    // Apply sorting
    if (currentSortMode === "recommended") {
        filtered = [...filtered].sort((a, b) => {
            const netA = (a.likes || 0) - (a.dislikes || 0);
            const netB = (b.likes || 0) - (b.dislikes || 0);
            if (netB !== netA) return netB - netA; // Descending score
            return a.title.localeCompare(b.title);  // Secondary alphabetical
        });
    } else if (currentSortMode === "downloaded") {
        filtered = [...filtered].sort((a, b) => {
            const dlA = a.downloads || 0;
            const dlB = b.downloads || 0;
            if (dlB !== dlA) return dlB - dlA; // Descending downloads
            return a.title.localeCompare(b.title); // Secondary alphabetical
        });
    } else {
        // Default alphabetical
        filtered = [...filtered].sort((a, b) => a.title.localeCompare(b.title));
    }
    
    renderBooks(filtered);
}

// Cast recommendation vote
async function castBookVote(hash, voteType, event) {
    try {
        const response = await fetch(`/api/books/${hash}/vote`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ vote_type: voteType })
        });
        
        if (!response.ok) throw new Error("Error registrando voto");
        const data = await response.json();
        
        // Update local state item
        const book = booksData.find(b => b.hash === hash);
        if (book) {
            book.likes = data.likes;
            book.dislikes = data.dislikes;
            book.user_vote = data.user_vote;
        }
        
        // Re-filter and render
        filterBooks();
    } catch (err) {
        console.error("Votación fallida:", err);
        showModal("Error del Sistema", "No se pudo registrar tu recomendación en este momento.");
    }
}

// Fetch download limit status from API
async function updateDownloadLimit() {
    try {
        const response = await fetch("/api/download/status");
        if (response.ok) {
            const data = await response.json();
            const limits = data.limits;
            dailyLimitIndLeft = limits.individual_left;
            dailyLimitIndTotal = limits.individual_limit;
            dailyLimitZipLeft = limits.zip_left;
            dailyLimitZipTotal = limits.zip_limit;
            
            limitBadgeInd.innerHTML = `⚡ <span>Indiv: <strong>${dailyLimitIndLeft} / ${dailyLimitIndTotal}</strong> rest.</span>`;
            limitBadgeZip.innerHTML = `📦 <span>ZIP: <strong>${dailyLimitZipLeft} / ${dailyLimitZipTotal}</strong> rest.</span>`;
            
            if (dailyLimitIndLeft <= 2) {
                limitBadgeInd.style.borderColor = "rgba(226, 176, 66, 0.4)";
                limitBadgeInd.style.color = "#e2b042";
            } else {
                limitBadgeInd.style.borderColor = "rgba(255, 255, 255, 0.08)";
                limitBadgeInd.style.color = "var(--text-gray)";
            }
            
            if (dailyLimitZipLeft <= 1) {
                limitBadgeZip.style.borderColor = "rgba(226, 176, 66, 0.4)";
                limitBadgeZip.style.color = "#e2b042";
            } else {
                limitBadgeZip.style.borderColor = "rgba(255, 255, 255, 0.08)";
                limitBadgeZip.style.color = "var(--text-gray)";
            }
        }
    } catch (err) {
        console.error("Error fetching download status:", err);
    }
}

// Download triggering logic
async function triggerDownload() {
    if (selectedHashes.size === 0) return;
    const count = selectedHashes.size;
    
    // 1. Verify limits locally
    if (count === 1) {
        if (dailyLimitIndLeft <= 0) {
            showModal(
                "Límite Diario Superado", 
                `Has agotado tus ${dailyLimitIndTotal} descargas individuales diarias permitidas. Por favor, vuelve mañana.`
            );
            return;
        }
    } else {
        if (count > 5) {
            showModal("Límite de Selección", "Puedes descargar hasta un máximo de 5 libros por ZIP.");
            return;
        }
        if (dailyLimitZipLeft <= 0) {
            showModal(
                "Límite de ZIP Superado", 
                `Has agotado tus ${dailyLimitZipTotal} descargas grupales (ZIP) diarias permitidas. Por favor, vuelve mañana.`
            );
            return;
        }
    }
    
    const hashesParam = Array.from(selectedHashes).join(",");
    
    // 2. Perform pre-flight API limit check
    try {
        const statusRes = await fetch("/api/download/status");
        if (statusRes.ok) {
            const statusData = await statusRes.json();
            const limits = statusData.limits;
            if (count === 1) {
                if (limits.individual_left <= 0) {
                    showModal("Límite Diario Superado", "Tu dirección IP ya ha agotado el límite de 10 descargas individuales hoy.");
                    updateDownloadLimit();
                    return;
                }
            } else {
                if (limits.zip_left <= 0) {
                    showModal("Límite de ZIP Superado", "Tu dirección IP ya ha agotado el límite de 3 descargas grupales (ZIP) hoy.");
                    updateDownloadLimit();
                    return;
                }
            }
        }
    } catch (e) {
        console.error("Preflight check failed", e);
    }
    
    // 3. Initiate download
    const downloadUrl = `/api/download?hashes=${hashesParam}`;
    const dlLink = document.createElement("a");
    dlLink.href = downloadUrl;
    dlLink.setAttribute("download", "");
    document.body.appendChild(dlLink);
    dlLink.click();
    document.body.removeChild(dlLink);
    
    clearSelection();
    
    // Give backend time to log download, then update GUI
    setTimeout(updateDownloadLimit, 800);
    setTimeout(fetchBooks, 1000); // Re-fetch download counts to update metrics live
}

// Modal management
function showModal(title, message) {
    modalTitle.textContent = title;
    modalMessage.textContent = message;
    errorModal.classList.add("active");
}

// Normalize strings for search
function normalize(text) {
    if (!text) return "";
    return text.toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "") // Remove accents
        .replace(/[^a-z0-9\s]/g, " ")
        .trim()
        .replace(/\s+/g, " ");
}

function hideModal() {
    errorModal.classList.remove("active");
}

function loggerError(msg, err) {
    console.error(msg, err);
    loadingIndicator.style.display = "none";
    showModal("Error del Sistema", msg);
}
