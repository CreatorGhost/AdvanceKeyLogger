/* ============================================================
   Settings Page JS
   ============================================================ */

function escapeHtml(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    loadSettings().catch(console.error);

    document.getElementById('copyConfig').addEventListener('click', copyRawConfig);
});

async function loadSettings() {
    const data = await apiFetch('/api/config');
    if (!data || !data.config) return;

    const config = data.config;

    renderSettingsGroup('captureSettings', config.capture || {});
    renderSettingsGroup('transportSettings', config.transport || {});
    renderSettingsGroup('generalSettings', config.general || {});
    renderStorageSettings(config);
    renderRawConfig(config);
}

function renderSettingsGroup(elementId, obj, prefix = '') {
    const el = document.getElementById(elementId);
    if (!el) return;

    const items = flattenObject(obj, prefix);
    if (items.length === 0) {
        el.innerHTML = '<div class="empty-state-sm">No settings available</div>';
        return;
    }

    el.innerHTML = items.map(([key, value]) => {
        let valueClass = 'setting-value';
        let displayValue = formatSettingValue(value);

        if (value === true) valueClass += ' bool-true';
        else if (value === false) valueClass += ' bool-false';

        return `
            <div class="setting-item">
                <span class="setting-key">${escapeHtml(key)}</span>
                <span class="${valueClass}">${escapeHtml(displayValue)}</span>
            </div>
        `;
    }).join('');
}

function renderStorageSettings(config) {
    const combined = {};
    if (config.storage) Object.assign(combined, flattenToObj(config.storage, 'storage'));
    if (config.encryption) Object.assign(combined, flattenToObj(config.encryption, 'encryption'));
    if (config.compression) Object.assign(combined, flattenToObj(config.compression, 'compression'));

    const el = document.getElementById('storageSettings');
    const items = Object.entries(combined);

    if (items.length === 0) {
        el.innerHTML = '<div class="empty-state-sm">No settings available</div>';
        return;
    }

    el.innerHTML = items.map(([key, value]) => {
        let valueClass = 'setting-value';
        let displayValue = formatSettingValue(value);
        if (value === true) valueClass += ' bool-true';
        else if (value === false) valueClass += ' bool-false';

        return `
            <div class="setting-item">
                <span class="setting-key">${escapeHtml(key)}</span>
                <span class="${valueClass}">${escapeHtml(displayValue)}</span>
            </div>
        `;
    }).join('');
}

function renderRawConfig(config) {
    const el = document.getElementById('rawConfig');
    el.textContent = yamlStringify(config, 0);
}

function flattenObject(obj, prefix = '') {
    const result = [];
    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
            result.push(...flattenObject(value, fullKey));
        } else {
            result.push([fullKey, value]);
        }
    }
    return result;
}

function flattenToObj(obj, prefix = '') {
    const result = {};
    for (const [key, value] of flattenObject(obj, prefix)) {
        result[key] = value;
    }
    return result;
}

function formatSettingValue(value) {
    if (value === true) return 'true';
    if (value === false) return 'false';
    if (value === null || value === undefined) return 'null';
    if (Array.isArray(value)) return value.length > 0 ? value.join(', ') : '[]';
    if (typeof value === 'string' && value === '') return '(empty)';
    return String(value);
}

function yamlStringify(obj, indent) {
    let result = '';
    const pad = '  '.repeat(indent);

    for (const [key, value] of Object.entries(obj)) {
        if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
            result += `${pad}${key}:\n${yamlStringify(value, indent + 1)}`;
        } else if (Array.isArray(value)) {
            result += `${pad}${key}:\n`;
            for (const item of value) {
                result += `${pad}  - ${item}\n`;
            }
        } else {
            let display = value;
            if (typeof value === 'string') display = `"${value}"`;
            result += `${pad}${key}: ${display}\n`;
        }
    }
    return result;
}

async function copyRawConfig() {
    const raw = document.getElementById('rawConfig').textContent;
    try {
        await navigator.clipboard.writeText(raw);
        const btn = document.getElementById('copyConfig');
        const original = btn.innerHTML;
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Copied!';
        setTimeout(() => { btn.innerHTML = original; }, 2000);
    } catch {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = raw;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    }
}
