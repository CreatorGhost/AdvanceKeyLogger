/* ============================================================
   Command Palette (Cmd+K)
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    const overlay = document.getElementById('cmd-overlay');
    const input = document.getElementById('cmd-input');
    const list = document.getElementById('cmd-list');
    const trigger = document.getElementById('search-trigger');

    if (!overlay || !input || !list) return;

    let selectedIdx = -1;

    function openPalette() {
        overlay.classList.add('open');
        input.value = '';
        filterItems('');
        selectedIdx = -1;
        updateSelection();
        setTimeout(() => input.focus(), 10);
    }

    function closePalette() {
        overlay.classList.remove('open');
        selectedIdx = -1;
    }

    function filterItems(query) {
        const items = list.querySelectorAll('.cmd-item');
        const q = query.toLowerCase();
        items.forEach(item => {
            const text = item.textContent.toLowerCase();
            item.style.display = text.indexOf(q) !== -1 ? '' : 'none';
        });
        selectedIdx = -1;
        updateSelection();
    }

    function getVisible() {
        const items = [];
        list.querySelectorAll('.cmd-item').forEach(item => {
            if (item.style.display !== 'none') items.push(item);
        });
        return items;
    }

    function updateSelection() {
        list.querySelectorAll('.cmd-item').forEach(item => {
            item.classList.remove('selected');
        });
        const visible = getVisible();
        if (selectedIdx >= 0 && selectedIdx < visible.length) {
            visible[selectedIdx].classList.add('selected');
        }
    }

    // Open trigger
    if (trigger) {
        trigger.addEventListener('click', openPalette);
    }

    // Keyboard shortcut: Cmd+K / Ctrl+K
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            if (overlay.classList.contains('open')) {
                closePalette();
            } else {
                openPalette();
            }
        }
        if (e.key === 'Escape' && overlay.classList.contains('open')) {
            closePalette();
        }
    });

    // Click overlay backdrop to close
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closePalette();
    });

    // Filter on input
    input.addEventListener('input', () => {
        filterItems(input.value);
    });

    // Keyboard navigation
    input.addEventListener('keydown', (e) => {
        const visible = getVisible();
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIdx = Math.min(selectedIdx + 1, visible.length - 1);
            updateSelection();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIdx = Math.max(selectedIdx - 1, 0);
            updateSelection();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (selectedIdx >= 0 && selectedIdx < visible.length) {
                navigateToItem(visible[selectedIdx]);
            }
            closePalette();
        }
    });

    // Click on items
    list.querySelectorAll('.cmd-item').forEach(item => {
        item.addEventListener('click', () => {
            navigateToItem(item);
            closePalette();
        });
    });

    function navigateToItem(item) {
        const href = item.getAttribute('data-href');
        if (href) {
            window.location.href = href;
        }
    }
});
