# Week 1: Backend Setup & First Endpoint

**Status: 🟢 READY TO START**

## What's Been Built Today

✅ Database models (SQLAlchemy)
  • User, CarProfile, RentalSession, InspectionPhoto
  • RentalDocument, DisputeReport, SyncQueue
  • All with proper indexes and relationships

✅ FastAPI application setup
  • Lifespan events (startup/shutdown)
  • CORS middleware
  • Language middleware (i18n)
  • Exception handlers
  • Health check endpoints

✅ Authentication router (stub)
  • POST /api/v1/auth/signup
  • POST /api/v1/auth/login
  • POST /api/v1/auth/logout
  • GET /api/v1/auth/me

✅ Router stubs for remaining endpoints
  • Cars, Sessions, Photos, Documents, Reports

✅ Configuration & Environment
  • .env.example with all needed variables
  • Settings management
  • Database URL configuration

✅ Multi-language Support
  • All error messages translated (4 languages)
  • Language auto-detection
  • Query parameter override (?lang=en)

---

## RUNNING THE APP RIGHT NOW

### Option 1: Development (Fastest)

```bash
cd /Users/evgenyz/Projects/rentalshield

# Install dependencies
pip install -r requirements.txt

# Create .env from template
cp .env.example .env

# Run the server
PYTHONPATH=src python -m uvicorn \
  rentalshield.api.server:app \
  --host 0.0.0.0 \
  --port 8888 \
  --reload
```

**Expected Output:**
```
✓ Database initialized
✓ Database connection verified
✓ All routers registered
INFO:     Uvicorn running on http://0.0.0.0:8888
```

### Option 2: Docker (Optional)

```bash
docker-compose up -d
```

---

## TEST THE API

### Health Check

```bash
curl http://localhost:8888/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": 1695848400.0,
  "version": "1.0.0"
}
```

### Get Configuration

```bash
# English
curl http://localhost:8888/config

# Italian
curl "http://localhost:8888/config?lang=it"

# Spanish
curl "http://localhost:8888/config?lang=es"

# French
curl "http://localhost:8888/config?lang=fr"
```

**Response (English):**
```json
{
  "app": {
    "name": "RentalShield",
    "version": "1.0.0",
    "environment": "development"
  },
  "languages": {
    "supported": ["en", "it", "es", "fr"],
    "current": "en",
    "names": {
      "en": "English",
      "it": "Italiano",
      "es": "Español",
      "fr": "Français"
    }
  },
  "features": {
    "document_parsing": true,
    "photo_capture": true,
    "offline_mode": true,
    "phase2_ai": false
  }
}
```

### API Documentation

Open browser: http://localhost:8888/docs

This is the interactive Swagger UI with all endpoints documented.

---

## DATABASE

### Check SQLite

```bash
sqlite3 rentalshield.db ".tables"
```

Should show:
```
users                  rental_sessions
car_profiles           inspection_photos
rental_documents       dispute_reports
sync_queue
```

### Check Tables

```bash
sqlite3 rentalshield.db ".schema users"
```

---

## NEXT STEPS (Monday)

### 1. Implement User Authentication (4-6 hours)

Files to implement:
  • src/rentalshield/api/routes/auth.py (extend stub)
  • Firebase integration
  • JWT token generation
  • Password hashing

### 2. Implement Car Profile Endpoints (3-4 hours)

Files to implement:
  • src/rentalshield/api/routes/cars.py
  • GET /api/v1/cars (list)
  • POST /api/v1/cars (create)
  • GET /api/v1/cars/{id} (detail)

### 3. Implement Rental Sessions (3-4 hours)

Files to implement:
  • src/rentalshield/api/routes/sessions.py
  • POST /api/v1/sessions (create pickup/dropoff)
  • GET /api/v1/sessions/{id} (detail)
  • PATCH /api/v1/sessions/{id}/complete (mark complete)

### 4. API Testing (2-3 hours)

Create:
  • tests/test_auth.py
  • tests/test_cars.py
  • tests/test_sessions.py

Run with:
```bash
pytest tests/ -v
```

---

## PROJECT STRUCTURE

```
rentalshield/
├── src/rentalshield/
│   ├── api/
│   │   ├── server.py           ✅ Main FastAPI app
│   │   └── routes/
│   │       ├── auth.py         ✅ Authentication (stub implemented)
│   │       ├── users.py        ✅ Users (stub)
│   │       ├── cars.py         ✅ Car profiles (stub)
│   │       ├── sessions.py     ✅ Sessions (stub)
│   │       ├── photos.py       ✅ Photos (stub)
│   │       ├── documents.py    ✅ Documents (stub)
│   │       └── reports.py      ✅ Reports (stub)
│   │
│   ├── db/
│   │   ├── models.py           ✅ SQLAlchemy models
│   │   └── database.py         ✅ Connection setup
│   │
│   ├── i18n/
│   │   ├── __init__.py         ✅ i18n functions
│   │   ├── middleware.py       ✅ Language middleware
│   │   ├── models.py           ✅ Pydantic models
│   │   └── translations/
│   │       ├── en.json         ✅ English
│   │       ├── it.json         ✅ Italian
│   │       ├── es.json         ✅ Spanish
│   │       └── fr.json         ✅ French
│   │
│   ├── config.py               ✅ Settings
│   └── main.py                 (not used - use server.py)
│
├── requirements.txt            ✅ Dependencies
├── .env.example               ✅ Configuration template
└── WEEK_1_STARTUP.md          ✅ This file
```

---

## DEBUGGING

### View Logs

```bash
# Live logs
tail -f rentalshield.log

# Or with loguru
PYTHONPATH=src python -c "from rentalshield.api.server import app; print('App loaded')"
```

### Database Issues

```bash
# Reset database
rm rentalshield.db
# App will recreate on next startup

# Or programmatically
python -c "from rentalshield.db.database import drop_db, init_db; drop_db(); init_db()"
```

### Test Database Connection

```python
from rentalshield.db.database import verify_db_connection
print(verify_db_connection())  # Should print True
```

---

## PRODUCTION READY (Week 2+)

To prepare for production:

1. Switch from SQLite to PostgreSQL
2. Add Redis for caching
3. Configure AWS S3/GCS
4. Setup Celery for background tasks
5. Add authentication with Firebase
6. Deploy to Heroku/Railway/Docker

---

## STATS

- **Lines of Code:** ~1,200 (core infrastructure)
- **Database Tables:** 7
- **API Endpoints Stubbed:** 6 routers
- **Languages Supported:** 4 (EN/IT/ES/FR)
- **Translation Keys:** ~400 per language
- **Setup Time:** Completed in this session ✅

---

## GO TIME! 🚀

Ready to build? Start the server and begin implementing the authentication endpoint.

```bash
PYTHONPATH=src python -m uvicorn \
  rentalshield.api.server:app \
  --host 0.0.0.0 \
  --port 8888 \
  --reload
```

Questions? Check DOCS/I18N_SETUP.md or DOCS/PHASE_1_ARCHITECTURE.md

Happy coding! 💻
