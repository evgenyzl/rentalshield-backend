#!/usr/bin/env python3
"""
Seed database with car photos for professional app.
Uses public car images from Wikimedia Commons and official sources.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rentalshield.db.database import get_db, engine
from rentalshield.db.models import CarProfile, Base
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

# Professional car photos (real URLs from Wikipedia Commons & official sources)
CAR_PHOTOS = {
    ("Ford", "Focus"): "https://upload.wikimedia.org/wikipedia/commons/thumb/9/92/2015_Ford_Focus_Hatchback_%28facelift%29%2C_front_8.28.18.jpg/1024px-2015_Ford_Focus_Hatchback_%28facelift%29%2C_front_8.28.18.jpg",
    ("Mazda", "3"): "https://upload.wikimedia.org/wikipedia/commons/thumb/3/38/2019_Mazda3_sedan%2C_front_8.24.19.jpg/1024px-2019_Mazda3_sedan%2C_front_8.24.19.jpg",
    ("Toyota", "Camry"): "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4f/2018_Toyota_Camry_front_8.16.18.jpg/1024px-2018_Toyota_Camry_front_8.16.18.jpg",
    ("Honda", "Civic"): "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d7/2016_Honda_Civic_front_8.17.18.jpg/1024px-2016_Honda_Civic_front_8.17.18.jpg",
    ("BMW", "3 Series"): "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b4/2019_BMW_3_Series_front_8.28.19.jpg/1024px-2019_BMW_3_Series_front_8.28.19.jpg",
    ("Mercedes", "C-Class"): "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/2019_Mercedes-Benz_C-Class_front_8.8.19.jpg/1024px-2019_Mercedes-Benz_C-Class_front_8.8.19.jpg",
    ("Volkswagen", "Golf"): "https://upload.wikimedia.org/wikipedia/commons/thumb/1/10/2017_Volkswagen_Golf_front_8.13.17.jpg/1024px-2017_Volkswagen_Golf_front_8.13.17.jpg",
    ("Audi", "A4"): "https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/2020_Audi_A4_front_8.10.20.jpg/1024px-2020_Audi_A4_front_8.10.20.jpg",
}

def seed_car_photos():
    """Add car photos to existing cars or create new ones."""
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        for (make, model), photo_url in CAR_PHOTOS.items():
            # Check if car exists
            existing_car = session.query(CarProfile).filter_by(
                make=make,
                model=model
            ).first()

            if existing_car:
                # Update photo
                existing_car.photo_url = photo_url
                print(f"✓ Updated {make} {model} with photo")
            else:
                # Create new car with photo
                new_car = CarProfile(
                    user_id="demo-user-1",  # Demo user
                    rental_provider="Hertz",
                    make=make,
                    model=model,
                    year=2023,
                    license_plate=f"{make[:3].upper()}-{model[:3].upper()}-001",
                    color="Silver",
                    photo_url=photo_url,
                    rental_start_date=datetime.utcnow(),
                    rental_end_date=datetime.utcnow() + timedelta(days=7),
                    pickup_location="LAX Terminal 1",
                    dropoff_location="LAX Terminal 1",
                    status="active"
                )
                session.add(new_car)
                print(f"✓ Created {make} {model} with photo")

        session.commit()
        print(f"\n✅ Seed complete! Added {len(CAR_PHOTOS)} cars with professional photos.")

if __name__ == "__main__":
    seed_car_photos()
