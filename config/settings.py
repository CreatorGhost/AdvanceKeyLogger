"""
Configuration loader with validation, defaults, and environment variable overrides.

Usage:
    from config.settings import Settings

    settings = Settings()                            # Load defaults only
    settings = Settings("my_config.yaml")            # Load with user overrides
    interval = settings.get("general.report_interval")  # Dot-notation access
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class Settings:
    """Loads config from YAML with defaults, env var overrides, and validation."""

    _instance: Settings | None = None

    def __new__(cls, config_path: str | None = None) -> Settings:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str | None = None) -> None:
        if self._initialized:
            return
        self._initialized = True

        default_path = Path(__file__).parent / "default_config.yaml"
        try:
            with open(default_path) as f:
                self._config: dict = yaml.safe_load(f)
        except FileNotFoundError:
            logger.critical("Default config not found at %s", default_path)
            raise
        except yaml.YAMLError as e:
            logger.critical("Failed to parse default config: %s", e)
            raise

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    user_config = yaml.safe_load(f)
                if user_config:
                    self._config = self._deep_merge(self._config, user_config)
                logger.info("Loaded user config from %s", config_path)
            except yaml.YAMLError as e:
                logger.error("Failed to parse user config %s: %s", config_path, e)
                raise

        self._apply_env_overrides()
        self._validate()
        logger.debug("Configuration loaded successfully")

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a nested config value using dot notation.

        Example:
            settings.get("capture.screenshot.quality")  -> 80
            settings.get("nonexistent.key", "fallback") -> "fallback"
        """
        keys = key_path.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, key_path: str, value: Any) -> None:
        """Set a nested config value using dot notation."""
        keys = key_path.split(".")
        d = self._config
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value

    def as_dict(self) -> dict:
        """Return the full config as a dictionary."""
        return self._config.copy()

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (useful for testing)."""
        cls._instance = None

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Recursively merge override dict into base dict."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _apply_env_overrides(self) -> None:
        """
        Allow environment variables to override config.

        Convention: SVC_SECTION__KEY=value (double underscore separates levels)
        Example:    SVC_GENERAL__LOG_LEVEL=DEBUG -> general.log_level

        Double underscore (__) separates config path levels, single underscore
        within a level is preserved. This allows keys like "log_level" to work.

        Legacy prefix KEYLOGGER_ is also supported for backward compatibility.
        """
        prefix = "SVC_"
        # Also check legacy prefix for backward compatibility
        legacy_prefix = "KEYLOGGER_"
        for env_key, env_value in os.environ.items():
            active_prefix = None
            if env_key.startswith(prefix):
                active_prefix = prefix
            elif env_key.startswith(legacy_prefix):
                active_prefix = legacy_prefix
            if active_prefix:
                # Split on double underscore to get path parts
                # Each part can contain single underscores (e.g., log_level)
                parts = env_key[len(active_prefix) :].lower().split("__")
                self._set_nested(self._config, parts, env_value)
                logger.debug("Env override: %s = %s", env_key, env_value)

    def _set_nested(self, d: dict, keys: list[str], value: str) -> None:
        """Set a nested dictionary value from a list of keys."""
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = self._cast_value(value)

    @staticmethod
    def _cast_value(value: str) -> Any:
        """Attempt to cast string env var to appropriate Python type."""
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def _validate(self) -> None:
        """Validate critical configuration values."""
        interval = self.get("general.report_interval")
        if not isinstance(interval, (int, float)) or interval < 1:
            raise ValueError(f"report_interval must be >= 1, got {interval}")

        max_size = self.get("storage.max_size_mb")
        if not isinstance(max_size, (int, float)) or max_size < 1:
            raise ValueError(f"storage.max_size_mb must be >= 1, got {max_size}")

        log_level = self.get("general.log_level", "INFO")
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got {log_level}")

        if self.get("fleet.enabled"):
            secret = self.get("fleet.auth.jwt_secret")
            if not secret or secret == "CHANGE_ME_IN_PRODUCTION":
                allow_default = self.get("fleet.auth.allow_default_secret", False)
                if allow_default:
                    logger.warning(
                        "Fleet enabled with default/empty JWT secret. "
                        "PLEASE CHANGE IN PRODUCTION (allow_default_secret=true)."
                    )
                else:
                    raise RuntimeError(
                        "Fleet is enabled but JWT secret is not configured. "
                        "Set fleet.auth.jwt_secret to a strong random value (32+ chars). "
                        "For development, set fleet.auth.allow_default_secret to true."
                    )
