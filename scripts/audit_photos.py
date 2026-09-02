#!/usr/bin/env python3
"""
RentalShield — Photo audit entry point.
Usage:
    python scripts/audit_photos.py <photo_dir> [--plate X] [--company X] ...

Accepts a folder of JPEG/PNG images instead of a video.
Phone camera photos are ~12 MP vs 1080p video frames — much sharper evidence.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
from rentalshield.models import RentalMetadata
from rentalshield.pipeline import run_photo_audit
from rich.console import Console

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="RentalShield — photo-based damage audit"
    )
    parser.add_argument(
        "photo_dir",
        help="Folder containing the walkaround photos (JPEG/PNG)",
    )

    meta = parser.add_argument_group("Rental info (shown in report header)")
    meta.add_argument("--plate",    "-p", default=None)
    meta.add_argument("--company",  "-c", default=None)
    meta.add_argument("--car",            default=None)
    meta.add_argument("--location", "-l", default=None)
    meta.add_argument("--contract",       default=None)
    meta.add_argument("--inspector",      default=None)
    meta.add_argument("--lat",  type=float, default=None)
    meta.add_argument("--lon",  type=float, default=None)

    args = parser.parse_args()

    metadata = RentalMetadata(
        car_plate       = args.plate,
        rental_company  = args.company,
        car_model       = args.car,
        location        = args.location,
        contract_number = args.contract,
        inspector_name  = args.inspector,
        gps_lat         = args.lat,
        gps_lon         = args.lon,
    )

    session = run_photo_audit(Path(args.photo_dir), metadata=metadata)
    console.print(f"\nSession ID: [bold]{session.session_id}[/bold]")
    console.print(f"To compare: python scripts/compare.py {session.session_id} --pdf <company.pdf>")


if __name__ == "__main__":
    main()
