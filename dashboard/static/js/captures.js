/* ============================================================
   Captures Page JS — Vercel Design
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    loadCaptures().catch(console.error);

    document.getElementById('refreshCaptures').addEventListener('click', () => loadCaptures().catch(console.error));
    document.getElementById('captureTypeFilter').addEventListener('change', () => loadCaptures().catch(console.error));
    document.getElementById('captureLimitFilter').addEventListener('change', () => loadCaptures().catch(console.error));
});

async function loadCaptures() {
    const type = document.getElementById('captureTypeFilter').value;
    const limit = document.getElementById('captureLimitFilter').value;

    let url = `/api/captures?limit=${limit}`;
    if (type) url += `&capture_type=${type}`;

    const data = await apiFetch(url);
    if (data) {
        renderCapturesTable(data);
    }
}

function renderCapturesTable(data) {
    const tbody = document.getElementById('capturesBody');
    const badge = document.getElementById('captureCountBadge');

    badge.textContent = `${data.items.length} / ${data.total}`;

    if (data.items.length === 0) {
        tbody.innerHTML = `
            <tr><td colspan="5" class="empty-state">
                No captures found. Start monitoring to see data here.
            </td></tr>`;
        return;
    }

    tbody.innerHTML = data.items.map(item => {
        const typeClass = getTypeBadgeClass(item.capture_type);
        const statusClass = item.status === 'sent' ? 'badge-green' : 'badge-amber';
        const timestamp = item.timestamp
            ? new Date(item.timestamp).toLocaleString()
            : '--';

        return `
            <tr>
                <td style="font-family:var(--font-mono);color:var(--text-tertiary)">#${escapeHtml(String(item.id))}</td>
                <td><span class="badge ${typeClass}">${escapeHtml(item.capture_type || 'unknown')}</span></td>
                <td title="${escapeHtml(item.data)}">${escapeHtml(truncate(item.data, 80))}</td>
                <td style="font-family:var(--font-mono);font-size:12px">${escapeHtml(timestamp)}</td>
                <td><span class="badge ${statusClass}">${escapeHtml(item.status || 'pending')}</span></td>
            </tr>
        `;
    }).join('');
}

function getTypeBadgeClass(type) {
    const map = {
        keyboard: 'badge-blue',
        mouse: 'badge-green',
        clipboard: 'badge-amber',
        window: 'badge',
        screenshot: 'badge-red',
    };
    return map[type] || 'badge';
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
