#!/usr/bin/env python3
"""
RentalShield — Compare script entry point.
Usage:
    python scripts/compare.py [session_id | damages.json] [--pdf company_report.pdf]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rentalshield.pipeline import compare_cli

if __name__ == "__main__":
    compare_cli()
