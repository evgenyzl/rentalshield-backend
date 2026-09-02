#!/usr/bin/env python3
"""Quick test script to measure damage detection on compressed images."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rentalshield.photo.extractor import PhotoExtractor
from rentalshield.ai.factory import get_analyzer
from rentalshield.pipeline import run_photo_audit
from rentalshield.api.jobs import DamageSession

# Test on iPhone WhatsApp compressed photos
test_dir = Path.home() / "Downloads" / "iPhone"
if not test_dir.exists():
    print(f"❌ Test photos not found at {test_dir}")
    sys.exit(1)

print(f"📸 Testing on {len(list(test_dir.glob('*.jpeg')))} compressed images from {test_dir.name}")
print("=" * 60)

try:
    # Extract photos
    extractor = PhotoExtractor(test_dir)

    # Create analyzer
    analyzer = get_analyzer()

    # Run pipeline
    session = DamageSession()
    run_photo_audit(extractor, analyzer, session)

    # Report results
    damage_count = len(session.damages)
    print(f"\n✅ RESULTS:")
    print(f"   Damages detected: {damage_count}")
    print(f"   Previous (old thresholds): 1 damage")
    print(f"   Improvement: {damage_count - 1:+d} damages")

    if damage_count > 1:
        print(f"\n✅ SUCCESS! Lower thresholds working!")
        for i, dmg in enumerate(session.damages, 1):
            print(f"   #{i}: {dmg.type.value} at {dmg.location} (conf: {dmg.confidence:.2f})")
    else:
        print(f"\n❌ No improvement. Need stronger changes.")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
