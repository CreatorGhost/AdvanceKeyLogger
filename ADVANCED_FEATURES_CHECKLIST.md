# Advanced Features Checklist

Generated: 2026-02-08
Priority: Ordered by impact on GitHub stars and project quality.

---

## Feature 1: Web Dashboard

**Directory:** `dashboard/`
**Dependencies:** `fastapi`, `uvicorn`, `jinja2`, `websockets`
**Priority:** HIGH — Visual projects get 10x more stars

### Backend Features
- [ ] FastAPI application with auto-generated OpenAPI/Swagger docs
- [ ] Token-based authentication (JWT) — login required to view dashboard
- [ ] WebSocket endpoint for real-time live data push to browser
- [ ] Session management — list active/past monitoring sessions
- [ ] Role-based access: admin (full control) vs viewer (read-only)

### API Endpoints
- [ ] `POST /api/auth/login` — authenticate, return JWT token
- [ ] `POST /api/auth/logout` — invalidate token
- [ ] `GET /api/status` — system status (uptime, active modules, storage usage, queue depth)
- [ ] `GET /api/captures` — paginated list of all captures (filterable by type, date range)
- [ ] `GET /api/captures/{id}` — single capture detail
- [ ] `GET /api/screenshots` — paginated screenshot list with thumbnails
- [ ] `GET /api/screenshots/{id}` — full-size screenshot image
- [ ] `GET /api/keystrokes` — keystroke log with pagination and search
- [ ] `GET /api/clipboard` — clipboard history
- [ ] `GET /api/windows` — window activity timeline
- [ ] `GET /api/analytics/wpm` — words-per-minute over time
- [ ] `GET /api/analytics/activity` — activity heatmap data (hour x day-of-week)
- [ ] `GET /api/analytics/apps` — top applications by time spent
- [ ] `GET /api/analytics/summary` — daily/weekly/monthly summary stats
- [ ] `POST /api/config` — update configuration at runtime
- [ ] `GET /api/config` — current running configuration
- [ ] `POST /api/control/start` — start capture modules
- [ ] `POST /api/control/stop` — stop capture modules
- [ ] `GET /api/export/{format}` — export data (json, csv, html)
- [ ] `GET /api/health` — health check for monitoring/load balancers
- [ ] `WS /ws/live` — WebSocket for real-time keystroke/event streaming

### Dashboard Pages/Views
- [ ] Login page
- [ ] Overview/home — system status, quick stats, recent activity
- [ ] Keystroke viewer — searchable, filterable log
- [ ] Screenshot gallery — grid view with lightbox
- [ ] Clipboard history — searchable list
- [ ] Window timeline — visual timeline of app usage
- [ ] Analytics — charts for WPM, activity heatmap, top apps
- [ ] Settings — configure modules, transports, intervals
- [ ] Export — download reports in various formats
- [ ] Live view — real-time stream of incoming events

### Files to Create
```
dashboard/
  __init__.py
  app.py              — FastAPI app factory, CORS, middleware
  auth.py             — JWT token creation/validation, login logic
  routes/
    __init__.py
    status.py          — /api/status, /api/health
    captures.py        — /api/captures, /api/keystrokes, /api/clipboard, /api/windows
    screenshots.py     — /api/screenshots
    analytics.py       — /api/analytics/*
    config.py          — /api/config
    control.py         — /api/control/*
    export.py          — /api/export/*
    websocket.py       — /ws/live
  models.py            — Pydantic request/response schemas
  dependencies.py      — FastAPI dependencies (get_db, get_current_user)
  templates/           — Jinja2 HTML templates (your design)
  static/              — CSS, JS, images (your design)
```

### Config Additions (default_config.yaml)
```yaml
dashboard:
  enabled: false
  host: "127.0.0.1"
  port: 8080
  secret_key: "change-me-in-production"
  token_expiry_minutes: 60
  admin_username: "admin"
  admin_password_hash: ""
  cors_origins: ["http://localhost:3000"]
```

### Tests
- [ ] `tests/test_dashboard_auth.py` — login, JWT validation, expired token, wrong password
- [ ] `tests/test_dashboard_api.py` — all endpoint status codes, pagination, filters
- [ ] `tests/test_dashboard_websocket.py` — WebSocket connect, receive events, auth required

---

## Feature 2: Docker Support

**Directory:** project root
**Dependencies:** Docker, docker-compose
**Priority:** HIGH — One-command setup drives adoption

### Checklist
- [ ] `Dockerfile` — Multi-stage build (builder + runtime), non-root user, minimal image
- [ ] `docker-compose.yml` — Main service + optional Grafana + InfluxDB
- [ ] `.dockerignore` — Exclude .git, __pycache__, .env, tests, docs
- [ ] Health check in Dockerfile (`HEALTHCHECK CMD`)
- [ ] Environment variable passthrough for all config options
- [ ] Volume mount for persistent data directory and SQLite database
- [ ] Volume mount for config overrides (user_config.yaml)
- [ ] Named volumes for screenshots and logs
- [ ] Configurable UID/GID for file permissions
- [ ] `docker-compose.override.yml.example` — development overrides template

### Files to Create
```
Dockerfile
docker-compose.yml
docker-compose.override.yml.example
.dockerignore
scripts/
  docker-entrypoint.sh    — startup script: validate config, run migrations, launch
```

### Dockerfile Requirements
- Base image: `python:3.12-slim`
- Install only production dependencies (not dev)
- Run as non-root user `appuser`
- Expose port 8080 (dashboard)
- Set `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`
- Default CMD: `python -m main --config /app/config/user_config.yaml`

### docker-compose.yml Services
- `app` — main application with dashboard
- `grafana` (optional profile) — pre-configured Grafana dashboards
- `influxdb` (optional profile) — time-series metrics storage

---

## Feature 3: Documentation Site (MkDocs)

**Directory:** `docs/`
**Dependencies:** `mkdocs`, `mkdocs-material`, `mkdocstrings[python]`
**Priority:** HIGH — Polished docs = credibility

### Checklist
- [ ] `mkdocs.yml` — MkDocs config with Material theme
- [ ] `docs/index.md` — Landing page with project overview
- [ ] `docs/getting-started/installation.md` — pip, Docker, from source
- [ ] `docs/getting-started/quickstart.md` — 5-minute setup guide
- [ ] `docs/getting-started/configuration.md` — full config reference with every option explained
- [ ] `docs/architecture/overview.md` — system architecture diagram and component descriptions
- [ ] `docs/architecture/plugin-system.md` — how capture/transport registries work
- [ ] `docs/architecture/data-flow.md` — collect -> store -> bundle -> encrypt -> transport pipeline
- [ ] `docs/modules/capture.md` — all 5 capture modules documented
- [ ] `docs/modules/transport.md` — all 4 transport modules documented
- [ ] `docs/modules/storage.md` — StorageManager + SQLiteStorage docs
- [ ] `docs/modules/utils.md` — crypto, compression, resilience, process docs
- [ ] `docs/development/plugin-guide.md` — how to write a custom capture/transport plugin
- [ ] `docs/development/testing.md` — how to run tests, write new tests, fixtures
- [ ] `docs/development/contributing.md` — contribution guidelines, code style, PR process
- [ ] `docs/api-reference/` — auto-generated from docstrings using mkdocstrings
- [ ] `docs/dashboard/` — dashboard features and API endpoint reference
- [ ] `docs/legal/disclaimer.md` — legal usage, ethical guidelines, consent requirements
- [ ] `docs/changelog.md` — version history
- [ ] `docs/faq.md` — common questions and troubleshooting
- [ ] GitHub Pages deployment via GitHub Action on push to main

### Files to Create
```
mkdocs.yml
docs/
  index.md
  getting-started/
    installation.md
    quickstart.md
    configuration.md
  architecture/
    overview.md
    plugin-system.md
    data-flow.md
  modules/
    capture.md
    transport.md
    storage.md
    utils.md
  development/
    plugin-guide.md
    testing.md
    contributing.md
  api-reference/
    (auto-generated)
  dashboard/
    features.md
    api-endpoints.md
  legal/
    disclaimer.md
  changelog.md
  faq.md
```

### GitHub Action Addition
- [ ] `.github/workflows/docs.yml` — build and deploy MkDocs to GitHub Pages on push to main

---

## Feature 4: PyPI Distribution

**Directory:** project root
**Dependencies:** `build`, `twine`, `bump2version`
**Priority:** HIGH — pip install = accessibility

### Checklist
- [ ] Update `pyproject.toml` with full PyPI metadata (classifiers, urls, license, authors)
- [ ] Add `__version__` to `__init__.py` at project root
- [ ] Add `LICENSE` file (MIT recommended for max adoption)
- [ ] `MANIFEST.in` — include default_config.yaml, README, LICENSE in sdist
- [ ] `.bumpversion.cfg` — version bump config for patch/minor/major releases
- [ ] Verify `python -m build` produces clean sdist and wheel
- [ ] Verify `pip install dist/*.whl` works in a fresh venv
- [ ] Entry point works: `advancekeylogger --help` after install
- [ ] GitHub Action for auto-publish to PyPI on tag push (v*)

### Files to Create/Update
```
LICENSE
MANIFEST.in
.bumpversion.cfg
__init__.py                              — add __version__
pyproject.toml                           — update metadata
.github/workflows/publish.yml            — auto-publish on tag
```

---

## Feature 5: Keystroke Analytics & Reports

**Directory:** `analytics/`
**Dependencies:** None (pure Python with stdlib + existing deps)
**Priority:** HIGH — transforms raw logger into productivity tool

### Checklist
- [ ] `analytics/__init__.py`
- [ ] `analytics/engine.py` — main analytics processor

### Metrics to Compute
- [ ] **Words per minute (WPM)** — calculate from keystroke timestamps, rolling average over configurable windows (1min, 5min, 15min)
- [ ] **Characters per minute (CPM)** — raw character throughput
- [ ] **Top applications** — aggregate time spent per window title, rank by duration
- [ ] **Activity heatmap data** — 24 hours x 7 days matrix of keystroke counts
- [ ] **Idle detection** — periods with no keystrokes/mouse activity (configurable idle threshold, default 5 minutes)
- [ ] **Session duration** — total active time vs idle time per day
- [ ] **Peak hours** — identify most productive hours of the day
- [ ] **Keystroke frequency distribution** — most pressed keys (anonymized, counts only)
- [ ] **Application switching frequency** — how often user switches between apps
- [ ] **Daily/weekly/monthly summary** — aggregate all metrics into summary object

### Report Generation
- [ ] `analytics/report.py` — report generator
- [ ] Export to JSON — structured data for programmatic access
- [ ] Export to CSV — flat tables for spreadsheet import
- [ ] Export to HTML — self-contained single-file report with inline CSS
- [ ] CLI command: `python -m main report --format html --output report.html --date 2026-02-08`
- [ ] CLI command: `python -m main report --format csv --output data.csv --range 7d`
- [ ] Configurable date range filters (today, last 7 days, last 30 days, custom range)

### Files to Create
```
analytics/
  __init__.py
  engine.py       — AnalyticsEngine class: compute_wpm(), compute_heatmap(), etc.
  report.py       — ReportGenerator class: to_json(), to_csv(), to_html()
  templates/
    report.html   — Jinja2 template for HTML reports
```

### Config Additions
```yaml
analytics:
  enabled: true
  idle_threshold_seconds: 300
  wpm_window_minutes: 5
  report_format: "html"
  report_output_dir: "reports/"
```

### Tests
- [ ] `tests/test_analytics.py` — WPM calculation, heatmap generation, idle detection, report export

---

## Feature 6: Interactive TUI (Terminal UI)

**Directory:** `tui/`
**Dependencies:** `textual` (recommended) or `rich`
**Priority:** MEDIUM — great for README screenshots and demos

### Checklist
- [ ] Real-time status panel — uptime, active modules, PID
- [ ] Capture module health — running/stopped/error per module with toggle
- [ ] Transport queue panel — queue depth, circuit breaker state (CLOSED/OPEN/HALF_OPEN), last send time
- [ ] Storage usage bar — current size / max size with percentage
- [ ] Live keystroke feed — scrolling log of recent keystrokes (redacted by default)
- [ ] Live event log — scrolling log of system events (module start/stop, transport success/fail, errors)
- [ ] Keyboard shortcuts — q=quit, p=pause, r=resume, s=send now, c=clear log
- [ ] CLI command: `python -m main --tui`
- [ ] Graceful fallback if terminal doesn't support TUI (fall back to plain logging)

### Files to Create
```
tui/
  __init__.py
  app.py          — Textual App class
  widgets/
    __init__.py
    status.py     — system status widget
    modules.py    — capture module status widget
    transport.py  — transport queue / circuit breaker widget
    storage.py    — storage usage bar widget
    feed.py       — live event feed widget
```

---

## Feature 7: Consent & Setup Wizard

**Directory:** `wizard/`
**Dependencies:** `rich` (for pretty CLI prompts)
**Priority:** MEDIUM — legitimizes the project, zero-friction onboarding

### Checklist
- [ ] Interactive CLI wizard triggered by `python -m main --setup`
- [ ] Step 1: Display consent/disclaimer banner — require explicit "I AGREE" to proceed
- [ ] Step 2: Select capture modules to enable (checkbox multi-select)
- [ ] Step 3: Configure transport method (single-select: email, http, ftp, telegram, none)
- [ ] Step 4: Enter transport credentials (email/password, URL, bot token, etc.)
- [ ] Step 5: Set report interval and storage limits
- [ ] Step 6: Generate encryption key (offer password-based or random)
- [ ] Step 7: Write `user_config.yaml` with all selections
- [ ] Step 8: Run a dry-run test to verify configuration works
- [ ] Step 9: Display summary and next steps
- [ ] Non-interactive mode: `python -m main --setup --non-interactive --config defaults.yaml`
- [ ] Consent log: write timestamped consent record to `data/consent.log`

### Files to Create
```
wizard/
  __init__.py
  setup.py        — SetupWizard class with step methods
  consent.py      — consent banner text, agreement validation, consent logging
  prompts.py      — reusable prompt helpers (select, multi-select, password input)
```

---

## Feature 8: Webhook & Notification System

**Directory:** `transport/webhook_transport.py` + `notifications/`
**Dependencies:** `requests` (already installed)
**Priority:** MEDIUM — integrates with Slack, Discord, IFTTT, Zapier

### Webhook Transport Checklist
- [ ] `transport/webhook_transport.py` — generic webhook transport
- [ ] Register via `@register_transport("webhook")`
- [ ] POST JSON payload to configurable URL
- [ ] Configurable headers (for auth tokens)
- [ ] Configurable payload template (Jinja2 or f-string)
- [ ] Retry with @retry decorator (like other transports)
- [ ] Timeout configuration

### Event Notification System
- [ ] `notifications/__init__.py`
- [ ] `notifications/notifier.py` — event notification dispatcher
- [ ] Configurable event triggers:
  - [ ] `on_screenshot` — new screenshot captured
  - [ ] `on_idle_start` — user went idle
  - [ ] `on_idle_end` — user returned from idle
  - [ ] `on_keyword_detected` — specific keyword typed (configurable keyword list)
  - [ ] `on_app_switch` — user switched to a specific application
  - [ ] `on_transport_failure` — transport send failed
  - [ ] `on_storage_warning` — storage usage above threshold (e.g., 80%)
- [ ] Multiple notification channels per event (e.g., screenshot -> webhook + telegram)
- [ ] Rate limiting — max 1 notification per event type per N seconds (prevent spam)

### Config Additions
```yaml
transport:
  webhook:
    enabled: false
    url: ""
    method: "POST"
    headers: {}
    timeout: 10

notifications:
  enabled: false
  rate_limit_seconds: 60
  events:
    on_screenshot:
      channels: ["webhook"]
    on_keyword_detected:
      channels: ["telegram"]
      keywords: []
    on_storage_warning:
      channels: ["webhook"]
      threshold_percent: 80
```

### Files to Create
```
transport/webhook_transport.py
notifications/
  __init__.py
  notifier.py
  events.py         — event type definitions
```

### Tests
- [ ] `tests/test_webhook_transport.py` — send, retry, custom headers
- [ ] `tests/test_notifications.py` — event dispatching, rate limiting, multi-channel

---

## Feature 9: Data Export CLI

**Directory:** `export/`
**Dependencies:** `jinja2` (for HTML template)
**Priority:** MEDIUM — practical utility

### Checklist
- [ ] `export/__init__.py`
- [ ] `export/exporter.py` — ExportManager class

### Export Formats
- [ ] **JSON** — full structured data dump with metadata
- [ ] **CSV** — flat tables (one CSV per capture type: keystrokes.csv, clicks.csv, windows.csv, clipboard.csv)
- [ ] **HTML** — self-contained single-file report with embedded CSS, tables, screenshot thumbnails
- [ ] **SQLite dump** — copy of the database file
- [ ] **ZIP bundle** — all of the above packaged together

### CLI Commands
- [ ] `python -m main export --format json --output captures.json`
- [ ] `python -m main export --format csv --output-dir ./export/`
- [ ] `python -m main export --format html --output report.html`
- [ ] `python -m main export --format zip --output full-export.zip`
- [ ] `python -m main export --format sqlite --output backup.db`
- [ ] Date range filter: `--from 2026-02-01 --to 2026-02-08`
- [ ] Capture type filter: `--types keystrokes,screenshots`
- [ ] Encryption: `--encrypt` to encrypt the export bundle
- [ ] Add argparse subcommands to main.py

### Files to Create
```
export/
  __init__.py
  exporter.py          — ExportManager with format-specific methods
  templates/
    report.html        — Jinja2 HTML report template
```

### Tests
- [ ] `tests/test_export.py` — each format output, date filtering, type filtering, encryption

---

## Feature 10: Plugin SDK & Cookiecutter Template

**Directory:** `plugin_template/`
**Dependencies:** `cookiecutter` (optional, for template generation)
**Priority:** MEDIUM — attracts contributors

### Checklist
- [ ] `plugin_template/` — cookiecutter template directory
- [ ] Template for custom capture plugin — pre-filled with BaseCapture, @register_capture, start/stop/collect stubs
- [ ] Template for custom transport plugin — pre-filled with BaseTransport, @register_transport, connect/send/disconnect stubs
- [ ] `plugins/` directory in main project for user-installed plugins
- [ ] Auto-discovery of plugins in `plugins/` directory (extend __init__.py import loops)
- [ ] Plugin metadata (name, version, author, description) via class attributes
- [ ] Plugin validation — verify required methods exist before registration
- [ ] Example plugins:
  - [ ] `plugins/example_capture_network.py` — example network activity capture (skeleton)
  - [ ] `plugins/example_transport_s3.py` — example S3 upload transport (skeleton)

### Files to Create
```
plugin_template/
  cookiecutter.json
  {{cookiecutter.plugin_name}}/
    __init__.py
    {{cookiecutter.plugin_type}}_plugin.py
    tests/
      test_{{cookiecutter.plugin_name}}.py

plugins/
  __init__.py
  README.md           — how to install and create plugins
  example_capture_network.py
  example_transport_s3.py
```

### Documentation
- [ ] `docs/development/plugin-guide.md` — step-by-step guide to creating a plugin (covered in Feature 3)

---

## Feature 11: Multi-Language Keyboard Layout Support

**Directory:** `capture/layouts/`
**Dependencies:** None (pure Python)
**Priority:** MEDIUM — differentiator, most keylogger projects only support US QWERTY

### Checklist
- [ ] `capture/layouts/__init__.py` — layout registry
- [ ] `capture/layouts/base.py` — abstract KeyboardLayout class
- [ ] `capture/layouts/us_qwerty.py` — US QWERTY (current default)
- [ ] `capture/layouts/uk_qwerty.py` — UK QWERTY
- [ ] `capture/layouts/french_azerty.py` — French AZERTY
- [ ] `capture/layouts/german_qwertz.py` — German QWERTZ
- [ ] `capture/layouts/dvorak.py` — Dvorak
- [ ] Auto-detect system keyboard layout via OS APIs
- [ ] Configurable layout override in config
- [ ] Update `keyboard_capture.py` to use layout classes for key mapping
- [ ] Dead key and modifier combination support (accented characters)

### Config Additions
```yaml
capture:
  keyboard:
    layout: "auto"    # auto-detect, or: us_qwerty, french_azerty, german_qwertz, dvorak
```

### Tests
- [ ] `tests/test_keyboard_layouts.py` — key mapping for each layout, auto-detect fallback

---

## Feature 12: Privacy Filters & Redaction

**Directory:** `filters/`
**Dependencies:** `re` (stdlib)
**Priority:** MEDIUM — shows responsible design, corporate compliance

### Checklist
- [ ] `filters/__init__.py`
- [ ] `filters/redactor.py` — RedactionEngine class

### Redaction Rules
- [ ] Credit card numbers — regex detect and replace with `[REDACTED-CC]`
- [ ] Social Security Numbers — regex detect and replace with `[REDACTED-SSN]`
- [ ] Email addresses — regex detect and replace with `[REDACTED-EMAIL]`
- [ ] Phone numbers — regex detect and replace with `[REDACTED-PHONE]`
- [ ] Custom patterns — user-defined regex list in config
- [ ] Password field detection — detect when active window title contains "password", "login", "sign in" and pause keystroke capture or redact
- [ ] Application blocklist — never capture data when specific apps are in focus (e.g., banking apps)
- [ ] Time-based filters — only capture during configured hours (e.g., 9 AM - 5 PM)
- [ ] Redact before storage — filter runs BEFORE data hits SQLite/disk
- [ ] Redaction audit log — log how many items were redacted (not the content)

### Config Additions
```yaml
privacy:
  enabled: false
  redact_credit_cards: true
  redact_ssn: true
  redact_emails: false
  redact_phone: false
  custom_patterns:
    - name: "API Keys"
      pattern: "(?:api[_-]?key|token)[=:]\s*\S+"
      replacement: "[REDACTED-APIKEY]"
  password_field_detection: true
  blocked_applications:
    - "1Password"
    - "KeePass"
    - "Bitwarden"
  active_hours:
    enabled: false
    start: "09:00"
    end: "17:00"
    timezone: "UTC"
```

### Files to Create
```
filters/
  __init__.py
  redactor.py       — RedactionEngine class
  patterns.py       — built-in regex patterns for CC, SSN, email, phone
```

### Tests
- [ ] `tests/test_redaction.py` — each pattern type, custom patterns, blocklist, time filter

---

## Feature 13: Remote Management API

**Directory:** integrated into `dashboard/` (Feature 1)
**Dependencies:** same as dashboard
**Priority:** LOW — useful but depends on dashboard being built first

### Checklist
- [ ] `POST /api/control/start` — start all or specific capture modules
- [ ] `POST /api/control/stop` — stop all or specific capture modules
- [ ] `POST /api/control/restart` — restart the application
- [ ] `GET /api/modules` — list all registered capture/transport modules with status
- [ ] `POST /api/modules/{name}/enable` — enable a specific module
- [ ] `POST /api/modules/{name}/disable` — disable a specific module
- [ ] `POST /api/config/reload` — reload config from disk without restart
- [ ] `GET /api/logs` — tail recent log entries (with level filter)
- [ ] `GET /api/diagnostics` — system info, memory usage, CPU, disk space
- [ ] Rate limiting on all management endpoints (prevent abuse)
- [ ] All management actions logged to audit trail

---

## Feature 14: Anomaly Detection

**Directory:** `analytics/anomaly.py`
**Dependencies:** None (pure Python stats, no ML libraries needed)
**Priority:** LOW — impressive feature, but complex

### Checklist
- [ ] `analytics/anomaly.py` — AnomalyDetector class
- [ ] **Typing cadence baseline** — learn normal inter-keystroke timing distribution per user
- [ ] **Anomaly scoring** — flag sessions where typing pattern deviates significantly (z-score > 2)
- [ ] **Activity anomalies** — unusual hours, sudden bursts after long idle
- [ ] **Application anomalies** — new/unusual applications detected
- [ ] Store baseline profiles in SQLite (per-user fingerprint)
- [ ] Configurable sensitivity threshold
- [ ] Integration with notification system (Feature 8) — alert on anomaly detected
- [ ] No external ML libraries — use simple statistics (mean, stddev, z-score)

### Config Additions
```yaml
analytics:
  anomaly_detection:
    enabled: false
    sensitivity: 2.0          # z-score threshold
    baseline_days: 7           # days of data to build baseline
    notify_on_anomaly: true
```

### Tests
- [ ] `tests/test_anomaly.py` — baseline building, scoring, threshold triggering

---

## Feature 15: Live Replay Mode

**Directory:** `replay/`
**Dependencies:** `rich` (for terminal replay) or integrated into dashboard
**Priority:** LOW — compelling demo feature

### Checklist
- [ ] `replay/__init__.py`
- [ ] `replay/player.py` — ReplayPlayer class
- [ ] Read captures from SQLite ordered by timestamp
- [ ] Terminal mode: replay keystrokes in real-time (or 2x, 5x, 10x speed)
- [ ] Show window title changes as headers
- [ ] Show screenshot timestamps as markers
- [ ] Show clipboard copies inline
- [ ] Playback controls: pause, resume, speed up, slow down, skip to time
- [ ] CLI command: `python -m main replay --session latest --speed 2x`
- [ ] CLI command: `python -m main replay --date 2026-02-08 --from 09:00 --to 17:00`
- [ ] Dashboard integration: replay via web UI (Feature 1 dependency)

### Files to Create
```
replay/
  __init__.py
  player.py         — ReplayPlayer class with playback logic
```

---

## Feature 16: GitHub Project Polish (Badges, Templates, Community)

**Directory:** project root + `.github/`
**Dependencies:** None
**Priority:** LOW effort, MEDIUM impact — signals project maturity

### Checklist
- [ ] README badges: build status, coverage %, PyPI version, Python versions, license, downloads
- [ ] `CONTRIBUTING.md` — contribution guidelines, code style, PR process
- [ ] `CODE_OF_CONDUCT.md` — standard contributor covenant
- [ ] `SECURITY.md` — security policy, responsible disclosure process
- [ ] `.github/ISSUE_TEMPLATE/bug_report.md` — structured bug report template
- [ ] `.github/ISSUE_TEMPLATE/feature_request.md` — structured feature request template
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` — PR checklist template
- [ ] `.github/FUNDING.yml` — sponsorship links (GitHub Sponsors, Buy Me a Coffee)
- [ ] `CHANGELOG.md` — keep-a-changelog format, updated on each release
- [ ] GitHub Topics: add relevant topics to repo (python, keylogger, monitoring, security, education)
- [ ] Social preview image for the repository (1280x640 banner)
- [ ] Feature comparison table in README vs similar projects

### Files to Create
```
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
CHANGELOG.md
.github/
  ISSUE_TEMPLATE/
    bug_report.md
    feature_request.md
  PULL_REQUEST_TEMPLATE.md
  FUNDING.yml
```

---

## Feature 17: Grafana + InfluxDB Metrics

**Directory:** `metrics/`
**Dependencies:** `influxdb-client` (optional)
**Priority:** LOW — advanced observability

### Checklist
- [ ] `metrics/__init__.py`
- [ ] `metrics/collector.py` — MetricsCollector class
- [ ] Emit metrics to InfluxDB at configurable interval
- [ ] Metrics to track:
  - [ ] `keystrokes_total` — total keystrokes counter
  - [ ] `keystrokes_per_minute` — gauge
  - [ ] `screenshots_total` — counter
  - [ ] `clipboard_copies_total` — counter
  - [ ] `transport_sends_total` — counter (with success/failure tag)
  - [ ] `transport_queue_depth` — gauge
  - [ ] `storage_usage_bytes` — gauge
  - [ ] `circuit_breaker_state` — gauge (0=closed, 1=open, 2=half_open)
  - [ ] `active_window` — string tag on keystroke metrics
- [ ] Pre-built Grafana dashboard JSON — importable via Grafana provisioning
- [ ] Included in docker-compose.yml (Feature 2) as optional service

### Config Additions
```yaml
metrics:
  enabled: false
  backend: "influxdb"
  influxdb:
    url: "http://localhost:8086"
    token: ""
    org: "default"
    bucket: "keylogger"
  push_interval_seconds: 10
```

### Files to Create
```
metrics/
  __init__.py
  collector.py
grafana/
  dashboard.json      — pre-built Grafana dashboard
  provisioning/
    datasources.yml   — auto-configure InfluxDB datasource
    dashboards.yml    — auto-provision dashboard
```

---

## Feature 18: Rate Limiting & Self-Protection

**Directory:** updates to existing files
**Dependencies:** None
**Priority:** LOW — defensive hardening

### Checklist
- [ ] Memory usage cap — stop captures if memory exceeds configurable limit (default 200MB)
- [ ] CPU throttling — reduce capture frequency if CPU usage exceeds threshold
- [ ] Disk space watchdog — pause storage if disk drops below 500MB free
- [ ] Max capture rate — configurable max keystrokes per second (prevent runaway loops)
- [ ] Automatic log rotation size limits (already in logger_setup.py, verify adequate)
- [ ] SQLite database size cap — auto-purge oldest sent records when DB exceeds limit
- [ ] Crash recovery — detect unclean shutdown (stale PID), recover pending items on restart
- [ ] Health self-check — periodic self-diagnosis logged to healthcheck file

### Config Additions
```yaml
self_protection:
  max_memory_mb: 200
  max_cpu_percent: 50
  min_free_disk_mb: 500
  max_keystrokes_per_second: 100
  max_db_size_mb: 100
  health_check_interval_seconds: 60
```

---

## Implementation Order (Recommended)

| Phase | Features | Why This Order |
|-------|----------|---------------|
| **Phase 1** | 16 (GitHub Polish), 4 (PyPI) | Low effort, immediate credibility boost |
| **Phase 2** | 7 (Consent Wizard), 12 (Privacy Filters) | Legitimizes the project for responsible use |
| **Phase 3** | 5 (Analytics), 9 (Export CLI) | Adds real utility beyond raw capture |
| **Phase 4** | 1 (Web Dashboard), 6 (TUI) | Visual features that drive stars |
| **Phase 5** | 2 (Docker), 3 (MkDocs) | Deployment and documentation polish |
| **Phase 6** | 8 (Webhooks), 10 (Plugin SDK) | Extensibility and integrations |
| **Phase 7** | 11 (Keyboard Layouts), 13 (Remote Mgmt) | Advanced features |
| **Phase 8** | 14 (Anomaly), 15 (Replay), 17 (Grafana), 18 (Self-Protection) | Power-user features |

---

## Summary

| # | Feature | Priority | Estimated Files | Depends On |
|---|---------|----------|-----------------|------------|
| 1 | Web Dashboard | HIGH | ~15 | — |
| 2 | Docker Support | HIGH | ~5 | Feature 1 (optional) |
| 3 | MkDocs Documentation | HIGH | ~20 | — |
| 4 | PyPI Distribution | HIGH | ~5 | — |
| 5 | Keystroke Analytics | HIGH | ~5 | — |
| 6 | Interactive TUI | MEDIUM | ~7 | — |
| 7 | Consent & Setup Wizard | MEDIUM | ~4 | — |
| 8 | Webhooks & Notifications | MEDIUM | ~5 | — |
| 9 | Data Export CLI | MEDIUM | ~4 | Feature 5 (optional) |
| 10 | Plugin SDK | MEDIUM | ~8 | — |
| 11 | Keyboard Layouts | MEDIUM | ~8 | — |
| 12 | Privacy Filters | MEDIUM | ~4 | — |
| 13 | Remote Management API | LOW | ~3 | Feature 1 |
| 14 | Anomaly Detection | LOW | ~3 | Feature 5 |
| 15 | Live Replay Mode | LOW | ~3 | — |
| 16 | GitHub Project Polish | LOW effort | ~10 | — |
| 17 | Grafana + InfluxDB | LOW | ~5 | Feature 2 |
| 18 | Rate Limiting & Self-Protection | LOW | ~2 | — |
