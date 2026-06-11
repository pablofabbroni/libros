// State variables
let booksData = [];
let selectedHashes = new Set();
let dailyLimitLeft = 10;
let dailyLimitTotal = 10;

// DOM Elements
const searchInput = document.getElementById("search-input");
const limitBadge = document.getElementById("limit-badge");
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
});

// Fetch books index from backend
async function fetchBooks() {
    try {
        const response = await fetch("/api/books");
        if (!response.ok) throw new Error("Error cargando libros");
        
        booksData = await response.json();
        
        loadingIndicator.style.display = "none";
        booksGrid.style.display = "grid";
        
        renderBooks(booksData);
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
            </div>
            <h3 class="book-title-container">
                <div class="book-card-title" title="${book.title}">${book.title}</div>
            </h3>
            <p class="book-card-author" title="${book.author}">${book.author}</p>
            <div class="book-card-meta">
                <span class="book-size">${book.size_mb} MB</span>
                <span>Comunidad RobotEdge</span>
            </div>
        `;
        
        // Add card select listener (clicking cover, details, or checkbox selects the card)
        card.addEventListener("click", (e) => {
            // Prevent event double-firing if user clicked checkbox directly
            if (e.target.classList.contains("card-checkbox")) {
                toggleBookSelection(book.hash);
                return;
            }
            
            toggleBookSelection(book.hash);
        });
        
        booksGrid.appendChild(card);
    });
}

// Toggle single book selection
function toggleBookSelection(hash) {
    if (selectedHashes.has(hash)) {
        selectedHashes.delete(hash);
    } else {
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
            checkbox.checked = true;
        } else {
            card.classList.remove("selected");
            checkbox.checked = false;
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
function clearSelection() {
    selectedHashes.clear();
    updateCardsUI();
    updateSelectionBarUI();
}

// Search & filter matching logic
function filterBooks() {
    const query = normalize(searchInput.value);
    
    if (!query) {
        renderBooks(booksData);
        return;
    }
    
    const filtered = booksData.filter(book => {
        const titleNorm = normalize(book.title);
        const authorNorm = normalize(book.author);
        return titleNorm.includes(query) || authorNorm.includes(query);
    });
    
    renderBooks(filtered);
}

// Fetch download limit status from API
async function updateDownloadLimit() {
    try {
        const response = await fetch("/api/download/status");
        if (response.ok) {
            const data = await response.json();
            dailyLimitLeft = data.limit_left;
            dailyLimitTotal = data.limit_total;
            
            limitBadge.innerHTML = `⚡ <span>Descargas: <strong>${dailyLimitLeft} / ${dailyLimitTotal}</strong> restantes hoy</span>`;
            if (dailyLimitLeft <= 2) {
                limitBadge.style.borderColor = "rgba(226, 176, 66, 0.5)";
                limitBadge.style.color = "#e2b042";
            } else {
                limitBadge.style.borderColor = "rgba(255, 255, 255, 0.08)";
                limitBadge.style.color = "var(--text-gray)";
            }
        }
    } catch (err) {
        console.error("Error fetching download status:", err);
    }
}

// Download triggering logic
async function triggerDownload() {
    if (selectedHashes.size === 0) return;
    
    // 1. Verify limit remaining locally first
    if (dailyLimitLeft <= 0) {
        showModal(
            "Descargas Diarias Agotadas", 
            `Has agotado tus ${dailyLimitTotal} descargas gratuitas diarias permitidas. Por favor, vuelve mañana para continuar descargando libros de la Comunidad RobotEdge.`
        );
        return;
    }
    
    const hashesParam = Array.from(selectedHashes).join(",");
    
    // 2. Perform limit request pre-flight check
    try {
        const statusRes = await fetch("/api/download/status");
        if (statusRes.ok) {
            const statusData = await statusRes.json();
            if (statusData.limit_left <= 0) {
                showModal(
                    "Límite diario superado", 
                    "Tu dirección IP ya ha superado el límite de 10 descargas diarias de la comunidad. Vuelve mañana para seguir descargando."
                );
                updateDownloadLimit();
                return;
            }
        }
    } catch (e) {
        console.error("Preflight check failed", e);
    }
    
    // 3. Initiate actual file download
    const downloadUrl = `/api/download?hashes=${hashesParam}`;
    
    // Create an invisible download link and trigger it
    const dlLink = document.createElement("a");
    dlLink.href = downloadUrl;
    // For single book, set target to download, ZIP already triggers download headers
    dlLink.setAttribute("download", "");
    document.body.appendChild(dlLink);
    dlLink.click();
    document.body.removeChild(dlLink);
    
    // Clean selection after triggering download
    clearSelection();
    
    // Give backend half a second to process download log, then update limit badge
    setTimeout(updateDownloadLimit, 800);
}

// Modal management
function showModal(title, message) {
    modalTitle.textContent = title;
    modalMessage.textContent = message;
    errorModal.classList.add("active");
}

function hideModal() {
    errorModal.classList.remove("active");
}

function loggerError(msg, err) {
    console.error(msg, err);
    loadingIndicator.style.display = "none";
    showModal("Error del Sistema", msg);
}
