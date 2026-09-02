#!/usr/bin/env python3
"""
RentalShield API server — local development entry point.

Usage:
    python scripts/serve.py
    python scripts/serve.py --port 8080
    python scripts/serve.py --host 0.0.0.0   # expose to LAN (test from phone)

The web UI is at http://localhost:8000
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RentalShield API server")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Host to bind (default: 0.0.0.0 — accessible from phone on same WiFi)")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port (default: 8000)")
    parser.add_argument("--reload", action="store_true",
                        help="Auto-reload on code changes (dev mode)")
    args = parser.parse_args()

    print(f"\n  RentalShield API")
    print(f"  ─────────────────────────────────")
    print(f"  Local:   http://localhost:{args.port}")
    print(f"  Network: http://<your-ip>:{args.port}   ← open on your phone")
    print(f"  ─────────────────────────────────\n")

    uvicorn.run(
        "rentalshield.api.app:app",
        host       = args.host,
        port       = args.port,
        reload     = args.reload,
        app_dir    = str(Path(__file__).parent.parent / "src"),
        log_level  = "info",
    )
