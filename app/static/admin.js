// State
let adminToken = localStorage.getItem("admin_token") || "";

// DOM Elements
const loginOverlay = document.getElementById("login-overlay");
const adminDashboardContent = document.getElementById("admin-dashboard-content");
const passwordInput = document.getElementById("password-input");
const btnLogin = document.getElementById("btn-login");
const loginErrorMsg = document.getElementById("login-error-msg");
const btnLogout = document.getElementById("btn-logout");

const kpiVisits = document.getElementById("kpi-visits");
const kpiDownloads = document.getElementById("kpi-downloads");
const kpiBooks = document.getElementById("kpi-books");
const topDownloadsTbody = document.getElementById("top-downloads-tbody");

const btnRefreshLibrary = document.getElementById("btn-refresh-library");

const adminModal = document.getElementById("admin-modal");
const adminModalIcon = document.getElementById("admin-modal-icon");
const adminModalTitle = document.getElementById("admin-modal-title");
const adminModalMessage = document.getElementById("admin-modal-message");
const btnCloseAdminModal = document.getElementById("btn-close-admin-modal");

// Init
document.addEventListener("DOMContentLoaded", () => {
    if (adminToken) {
        showDashboard();
    } else {
        showLogin();
    }

    // Event listeners
    btnLogin.addEventListener("click", handleLogin);
    passwordInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") handleLogin();
    });
    btnLogout.addEventListener("click", handleLogout);
    btnRefreshLibrary.addEventListener("click", handleRefreshLibrary);
    btnCloseAdminModal.addEventListener("click", hideAdminModal);
});

// Authentication
function showLogin() {
    loginOverlay.style.display = "flex";
    adminDashboardContent.style.display = "none";
    passwordInput.value = "";
    passwordInput.focus();
}

function showDashboard() {
    loginOverlay.style.display = "none";
    adminDashboardContent.style.display = "block";
    fetchStats();
}

async function handleLogin() {
    const password = passwordInput.value;
    if (!password) return;

    try {
        const response = await fetch("/api/admin/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password })
        });

        const data = await response.json();
        if (response.ok && data.success) {
            adminToken = data.token;
            localStorage.setItem("admin_token", adminToken);
            loginErrorMsg.style.display = "none";
            showDashboard();
        } else {
            loginErrorMsg.style.display = "block";
            passwordInput.focus();
        }
    } catch (err) {
        console.error("Login request failed:", err);
        loginErrorMsg.textContent = "Error de conexión con el servidor.";
        loginErrorMsg.style.display = "block";
    }
}

function handleLogout() {
    adminToken = "";
    localStorage.removeItem("admin_token");
    showLogin();
}

// Stats Loading
async function fetchStats() {
    if (!adminToken) return;

    try {
        // 1. Fetch backend analytics
        const response = await fetch(`/api/admin/stats?token=${adminToken}`);
        if (!response.ok) {
            if (response.status === 403) {
                // Token expired or invalid, force logout
                handleLogout();
                return;
            }
            throw new Error("Failed to load dashboard metrics");
        }
        const stats = await response.json();

        // 2. Fetch current books list count
        const booksResponse = await fetch("/api/books");
        const books = booksResponse.ok ? await booksResponse.json() : [];

        // 3. Render KPIs
        kpiVisits.textContent = stats.unique_visitors;
        kpiDownloads.textContent = stats.total_downloads;
        kpiBooks.textContent = books.length;

        // 4. Render Top Downloads Table
        topDownloadsTbody.innerHTML = "";
        
        if (stats.top_books.length === 0) {
            topDownloadsTbody.innerHTML = `
                <tr>
                    <td colspan="3" style="text-align: center; color: var(--text-gray); padding: 30px;">
                        No hay registros de descargas aún.
                    </td>
                </tr>
            `;
            return;
        }

        stats.top_books.forEach((book, index) => {
            const row = document.createElement("tr");
            row.innerHTML = `
                <td class="rank-col">${index + 1}</td>
                <td>${book.title}</td>
                <td class="count-col">${book.count}</td>
            `;
            topDownloadsTbody.appendChild(row);
        });

    } catch (err) {
        console.error("Error fetching stats:", err);
    }
}

// Refresh library index
async function handleRefreshLibrary() {
    btnRefreshLibrary.disabled = true;
    btnRefreshLibrary.textContent = "Sincronizando...";

    try {
        const response = await fetch("/api/books?refresh=true");
        if (response.ok) {
            showAdminModal("✔", "Biblioteca Sincronizada", "La carpeta de libros PDF se ha escaneado con éxito. El índice y las portadas se han actualizado.");
            fetchStats();
        } else {
            throw new Error("Failed to refresh library");
        }
    } catch (err) {
        showAdminModal("❌", "Error de Sincronización", "No se pudo sincronizar la biblioteca con el servidor.");
    } finally {
        btnRefreshLibrary.disabled = false;
        btnRefreshLibrary.textContent = "Sincronizar Libros";
    }
}

// Modal Helper functions
function showAdminModal(icon, title, message) {
    adminModalIcon.textContent = icon;
    adminModalIcon.style.color = icon === "✔" ? "var(--accent-gold)" : "#ef4444";
    adminModalTitle.textContent = title;
    adminModalMessage.textContent = message;
    adminModal.classList.add("active");
}

function hideAdminModal() {
    adminModal.classList.remove("active");
}
