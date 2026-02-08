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

    grid.innerHTML = '';

    if (data.screenshots.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.style.gridColumn = '1 / -1';
        empty.textContent = 'No screenshots captured yet.';
        grid.appendChild(empty);
        return;
    }

    const fallbackSrc = "data:image/svg+xml," + encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60">'
        + '<rect fill="#141414" width="100" height="60"/>'
        + '<text x="50" y="35" fill="#555555" text-anchor="middle" font-size="8">No Preview</text>'
        + '</svg>'
    );

    for (const s of data.screenshots) {
        const card = document.createElement('div');
        card.className = 'screenshot-card';
        card.dataset.path = s.path;
        card.dataset.filename = s.filename;
        card.dataset.timestamp = s.timestamp;
        card.addEventListener('click', function () {
            openLightbox(this.dataset.path, this.dataset.filename, this.dataset.timestamp);
        });

        const img = document.createElement('img');
        img.className = 'screenshot-thumb';
        img.src = s.path;
        img.alt = s.filename;
        img.loading = 'lazy';
        img.onerror = function () { this.src = fallbackSrc; };

        const meta = document.createElement('div');
        meta.className = 'screenshot-meta';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'screenshot-name';
        nameSpan.textContent = s.filename;

        const sizeSpan = document.createElement('span');
        sizeSpan.className = 'screenshot-size';
        sizeSpan.textContent = s.size_kb + ' KB';

        meta.appendChild(nameSpan);
        meta.appendChild(sizeSpan);
        card.appendChild(img);
        card.appendChild(meta);
        grid.appendChild(card);
    }
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
