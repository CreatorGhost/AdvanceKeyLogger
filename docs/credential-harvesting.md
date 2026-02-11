# Credential & Data Harvesting

Extracts stored credentials, browser data, SSH keys, and API tokens from the target system.

- **Source:** [`harvest/`](../harvest/) package

## What Gets Harvested

### Browser Credentials (`harvest/browser_creds.py`)
- Chrome/Chromium passwords (Login Data SQLite + AES-GCM decryption)
- Firefox passwords (logins.json + NSS)
- Safari passwords (macOS Keychain)
- Edge, Brave, Opera, Vivaldi (shared Chromium format)
- Cross-platform path detection for all browser profiles

**Decryption per platform:**
| Platform | Method |
|----------|--------|
| macOS | Keychain (`security find-generic-password`) + PBKDF2 (1003 iterations) |
| Windows | DPAPI (`CryptUnprotectData`) |
| Linux | GNOME Keyring / PBKDF2 with `"peanuts"` fallback (1 iteration) |

### Browser Data (`harvest/browser_data.py`)
- Browsing history (URLs, titles, visit counts, timestamps)
- Cookies (metadata; values encrypted on Chrome)
- Bookmarks from all browsers
- Download history with file paths
- Autofill/form data (names, addresses, phone numbers)

### SSH Keys & Cloud Credentials (`harvest/keys.py`)
- SSH private keys (`~/.ssh/id_rsa`, `id_ed25519`, etc.)
- SSH known_hosts and config
- AWS credentials (`~/.aws/credentials`)
- GCP service account keys (`~/.config/gcloud/`)
- Azure tokens (`~/.azure/`)
- API tokens from `.env` files
- Git credential helpers and shell history tokens
- WiFi passwords (Keychain on macOS, netsh on Windows, NetworkManager on Linux)

### Harvest Scheduler (`harvest/scheduler.py`)
- One-shot or periodic harvesting modes
- Change detection (only re-harvest when source files are modified)
- Fleet integration (trigger harvest via controller command)
- Thread-safe with locking for concurrent access

## Usage

```python
from harvest.browser_creds import BrowserCredentialHarvester
from harvest.keys import KeyHarvester
from harvest.scheduler import HarvestScheduler

# One-shot harvest
harvester = BrowserCredentialHarvester()
creds = harvester.harvest_all()

# Key discovery
keys = KeyHarvester().harvest_all()

# Scheduled periodic harvesting
scheduler = HarvestScheduler({"interval_seconds": 3600})
scheduler.start_periodic()
```

## Configuration

```yaml
# Harvest is triggered via fleet commands or programmatically
# No default config section -- controlled by fleet controller
```
