#!/usr/bin/env python3
"""
RentalShield — Audit script entry point.
Usage:
    python scripts/audit.py [video_path] [--interval N]
"""

import sys
from pathlib import Path

# Make src/ importable when running directly from the project root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rentalshield.pipeline import audit_cli

if __name__ == "__main__":
    audit_cli()
