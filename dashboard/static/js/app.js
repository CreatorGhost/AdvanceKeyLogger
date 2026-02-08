/* ============================================================
   AdvanceKeyLogger Dashboard — Core JS
   ============================================================ */

// --- Sidebar Toggle (Mobile) ---
document.addEventListener('DOMContentLoaded', () => {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');

    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });

        // Close sidebar on outside click (mobile)
        document.addEventListener('click', (e) => {
            if (sidebar.classList.contains('open') &&
                !sidebar.contains(e.target) &&
                !menuToggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }

    // Update status indicator
    updateStatus();
});

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

// --- Status Indicator ---
async function updateStatus() {
    const indicator = document.getElementById('statusIndicator');
    if (!indicator) return;

    const dot = indicator.querySelector('.status-dot');
    const text = indicator.querySelector('.status-text');

    const data = await apiFetch('/api/health');
    if (data && data.status === 'ok') {
        dot.className = 'status-dot online';
        text.textContent = 'Online';
    } else {
        dot.className = 'status-dot offline';
        text.textContent = 'Offline';
    }
}

// --- Number Formatting ---
function formatNumber(n) {
    if (n === null || n === undefined || n === '--') return '--';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toLocaleString();
}

// --- Chart Defaults ---
if (typeof Chart !== 'undefined') {
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.borderColor = '#1e293b';
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.pointStyleWidth = 10;
    Chart.defaults.plugins.legend.labels.padding = 16;
}
