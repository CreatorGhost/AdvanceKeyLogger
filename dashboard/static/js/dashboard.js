/* ============================================================
   Dashboard Page JS
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    loadDashboardData();
    // Auto-refresh every 30 seconds
    setInterval(loadDashboardData, 30000);
});

async function loadDashboardData() {
    // Load all data in parallel
    const [status, summary, modules, activity] = await Promise.all([
        apiFetch('/api/status'),
        apiFetch('/api/analytics/summary'),
        apiFetch('/api/modules'),
        apiFetch('/api/analytics/activity'),
    ]);

    if (status) renderSystemInfo(status);
    if (summary) renderSummaryStats(summary);
    if (modules) renderModules(modules);
    if (activity) renderActivityChart(activity);
}

function renderSummaryStats(data) {
    document.getElementById('totalCaptures').textContent = formatNumber(data.total_captures);
    document.getElementById('pendingCount').textContent = formatNumber(data.pending);
    document.getElementById('sentCount').textContent = formatNumber(data.sent);
    document.getElementById('screenshotsCount').textContent = formatNumber(data.screenshots_count);
}

function renderSystemInfo(data) {
    const sys = data.system;
    const storage = data.storage;

    document.getElementById('uptimeBadge').textContent = data.uptime;
    document.getElementById('sysHostname').textContent = sys.hostname;
    document.getElementById('sysOS').textContent = sys.os;
    document.getElementById('sysPython').textContent = sys.python;
    document.getElementById('sysCPU').textContent = sys.cpu_percent.toFixed(1) + '%';
    document.getElementById('sysMemory').textContent = sys.memory_mb + ' MB';
    document.getElementById('sysStorage').textContent = storage.data_dir_mb + ' MB';

    // Storage bar (assume 500 MB max from config)
    const pct = Math.min((storage.data_dir_mb / 500) * 100, 100);
    document.getElementById('storageBar').style.width = pct + '%';
}

function renderModules(data) {
    const captureEl = document.getElementById('captureModules');
    const transportEl = document.getElementById('transportModules');

    if (data.capture_modules.length === 0) {
        captureEl.innerHTML = '<div class="empty-state-sm">No capture modules loaded</div>';
    } else {
        captureEl.innerHTML = data.capture_modules.map(m => `
            <div class="module-item">
                <span class="module-name">${m.name}</span>
                <span class="module-class">${m.class}</span>
            </div>
        `).join('');
    }

    if (data.transport_modules.length === 0) {
        transportEl.innerHTML = '<div class="empty-state-sm">No transport modules loaded</div>';
    } else {
        transportEl.innerHTML = data.transport_modules.map(m => `
            <div class="module-item">
                <span class="module-name">${m.name}</span>
                <span class="module-class">${m.class}</span>
            </div>
        `).join('');
    }
}

let activityChart = null;

function renderActivityChart(data) {
    const canvas = document.getElementById('activityChart');
    if (!canvas) return;

    // Sum heatmap into hourly totals
    const hourlyTotals = new Array(24).fill(0);
    for (const dayRow of data.heatmap) {
        for (let h = 0; h < 24; h++) {
            hourlyTotals[h] += dayRow[h];
        }
    }

    const labels = hourlyTotals.map((_, i) => {
        const h = i % 12 || 12;
        return h + (i < 12 ? 'a' : 'p');
    });

    const chartData = {
        labels: labels,
        datasets: [{
            label: 'Events',
            data: hourlyTotals,
            backgroundColor: 'rgba(99, 102, 241, 0.3)',
            borderColor: '#6366f1',
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            pointBackgroundColor: '#6366f1',
            pointBorderColor: '#6366f1',
            pointRadius: 3,
            pointHoverRadius: 6,
        }],
    };

    if (activityChart) {
        activityChart.data = chartData;
        activityChart.update();
        return;
    }

    activityChart = new Chart(canvas, {
        type: 'line',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index',
            },
            scales: {
                x: {
                    grid: { display: false },
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(30, 41, 59, 0.5)',
                    },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1a1f2e',
                    borderColor: '#2a3441',
                    borderWidth: 1,
                    titleColor: '#e2e8f0',
                    bodyColor: '#94a3b8',
                    padding: 12,
                    cornerRadius: 8,
                },
            },
        },
    });
}
