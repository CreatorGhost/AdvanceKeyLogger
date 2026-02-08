/* ============================================================
   Dashboard Page JS — Vercel Design
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    loadDashboardData();
    setInterval(loadDashboardData, 30000);

    // Metric tab click
    document.querySelectorAll('.metric-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.metric-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
        });
    });
});

async function loadDashboardData() {
    const [status, summary, modules, captures] = await Promise.all([
        apiFetch('/api/status'),
        apiFetch('/api/analytics/summary'),
        apiFetch('/api/modules'),
        apiFetch('/api/captures?limit=6'),
    ]);

    if (summary) renderMetrics(summary);
    if (status) renderResources(status);
    if (modules) renderModules(modules);
    if (captures) renderActivity(captures);
    if (status) renderUptime(status);
    if (summary) renderTransport(summary);
}

function renderMetrics(data) {
    document.getElementById('totalCaptures').textContent = formatNumber(data.total_captures);
    document.getElementById('pendingCount').textContent = formatNumber(data.pending);
    document.getElementById('screenshotsCount').textContent = formatNumber(data.screenshots_count);
}

function renderUptime(data) {
    document.getElementById('uptimeValue').textContent = data.uptime || '--';
}

function renderResources(data) {
    const sys = data.system;
    const storage = data.storage;

    // CPU
    const cpuPct = sys.cpu_percent;
    document.getElementById('resCpu').textContent = cpuPct.toFixed(1) + '%';
    document.getElementById('resCpuBar').style.width = Math.min(cpuPct, 100) + '%';

    // Memory
    const memMb = sys.memory_mb;
    document.getElementById('resMemory').textContent = memMb + ' MB';
    const memPct = Math.min((memMb / 500) * 100, 100);
    document.getElementById('resMemoryBar').style.width = memPct + '%';

    // Storage
    const storageMb = storage.data_dir_mb;
    document.getElementById('resStorage').textContent = storageMb + ' MB';
    const storagePct = Math.min((storageMb / 500) * 100, 100);
    document.getElementById('resStorageBar').style.width = storagePct + '%';
}

function renderModules(data) {
    const el = document.getElementById('modulesList');
    const allModules = [
        ...(data.capture_modules || []).map(m => ({...m, type: 'capture'})),
        ...(data.transport_modules || []).map(m => ({...m, type: 'transport'})),
    ];

    if (allModules.length === 0) {
        el.innerHTML = '<div class="empty-state-sm">No modules loaded</div>';
        return;
    }

    el.innerHTML = allModules.map(m => `
        <div class="mod-row">
            <span class="mod-dot"></span>
            <span class="mod-name">${escapeHtml(m.name)}</span>
            <span class="mod-status">${m.type}</span>
            <span class="mod-rate">${escapeHtml(m.class || '')}</span>
        </div>
    `).join('');
}

function renderActivity(data) {
    const tbody = document.getElementById('activityBody');
    const mobile = document.getElementById('activityMobile');

    if (!data.items || data.items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" class="empty-state-sm">No recent activity</td></tr>';
        mobile.innerHTML = '<div class="empty-state-sm">No recent activity</div>';
        return;
    }

    tbody.innerHTML = data.items.map(item => {
        const dotClass = item.status === 'sent' ? 'dot-success' : 'dot-neutral';
        const ts = item.timestamp ? timeAgo(item.timestamp) : '--';
        return `<tr>
            <td><span class="event-dot ${dotClass}"></span>${escapeHtml(item.capture_type || 'event')}</td>
            <td class="detail-cell">${escapeHtml(truncate(item.data || '', 60))}</td>
            <td class="time-cell">${ts}</td>
        </tr>`;
    }).join('');

    mobile.innerHTML = data.items.map(item => {
        const dotClass = item.status === 'sent' ? 'dot-success' : 'dot-neutral';
        const ts = item.timestamp ? timeAgo(item.timestamp) : '--';
        return `<div class="mobile-card">
            <div class="mobile-card-event"><span class="event-dot ${dotClass}"></span>${escapeHtml(item.capture_type || 'event')}</div>
            <div class="mobile-card-detail">${escapeHtml(truncate(item.data || '', 60))}</div>
            <div class="mobile-card-time">${ts}</div>
        </div>`;
    }).join('');
}

function renderTransport(data) {
    document.getElementById('transportSent').textContent = formatNumber(data.sent);
}

function timeAgo(ts) {
    const diff = Date.now() - new Date(ts).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'now';
    if (mins < 60) return mins + 'm';
    const hours = Math.floor(mins / 60);
    if (hours < 24) return hours + 'h';
    return Math.floor(hours / 24) + 'd';
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.substring(0, max) + '...' : str;
}
