"""Run the dashboard server."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="AdvanceKeyLogger Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    parser.add_argument(
        "--secret-key", default="change-me-in-production", help="Session secret key"
    )
    parser.add_argument("--admin-user", default="admin", help="Admin username (default: admin)")
    parser.add_argument(
        "--admin-pass",
        default=None,
        help="Admin password (REQUIRED in production; auto-generated if omitted in dev)",
    )
    parser.add_argument("--enable-fleet", action="store_true", help="Enable fleet management")
    parser.add_argument("--fleet-db", default=None, help="Path to fleet database")
    args = parser.parse_args()

    # Require an explicit admin password in production
    import os as _os
    import secrets as _secrets

    _env = _os.environ.get("APP_ENV", "development").lower()
    if args.admin_pass is None:
        if _env not in ("development", "dev", "test"):
            parser.error(
                "--admin-pass is required in production. "
                "Set APP_ENV=development to auto-generate a password for local use."
            )
        # Auto-generate for dev/test and print to console
        args.admin_pass = _secrets.token_urlsafe(16)
        print(f"[DEV] Auto-generated admin password: {args.admin_pass}")

    # Configure settings
    from config.settings import Settings

    settings = Settings()
    if args.enable_fleet:
        settings.set("fleet.enabled", True)
    if args.fleet_db:
        settings.set("fleet.database_path", args.fleet_db)

    # Configure auth
    from dashboard.auth import configure_auth, hash_password

    password_hash = hash_password(args.admin_pass)
    configure_auth(args.admin_user, password_hash)

    # Create and run app
    from dashboard.app import create_app

    app = create_app(secret_key=args.secret_key)

    import uvicorn

    print(f"\n  AdvanceKeyLogger Dashboard")
    print(f"  Running on http://{args.host}:{args.port}")
    print(f"  Login: {args.admin_user} / {'*' * len(args.admin_pass)}")
    print(f"  API docs: http://{args.host}:{args.port}/api/docs")
    print()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
