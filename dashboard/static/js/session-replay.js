/* ============================================================
   Session Replay Player — Vercel Design
   
   Loads timeline data (frames + events) from the API and plays
   them back with a scrub bar, speed control, and input overlays
   (mouse cursor, click ripples, keystrokes, window titles).
   ============================================================ */

class SessionReplayPlayer {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.frames = [];
        this.events = [];
        this.session = null;
        this.duration = 0;

        // Playback state
        this.playing = false;
        this.currentTime = 0;  // seconds from session start
        this.speed = 1.0;
        this.frameIndex = 0;
        this.eventIndex = 0;
        this.animFrame = null;
        this.lastTick = 0;

        // Keystroke buffer for overlay
        this._keystrokeBuffer = '';
        this._keystrokeClearTimer = null;

        // DOM refs (populated in init)
        this.$ = {};
    }

    async init() {
        this._bindDOM();
        this._bindEvents();
        await this._loadTimeline();
    }

    // ------------------------------------------------------------------
    // DOM binding
    // ------------------------------------------------------------------

    _bindDOM() {
        const q = (id) => document.getElementById(id);
        this.$ = {
            screenImage: q('screenImage'),
            screenPlaceholder: q('screenPlaceholder'),
            cursorOverlay: q('cursorOverlay'),
            clickRipple: q('clickRipple'),
            keystrokeOverlay: q('keystrokeOverlay'),
            windowOverlay: q('windowOverlay'),
            scrubBar: q('scrubBar'),
            currentTime: q('currentTime'),
            totalTime: q('totalTime'),
            btnPlay: q('btnPlay'),
            btnStop: q('btnStop'),
            btnPrev: q('btnPrev'),
            btnNext: q('btnNext'),
            iconPlay: q('iconPlay'),
            iconPause: q('iconPause'),
            speedSelect: q('speedSelect'),
            frameInfo: q('frameInfo'),
            sessionMeta: q('sessionMeta'),
            eventLogBody: q('eventLogBody'),
            eventCountBadge: q('eventCountBadge'),
            screenContainer: q('screenContainer'),
        };
    }

    _bindEvents() {
        this.$.btnPlay.addEventListener('click', () => this.togglePlay());
        this.$.btnStop.addEventListener('click', () => this.stop());
        this.$.btnPrev.addEventListener('click', () => this.prevFrame());
        this.$.btnNext.addEventListener('click', () => this.nextFrame());
        this.$.speedSelect.addEventListener('change', (e) => {
            this.speed = parseFloat(e.target.value);
        });
        this.$.scrubBar.addEventListener('input', (e) => {
            this.seekTo(parseFloat(e.target.value));
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
            switch (e.key) {
                case ' ': e.preventDefault(); this.togglePlay(); break;
                case 'ArrowLeft': this.prevFrame(); break;
                case 'ArrowRight': this.nextFrame(); break;
                case 'Home': this.seekTo(0); break;
                case 'End': this.seekTo(this.duration); break;
            }
        });
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------

    async _loadTimeline() {
        const data = await apiFetch(`/api/sessions/${this.sessionId}/timeline`);
        if (!data || !data.session) {
            this.$.screenPlaceholder.textContent = 'Session not found.';
            return;
        }

        this.session = data.session;
        this.frames = data.frames || [];
        this.events = data.events || [];
        this.duration = data.session.duration || 0;

        // Update UI
        this.$.scrubBar.max = this.duration;
        this.$.totalTime.textContent = this._formatTime(this.duration);
        this.$.sessionMeta.innerHTML =
            `${this.frames.length} frames &middot; ${this.events.length} events &middot; ${this._formatTime(this.duration)}`;
        this.$.eventCountBadge.textContent = this.events.length;

        // Populate event log
        this._renderEventLog();

        // Show first frame
        if (this.frames.length > 0) {
            this._showFrame(0);
            this.$.screenPlaceholder.style.display = 'none';
            this.$.screenImage.style.display = 'block';
        } else {
            this.$.screenPlaceholder.textContent = 'No frames captured in this session.';
        }
    }

    // ------------------------------------------------------------------
    // Playback controls
    // ------------------------------------------------------------------

    togglePlay() {
        if (this.playing) {
            this.pause();
        } else {
            this.play();
        }
    }

    play() {
        if (this.frames.length === 0) return;
        if (this.currentTime >= this.duration) {
            this.seekTo(0);
        }
        this.playing = true;
        this.lastTick = performance.now();
        this.$.iconPlay.style.display = 'none';
        this.$.iconPause.style.display = 'block';
        this._tick();
    }

    pause() {
        this.playing = false;
        this.$.iconPlay.style.display = 'block';
        this.$.iconPause.style.display = 'none';
        if (this.animFrame) {
            cancelAnimationFrame(this.animFrame);
            this.animFrame = null;
        }
    }

    stop() {
        this.pause();
        this.seekTo(0);
    }

    seekTo(time) {
        this.currentTime = Math.max(0, Math.min(time, this.duration));
        this._updateScrubBar();

        // Find the right frame
        this.frameIndex = this._findFrameAt(this.currentTime);
        this._showFrame(this.frameIndex);

        // Reset event pointer
        this.eventIndex = this._findEventAt(this.currentTime);

        // Clear overlays
        this._keystrokeBuffer = '';
        this.$.keystrokeOverlay.style.display = 'none';
        this.$.cursorOverlay.style.display = 'none';
    }

    prevFrame() {
        if (this.frameIndex > 0) {
            this.frameIndex--;
            this._showFrame(this.frameIndex);
            this.currentTime = this.frames[this.frameIndex].offset_sec;
            this._updateScrubBar();
        }
    }

    nextFrame() {
        if (this.frameIndex < this.frames.length - 1) {
            this.frameIndex++;
            this._showFrame(this.frameIndex);
            this.currentTime = this.frames[this.frameIndex].offset_sec;
            this._updateScrubBar();
        }
    }

    // ------------------------------------------------------------------
    // Tick loop (requestAnimationFrame)
    // ------------------------------------------------------------------

    _tick() {
        if (!this.playing) return;

        const now = performance.now();
        const delta = ((now - this.lastTick) / 1000) * this.speed;
        this.lastTick = now;

        this.currentTime += delta;

        if (this.currentTime >= this.duration) {
            this.currentTime = this.duration;
            this.pause();
            return;
        }

        // Update frame if needed
        const targetFrame = this._findFrameAt(this.currentTime);
        if (targetFrame !== this.frameIndex) {
            this.frameIndex = targetFrame;
            this._showFrame(this.frameIndex);
        }

        // Process events up to current time
        this._processEventsUpTo(this.currentTime);

        this._updateScrubBar();

        this.animFrame = requestAnimationFrame(() => this._tick());
    }

    // ------------------------------------------------------------------
    // Frame display
    // ------------------------------------------------------------------

    _showFrame(index) {
        if (index < 0 || index >= this.frames.length) return;
        const frame = this.frames[index];
        this.$.screenImage.src = frame.url;
        this.$.frameInfo.textContent = `Frame ${index + 1}/${this.frames.length} [${frame.trigger}]`;
    }

    _findFrameAt(time) {
        // Binary search for the latest frame at or before `time`
        let lo = 0, hi = this.frames.length - 1, result = 0;
        while (lo <= hi) {
            const mid = (lo + hi) >> 1;
            if (this.frames[mid].offset_sec <= time) {
                result = mid;
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        return result;
    }

    _findEventAt(time) {
        let lo = 0, hi = this.events.length - 1, result = 0;
        while (lo <= hi) {
            const mid = (lo + hi) >> 1;
            if (this.events[mid].offset_sec <= time) {
                result = mid + 1;
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        return result;
    }

    // ------------------------------------------------------------------
    // Event processing during playback
    // ------------------------------------------------------------------

    _processEventsUpTo(time) {
        while (this.eventIndex < this.events.length &&
               this.events[this.eventIndex].offset_sec <= time) {
            const ev = this.events[this.eventIndex];
            this._handleEvent(ev);
            this.eventIndex++;
        }
    }

    _handleEvent(ev) {
        const type = ev.event_type;
        let data = ev.data;
        if (typeof data === 'string') {
            try { data = JSON.parse(data); } catch (_e) { /* keep as string */ }
        }

        if (type === 'mouse_click' || type === 'mouse_move') {
            this._showCursor(data);
            if (type === 'mouse_click') {
                this._showClickRipple(data);
            }
        } else if (type === 'keystroke') {
            this._showKeystroke(typeof data === 'string' ? data : (data.key || ''));
        } else if (type === 'window') {
            this._showWindow(typeof data === 'string' ? data : (data.title || ''));
        }
    }

    _showCursor(data) {
        if (!data || data.x === undefined) return;
        const container = this.$.screenContainer;
        const img = this.$.screenImage;
        if (!img.naturalWidth) return;

        // Scale cursor position to displayed image size
        const rect = img.getBoundingClientRect();
        const scaleX = rect.width / (img.naturalWidth || 1);
        const scaleY = rect.height / (img.naturalHeight || 1);
        const offsetLeft = img.offsetLeft;
        const offsetTop = img.offsetTop;

        const x = offsetLeft + data.x * scaleX;
        const y = offsetTop + data.y * scaleY;

        const cursor = this.$.cursorOverlay;
        cursor.style.left = x + 'px';
        cursor.style.top = y + 'px';
        cursor.style.display = 'block';
    }

    _showClickRipple(data) {
        if (!data || data.x === undefined) return;
        const img = this.$.screenImage;
        if (!img.naturalWidth) return;

        const rect = img.getBoundingClientRect();
        const scaleX = rect.width / (img.naturalWidth || 1);
        const scaleY = rect.height / (img.naturalHeight || 1);

        const x = img.offsetLeft + data.x * scaleX;
        const y = img.offsetTop + data.y * scaleY;

        const ripple = this.$.clickRipple;
        ripple.style.left = x + 'px';
        ripple.style.top = y + 'px';
        ripple.style.display = 'block';
        ripple.classList.remove('click-ripple-anim');
        // Force reflow to restart animation
        void ripple.offsetWidth;
        ripple.classList.add('click-ripple-anim');
        setTimeout(() => { ripple.style.display = 'none'; }, 400);
    }

    _showKeystroke(key) {
        this._keystrokeBuffer += key;
        // Trim to last 80 chars
        if (this._keystrokeBuffer.length > 80) {
            this._keystrokeBuffer = this._keystrokeBuffer.slice(-80);
        }
        this.$.keystrokeOverlay.textContent = this._keystrokeBuffer;
        this.$.keystrokeOverlay.style.display = 'block';

        // Clear after 3 seconds of no new keystrokes
        clearTimeout(this._keystrokeClearTimer);
        this._keystrokeClearTimer = setTimeout(() => {
            this.$.keystrokeOverlay.style.display = 'none';
            this._keystrokeBuffer = '';
        }, 3000);
    }

    _showWindow(title) {
        if (!title) return;
        this.$.windowOverlay.textContent = title;
        this.$.windowOverlay.style.display = 'block';
    }

    // ------------------------------------------------------------------
    // UI updates
    // ------------------------------------------------------------------

    _updateScrubBar() {
        this.$.scrubBar.value = this.currentTime;
        this.$.currentTime.textContent = this._formatTime(this.currentTime);
    }

    _formatTime(sec) {
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    _renderEventLog() {
        const tbody = this.$.eventLogBody;
        tbody.innerHTML = '';

        // Show up to 500 events in the log
        const maxShow = Math.min(this.events.length, 500);
        for (let i = 0; i < maxShow; i++) {
            const ev = this.events[i];
            const tr = document.createElement('tr');

            const tdTime = document.createElement('td');
            tdTime.style.fontFamily = 'var(--font-mono)';
            tdTime.style.whiteSpace = 'nowrap';
            tdTime.textContent = this._formatTime(ev.offset_sec);
            tdTime.style.cursor = 'pointer';
            tdTime.title = 'Click to seek';
            tdTime.addEventListener('click', () => {
                this.seekTo(ev.offset_sec);
            });

            const tdType = document.createElement('td');
            tdType.textContent = ev.event_type;

            const tdData = document.createElement('td');
            tdData.style.maxWidth = '300px';
            tdData.style.overflow = 'hidden';
            tdData.style.textOverflow = 'ellipsis';
            tdData.style.whiteSpace = 'nowrap';
            let dataStr = ev.data;
            if (typeof dataStr === 'string' && dataStr.length > 60) {
                dataStr = dataStr.substring(0, 60) + '...';
            }
            tdData.textContent = dataStr;

            tr.appendChild(tdTime);
            tr.appendChild(tdType);
            tr.appendChild(tdData);
            tbody.appendChild(tr);
        }

        if (this.events.length > maxShow) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 3;
            td.style.textAlign = 'center';
            td.style.color = 'var(--text-tertiary)';
            td.textContent = `... and ${this.events.length - maxShow} more events`;
            tr.appendChild(td);
            tbody.appendChild(tr);
        }
    }
}

// ------------------------------------------------------------------
// Initialize on page load
// ------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    const sessionId = window.__SESSION_ID__;
    if (!sessionId) {
        console.error('No session ID provided');
        return;
    }
    const player = new SessionReplayPlayer(sessionId);
    window.replayPlayer = player;
    player.init();
});
