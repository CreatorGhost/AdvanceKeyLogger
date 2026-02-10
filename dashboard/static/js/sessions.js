/* ============================================================
   Sessions Page JS — Vercel Design
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    loadSessions();
    loadStats();

    document.getElementById('refreshSessions').addEventListener('click', () => {
        loadSessions();
        loadStats();
    });
    document.getElementById('sessionStatus').addEventListener('change', loadSessions);
    document.getElementById('sessionLimit').addEventListener('change', loadSessions);
});

async function loadStats() {
    const data = await apiFetch('/api/sessions/stats');
    if (!data) return;
    document.getElementById('statTotal').textContent = data.total_sessions || 0;
    document.getElementById('statRecording').textContent = data.recording || 0;
    document.getElementById('statFrames').textContent = data.total_frames || 0;
    document.getElementById('statEvents').textContent = data.total_events || 0;
}

async function loadSessions() {
    const limit = document.getElementById('sessionLimit').value;
    const status = document.getElementById('sessionStatus').value;
    let url = `/api/sessions?limit=${limit}`;
    if (status) url += `&status=${status}`;

    const data = await apiFetch(url);
    if (data) renderSessions(data);
}

function renderSessions(data) {
    const grid = document.getElementById('sessionGrid');
    const badge = document.getElementById('sessionCountBadge');
    const sessions = (data && Array.isArray(data.sessions)) ? data.sessions : [];

    badge.textContent = sessions.length;
    grid.innerHTML = '';

    if (sessions.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.style.gridColumn = '1 / -1';
        empty.textContent = 'No sessions recorded yet.';
        grid.appendChild(empty);
        return;
    }

    const fallbackSrc = "data:image/svg+xml," + encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60">'
        + '<rect fill="#141414" width="100" height="60"/>'
        + '<text x="50" y="30" fill="#555" text-anchor="middle" font-size="7">No Frames</text>'
        + '</svg>'
    );

    for (const s of sessions) {
        const card = document.createElement('div');
        card.className = 'screenshot-card';
        card.style.cursor = 'pointer';
        card.addEventListener('click', () => {
            window.location.href = `/sessions/${s.id}/replay`;
        });

        // Thumbnail
        const img = document.createElement('img');
        img.className = 'screenshot-thumb';
        img.src = s.thumbnail_url || fallbackSrc;
        img.alt = 'Session ' + s.id;
        img.loading = 'lazy';
        img.onerror = function () { this.src = fallbackSrc; };

        // Meta
        const meta = document.createElement('div');
        meta.className = 'screenshot-meta';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'screenshot-name';
        const duration = s.duration ? formatDuration(s.duration) : 'Recording...';
        nameSpan.textContent = duration;

        const sizeSpan = document.createElement('span');
        sizeSpan.className = 'screenshot-size';
        if (s.status === 'recording') {
            sizeSpan.innerHTML = '<span style="color:var(--accent-green)">● REC</span>';
        } else {
            sizeSpan.textContent = `${Number(s.frame_count) || 0} frames · ${Number(s.event_count) || 0} events`;
        }

        const dateSpan = document.createElement('span');
        dateSpan.className = 'screenshot-size';
        dateSpan.style.fontSize = '10px';
        dateSpan.style.opacity = '0.5';
        dateSpan.textContent = new Date(s.started_at * 1000).toLocaleString();

        meta.appendChild(nameSpan);
        meta.appendChild(sizeSpan);
        meta.appendChild(dateSpan);
        card.appendChild(img);
        card.appendChild(meta);
        grid.appendChild(card);
    }
}

function formatDuration(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}
