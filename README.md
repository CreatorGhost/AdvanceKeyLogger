# AdvanceKeyLogger

A Python-based input monitoring and screen capture tool built for **educational purposes** — learning about OS-level input APIs, networking, encryption, and software architecture.

## Current Status

Core architecture is implemented (config system, capture plugins, transports,
storage, utilities, and tests). See [`REVIEW.md`](REVIEW.md) for the full review
and detailed implementation roadmap.

## Project Structure

```
AdvanceKeyLogger/
├── main.py                    # Entry point
├── createfile.py              # Legacy: click-to-screenshot demo
├── mailLogger.py              # Legacy: standalone email sender
├── credentials.json.example   # Credential template (copy to credentials.json)
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Project config (planned)
├── .gitignore                 # Git ignore rules
├── REVIEW.md                  # Full review & implementation guide
├── config/                    # Configuration management
├── capture/                   # Input capture modules
├── transport/                 # Data transport modules
├── storage/                   # Storage layer
├── utils/                     # Shared utilities
└── tests/                     # Unit tests
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

# Copy and configure credentials (email transport)
cp credentials.json.example credentials.json
# Edit credentials.json with your settings

# Run (uses config/default_config.yaml)
python main.py

# List available plugins
python main.py --list-captures
python main.py --list-transports
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
