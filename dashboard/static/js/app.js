/* ============================================================
   Dashboard — Core JS (Vercel Design)
   ============================================================ */

// --- Theme Toggle ---
(function() {
    const saved = localStorage.getItem('sys-theme');
    if (saved === 'light') document.documentElement.classList.add('light');
})();

document.addEventListener('DOMContentLoaded', () => {
    // Theme toggle button
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }

    // Sidebar hamburger (mobile)
    const hamburger = document.getElementById('hamburger-btn');
    const sidebar = document.getElementById('sidebar');
    if (hamburger && sidebar) {
        hamburger.addEventListener('click', () => {
            sidebar.classList.toggle('mobile-open');
        });

        // Close sidebar on outside click (mobile)
        document.addEventListener('click', (e) => {
            if (sidebar.classList.contains('mobile-open') &&
                !sidebar.contains(e.target) &&
                !hamburger.contains(e.target)) {
                sidebar.classList.remove('mobile-open');
            }
        });
    }
});

function toggleTheme() {
    document.documentElement.classList.toggle('light');
    const isLight = document.documentElement.classList.contains('light');
    localStorage.setItem('sys-theme', isLight ? 'light' : 'dark');
}

// --- API Helper ---
async function apiFetch(endpoint) {
    try {
        const response = await fetch(endpoint);
        if (response.status === 401) {
            window.location.href = '/login';
            return null;
        }
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (err) {
        console.error(`API fetch failed: ${endpoint}`, err);
        return null;
    }
}

// --- Number Formatting ---
function formatNumber(n) {
    if (n === null || n === undefined || n === '--') return '--';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toLocaleString();
}

// --- Chart.js Defaults ---
if (typeof Chart !== 'undefined') {
    Chart.defaults.color = '#888888';
    Chart.defaults.borderColor = 'rgba(255,255,255,0.08)';
    Chart.defaults.font.family = "'Geist', -apple-system, sans-serif";
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.pointStyleWidth = 10;
    Chart.defaults.plugins.legend.labels.padding = 16;
}
