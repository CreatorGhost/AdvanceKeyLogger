/* ============================================================
   WebSocket Client for Dashboard Real-time Updates
   ============================================================ */

class DashboardWebSocket {
    constructor(options = {}) {
        this.url = options.url || this._buildWsUrl('/ws/dashboard');
        this.reconnectInterval = options.reconnectInterval || 5000;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        this.reconnectAttempts = 0;
        this.socket = null;
        this.handlers = {};
        this.connected = false;
        this.connecting = false;

        // Bind methods
        this._onOpen = this._onOpen.bind(this);
        this._onClose = this._onClose.bind(this);
        this._onError = this._onError.bind(this);
        this._onMessage = this._onMessage.bind(this);
    }

    _buildWsUrl(path) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        let url = `${protocol}//${window.location.host}${path}`;

        // Extract session_token cookie and pass as query param for WS auth
        const match = document.cookie.match(/(?:^|;\s*)session_token=([^;]*)/);
        if (match) {
            url += `?token=${encodeURIComponent(match[1])}`;
        }

        return url;
    }

    connect() {
        if (this.connected || this.connecting) {
            console.log('[WS] Already connected or connecting');
            return;
        }

        this.connecting = true;
        console.log(`[WS] Connecting to ${this.url}...`);

        try {
            this.socket = new WebSocket(this.url);
            this.socket.onopen = this._onOpen;
            this.socket.onclose = this._onClose;
            this.socket.onerror = this._onError;
            this.socket.onmessage = this._onMessage;
        } catch (error) {
            console.error('[WS] Connection error:', error);
            this.connecting = false;
            this._scheduleReconnect();
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
        this.connected = false;
        this.connecting = false;
    }

    send(action, data = {}) {
        if (!this.connected || !this.socket) {
            console.warn('[WS] Cannot send - not connected');
            return false;
        }

        // Backend expects {"action": "...", ...fields} at top level
        const message = JSON.stringify({ action, ...data });
        try {
            this.socket.send(message);
            return true;
        } catch (error) {
            console.error('[WS] Send error:', error);
            return false;
        }
    }

    on(messageType, handler) {
        if (!this.handlers[messageType]) {
            this.handlers[messageType] = [];
        }
        this.handlers[messageType].push(handler);
    }

    off(messageType, handler) {
        if (this.handlers[messageType]) {
            this.handlers[messageType] = this.handlers[messageType].filter(h => h !== handler);
        }
    }

    _onOpen(event) {
        console.log('[WS] Connected');
        this.connected = true;
        this.connecting = false;
        this.reconnectAttempts = 0;
        this._emit('connected', { event });

        // Request initial status
        this.send('get_status');
    }

    _onClose(event) {
        console.log(`[WS] Disconnected (code: ${event.code})`);
        this.connected = false;
        this.connecting = false;
        this._emit('disconnected', { event });
        this._scheduleReconnect();
    }

    _onError(event) {
        console.error('[WS] Error:', event);
        this._emit('error', { event });
    }

    _onMessage(event) {
        try {
            const message = JSON.parse(event.data);
            const type = message.type;
            const data = message.data || message;

            console.debug(`[WS] Received: ${type}`, data);

            // Emit to specific handlers
            this._emit(type, data);

            // Also emit to 'message' for catch-all handling
            this._emit('message', { type, data });

        } catch (error) {
            console.error('[WS] Failed to parse message:', error, event.data);
        }
    }

    _emit(type, data) {
        const handlers = this.handlers[type] || [];
        handlers.forEach(handler => {
            try {
                handler(data);
            } catch (error) {
                console.error(`[WS] Handler error for ${type}:`, error);
            }
        });
    }

    _scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('[WS] Max reconnect attempts reached');
            this._emit('max_reconnects', {});
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectInterval * Math.min(this.reconnectAttempts, 5);
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        setTimeout(() => {
            if (!this.connected && !this.connecting) {
                this.connect();
            }
        }, delay);
    }
}

// Dashboard-specific WebSocket handlers
class LiveDashboard {
    constructor() {
        this.ws = new DashboardWebSocket();
        this._agents = {};
        this._statusInterval = null;
        this._setupHandlers();
    }

    init() {
        this.ws.connect();
        // Poll for status every 30 seconds to keep resources panel updated
        this._statusInterval = setInterval(() => {
            if (this.ws.connected) {
                this.requestStatus();
            }
        }, 30000);
    }

    _setupHandlers() {
        // Connection status
        this.ws.on('connected', () => {
            this._updateConnectionStatus(true);
        });

        this.ws.on('disconnected', () => {
            this._updateConnectionStatus(false);
        });

        // Agent status updates
        this.ws.on('agent_status', (data) => {
            this._handleAgentStatus(data);
        });

        // New capture data
        this.ws.on('new_capture', (data) => {
            this._handleNewCapture(data);
        });

        // Command results
        this.ws.on('command_result', (data) => {
            this._handleCommandResult(data);
        });

        // Status response
        this.ws.on('status', (data) => {
            this._handleStatusResponse(data);
        });

        // Captures response (from get_captures action)
        this.ws.on('captures', (data) => {
            this._handleCapturesResponse(data);
        });
    }

    _updateConnectionStatus(connected) {
        const indicator = document.getElementById('wsStatus');
        if (indicator) {
            indicator.classList.toggle('connected', connected);
            indicator.classList.toggle('disconnected', !connected);
            indicator.title = connected ? 'Real-time updates active' : 'Disconnected';
        }

        // Update any "live" badge
        const liveBadge = document.getElementById('liveBadge');
        if (liveBadge) {
            liveBadge.style.display = connected ? 'inline-flex' : 'none';
        }
    }

    _handleAgentStatus(data) {
        console.log('[Live] Agent status:', data);

        // Extract status string — data.status may be a dict or string
        const statusObj = data.status || {};
        const statusStr = (typeof statusObj === 'string')
            ? statusObj
            : (statusObj.status || 'ONLINE');

        // Track agent in local state
        this._agents[data.agent_id] = {
            status: statusStr,
            last_seen: data.timestamp || Date.now() / 1000
        };

        // Re-render agents list
        const agentsList = document.getElementById('agentsList');
        if (agentsList) {
            this._renderAgentsList(agentsList);
        }

        // Update connected agents count
        this._updateConnectedAgentsCount();

        // Update existing agent row in fleet table if visible
        const agentRow = document.querySelector(`[data-agent-id="${CSS.escape(data.agent_id)}"]`);
        if (agentRow) {
            const statusCell = agentRow.querySelector('.agent-status');
            if (statusCell) {
                statusCell.textContent = statusStr;
                statusCell.className = `agent-status status-${statusStr.toLowerCase()}`;
            }

            const lastSeenCell = agentRow.querySelector('.agent-last-seen');
            if (lastSeenCell) {
                lastSeenCell.textContent = 'just now';
            }
        }

        // Show notification for status changes
        if (statusStr === 'OFFLINE') {
            this._showNotification(`Agent ${data.agent_id} went offline`, 'warning');
        } else if (statusStr === 'ONLINE') {
            this._showNotification(`Agent ${data.agent_id} is now online`, 'success');
        }
    }

    _handleNewCapture(data) {
        console.log('[Live] New capture:', data);

        // Prepend to activity table
        const tbody = document.getElementById('activityBody');
        if (tbody) {
            const row = document.createElement('tr');
            row.className = 'new-row';
            row.innerHTML = `
                <td><span class="event-dot dot-neutral"></span>${this._escapeHtml(data.capture_type || 'event')}</td>
                <td class="detail-cell">${this._escapeHtml(this._truncate(data.data || '', 60))}</td>
                <td class="time-cell">now</td>
            `;
            tbody.insertBefore(row, tbody.firstChild);

            // Remove animation class after animation completes
            setTimeout(() => row.classList.remove('new-row'), 1000);

            // Limit rows
            while (tbody.children.length > 10) {
                tbody.removeChild(tbody.lastChild);
            }
        }

        // Update capture count
        const totalCaptures = document.getElementById('totalCaptures');
        if (totalCaptures) {
            const current = parseInt(totalCaptures.textContent.replace(/,/g, '')) || 0;
            totalCaptures.textContent = this._formatNumber(current + 1);
        }

        // Update pending count if capture is pending
        if (data.status === 'pending') {
            const pendingCount = document.getElementById('pendingCount');
            if (pendingCount) {
                const current = parseInt(pendingCount.textContent.replace(/,/g, '')) || 0;
                pendingCount.textContent = this._formatNumber(current + 1);
            }
        }
    }

    _handleCommandResult(data) {
        console.log('[Live] Command result:', data);

        // Update command status in UI if visible
        const cmdId = data.command_id || '';
        const cmdRow = cmdId ? document.querySelector(`[data-command-id="${CSS.escape(cmdId)}"]`) : null;
        if (cmdRow) {
            const statusCell = cmdRow.querySelector('.command-status');
            if (statusCell) {
                statusCell.textContent = data.success ? 'Completed' : 'Failed';
                statusCell.className = `command-status status-${data.success ? 'completed' : 'failed'}`;
            }
        }

        // Show notification
        this._showNotification(
            `Command ${data.command_id} ${data.success ? 'completed' : 'failed'}`,
            data.success ? 'success' : 'error'
        );
    }

    _handleStatusResponse(data) {
        console.log('[Live] Status response:', data);

        // data = { clients: N, agents: { id: { connected: bool, last_seen: T }, ... }, system: {...}, timestamp: T }
        if (data.agents && typeof data.agents === 'object') {
            // Populate local agent state from status response
            for (const [agentId, info] of Object.entries(data.agents)) {
                this._agents[agentId] = {
                    status: info.connected ? 'ONLINE' : 'OFFLINE',
                    last_seen: info.last_seen || 0
                };
            }

            // Update connected agents count
            this._updateConnectedAgentsCount();

            // Re-render agents list
            const agentsList = document.getElementById('agentsList');
            if (agentsList) {
                this._renderAgentsList(agentsList);
            }
        }

        // Update resources panel from system metrics
        if (data.system) {
            this._updateResources(data.system);
        }
    }

    _handleCapturesResponse(data) {
        console.log('[Live] Captures response:', data);

        // Update captures list/table if visible
        const capturesList = document.getElementById('capturesList');
        if (capturesList && Array.isArray(data)) {
            capturesList.innerHTML = '';
            data.forEach(capture => {
                const item = document.createElement('div');
                item.className = 'capture-item';
                item.innerHTML = `
                    <span class="capture-type">${this._escapeHtml(capture.type || 'unknown')}</span>
                    <span class="capture-time">${new Date(Number(capture.timestamp) * 1000).toLocaleTimeString()}</span>
                    <span class="capture-agent">${this._escapeHtml(capture.agent_id || 'local')}</span>
                `;
                capturesList.appendChild(item);
            });
        }

        // Update total count
        const totalCaptures = document.getElementById('totalCaptures');
        if (totalCaptures && Array.isArray(data)) {
            totalCaptures.textContent = this._formatNumber(data.length);
        }
    }

    _showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `ws-notification ws-notification-${type}`;
        notification.textContent = message;

        // Add to container (create if doesn't exist)
        let container = document.getElementById('wsNotifications');
        if (!container) {
            container = document.createElement('div');
            container.id = 'wsNotifications';
            container.className = 'ws-notifications-container';
            document.body.appendChild(container);
        }

        container.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            notification.classList.add('ws-notification-fadeout');
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }

    _escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    _truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.substring(0, max) + '...' : str;
    }

    _formatNumber(num) {
        return new Intl.NumberFormat().format(num);
    }

    _renderAgentsList(container) {
        const agentIds = Object.keys(this._agents);
        if (agentIds.length === 0) {
            container.innerHTML = '<div class="empty-state-sm">No agents connected</div>';
            return;
        }

        container.innerHTML = '';
        for (const agentId of agentIds) {
            const info = this._agents[agentId];
            const statusClass = (info.status || '').toLowerCase() === 'online' ? 'online' : 'offline';
            const el = document.createElement('div');
            el.className = 'agent-item';
            el.setAttribute('data-agent-id', agentId);
            el.innerHTML = `
                <span class="agent-status-dot status-dot-${statusClass}"></span>
                <span class="agent-name">${this._escapeHtml(agentId)}</span>
                <span class="agent-badge agent-badge-${statusClass}">${this._escapeHtml(info.status || 'UNKNOWN')}</span>
            `;
            container.appendChild(el);
        }
    }

    _updateConnectedAgentsCount() {
        const count = Object.values(this._agents).filter(a =>
            (a.status || '').toUpperCase() === 'ONLINE'
        ).length;
        const el = document.getElementById('connectedAgents');
        if (el) {
            el.textContent = count;
        }
    }

    _updateResources(system) {
        if (system.cpu_percent !== undefined) {
            const el = document.getElementById('resCpu');
            const bar = document.getElementById('resCpuBar');
            if (el) el.textContent = system.cpu_percent.toFixed(1) + '%';
            if (bar) bar.style.width = Math.min(system.cpu_percent, 100) + '%';
        }
        if (system.memory_percent !== undefined) {
            const el = document.getElementById('resMemory');
            const bar = document.getElementById('resMemoryBar');
            if (el) el.textContent = system.memory_percent.toFixed(1) + '%';
            if (bar) bar.style.width = Math.min(system.memory_percent, 100) + '%';
        }
        if (system.disk_percent !== undefined) {
            const el = document.getElementById('resStorage');
            const bar = document.getElementById('resStorageBar');
            if (el) el.textContent = system.disk_percent.toFixed(1) + '%';
            if (bar) bar.style.width = Math.min(system.disk_percent, 100) + '%';
        }
    }

    // Public API for sending commands
    sendCommand(agentId, action, parameters = {}) {
        return this.ws.send('command', {
            agent_id: agentId,
            action_type: action,
            parameters: parameters
        });
    }

    broadcastCommand(action, parameters = {}) {
        return this.ws.send('broadcast', {
            message: JSON.stringify({ action: action, parameters: parameters })
        });
    }

    requestStatus() {
        return this.ws.send('get_status');
    }

    requestCaptures(limit = 10) {
        return this.ws.send('get_captures', { limit });
    }
}

// CSS for WebSocket notifications (inject if not present)
(function injectStyles() {
    if (document.getElementById('ws-client-styles')) return;

    const style = document.createElement('style');
    style.id = 'ws-client-styles';
    style.textContent = `
        .ws-notifications-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .ws-notification {
            padding: 12px 16px;
            border-radius: 6px;
            background: #1a1a1a;
            color: #fff;
            font-size: 14px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            animation: ws-slide-in 0.3s ease;
        }

        .ws-notification-success {
            border-left: 3px solid #10b981;
        }

        .ws-notification-warning {
            border-left: 3px solid #f59e0b;
        }

        .ws-notification-error {
            border-left: 3px solid #ef4444;
        }

        .ws-notification-info {
            border-left: 3px solid #3b82f6;
        }

        .ws-notification-fadeout {
            animation: ws-fade-out 0.3s ease forwards;
        }

        @keyframes ws-slide-in {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        @keyframes ws-fade-out {
            from {
                opacity: 1;
            }
            to {
                opacity: 0;
            }
        }

        .new-row {
            animation: highlight-row 1s ease;
        }

        @keyframes highlight-row {
            from {
                background-color: rgba(59, 130, 246, 0.2);
            }
            to {
                background-color: transparent;
            }
        }

        #wsStatus {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
        }

        #wsStatus.connected {
            background-color: #10b981;
        }

        #wsStatus.disconnected {
            background-color: #6b7280;
        }

        #liveBadge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 2px 8px;
            background: rgba(16, 185, 129, 0.1);
            color: #10b981;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 500;
        }

        #liveBadge::before {
            content: '';
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #10b981;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% {
                opacity: 1;
            }
            50% {
                opacity: 0.5;
            }
        }
    `;
    document.head.appendChild(style);
})();

// Global instance
let liveDashboard = null;

// Auto-init on DOM ready if on live page
document.addEventListener('DOMContentLoaded', () => {
    // Check if we're on a page that should use WebSocket
    const isLivePage = window.location.pathname.includes('/live') ||
                       document.body.dataset.enableWebsocket === 'true';

    if (isLivePage && !liveDashboard) {
        liveDashboard = new LiveDashboard();
        // Also expose on window so inline template scripts (live.html) can access it
        window.liveDashboard = liveDashboard;
        liveDashboard.init();
        console.log('[WS] Live dashboard initialized');
    }
});

// Export for use in other scripts
window.DashboardWebSocket = DashboardWebSocket;
window.LiveDashboard = LiveDashboard;
window.getLiveDashboard = () => liveDashboard;
