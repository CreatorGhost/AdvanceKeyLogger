/* ============================================================
   Screenshots Page JS — Vercel Design
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    loadScreenshots();

    document.getElementById('refreshScreenshots').addEventListener('click', loadScreenshots);
    document.getElementById('screenshotLimit').addEventListener('change', loadScreenshots);

    document.getElementById('lightboxClose').addEventListener('click', closeLightbox);
    document.querySelector('.lightbox-backdrop').addEventListener('click', closeLightbox);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeLightbox();
    });
});

async function loadScreenshots() {
    const limit = document.getElementById('screenshotLimit').value;
    const data = await apiFetch(`/api/screenshots?limit=${limit}`);
    if (data) {
        renderScreenshots(data);
    }
}

function renderScreenshots(data) {
    const grid = document.getElementById('screenshotGrid');
    const badge = document.getElementById('screenshotCountBadge');

    badge.textContent = `${data.screenshots.length} / ${data.total}`;

    if (data.screenshots.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column:1/-1">
                No screenshots captured yet.
            </div>`;
        return;
    }

    grid.innerHTML = data.screenshots.map(s => `
        <div class="screenshot-card" onclick="openLightbox('${s.path}', '${s.filename}', '${s.timestamp}')">
            <img class="screenshot-thumb"
                 src="${s.path}"
                 alt="${s.filename}"
                 loading="lazy"
                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 60%22><rect fill=%22%23141414%22 width=%22100%22 height=%2260%22/><text x=%2250%22 y=%2235%22 fill=%22%23555555%22 text-anchor=%22middle%22 font-size=%228%22>No Preview</text></svg>'">
            <div class="screenshot-meta">
                <span class="screenshot-name">${s.filename}</span>
                <span class="screenshot-size">${s.size_kb} KB</span>
            </div>
        </div>
    `).join('');
}

function openLightbox(src, filename, timestamp) {
    const lightbox = document.getElementById('lightbox');
    const img = document.getElementById('lightboxImage');
    const info = document.getElementById('lightboxInfo');

    img.src = src;
    info.textContent = `${filename} — ${new Date(timestamp).toLocaleString()}`;
    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    lightbox.classList.remove('active');
    document.body.style.overflow = '';
}
