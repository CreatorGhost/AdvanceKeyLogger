# AdvanceKeyLogger

A Python-based input monitoring and screen capture tool built for **educational purposes** — learning about OS-level input APIs, networking, encryption, and software architecture.

## Current Status

This project is in early development. See [`REVIEW.md`](REVIEW.md) for a full codebase review, list of known issues, and a detailed improvement roadmap with code examples for every feature.

## Project Structure

```
AdvanceKeyLogger/
├── main.py                    # Entry point (planned)
├── createfile.py              # Current: mouse listener + screenshot
├── mailLogger.py              # Current: email transport
├── credentials.json.example   # Credential template (copy to credentials.json)
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Project config (planned)
├── .gitignore                 # Git ignore rules
├── REVIEW.md                  # Full review & implementation guide
├── config/                    # Configuration management (planned)
├── capture/                   # Input capture modules (planned)
├── transport/                 # Data transport modules (planned)
├── storage/                   # Storage layer (planned)
├── utils/                     # Shared utilities (planned)
└── tests/                     # Unit tests (planned)
```

## Setup

```bash
# Clone the repository
git clone https://github.com/CreatorGhost/AdvanceKeyLogger.git
cd AdvanceKeyLogger

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure credentials
cp credentials.json.example credentials.json
# Edit credentials.json with your settings
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `pynput` | Keyboard and mouse input listeners |
| `Pillow` | Screenshot capture (replaces deprecated `pyscreenshot`) |
| `cryptography` | AES-256 encryption |
| `pyperclip` | Clipboard access |
| `pyyaml` | YAML configuration parsing |
| `requests` | HTTP transport |

## Development

```bash
# Run linter
ruff check .

# Run formatter
ruff format .

# Run type checker
mypy . --ignore-missing-imports

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=. --cov-report=term-missing
```

## Roadmap

See [`REVIEW.md`](REVIEW.md) for the complete roadmap, including:

- **Phase 1**: Fix bugs, project structure, config system, logging
- **Phase 2**: Rewrite modules as classes, proper entry point
- **Phase 3**: New capture modules, encryption, compression, transports
- **Phase 4**: Type hints, tests, CI/CD, documentation

## Disclaimer

This project is for **educational and authorized security research purposes only**. Do not use this software on systems you do not own or without explicit written permission from the system owner. Unauthorized monitoring of computer activity may violate local, state, and federal laws.
