"""Run the dashboard server."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="AdvanceKeyLogger Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    parser.add_argument("--secret-key", default="change-me-in-production", help="Session secret key")
    parser.add_argument("--admin-user", default="admin", help="Admin username (default: admin)")
    parser.add_argument("--admin-pass", default="admin", help="Admin password (default: admin)")
    args = parser.parse_args()

    # Configure auth
    from dashboard.auth import configure_auth
    password_hash = hashlib.sha256(args.admin_pass.encode()).hexdigest()
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
