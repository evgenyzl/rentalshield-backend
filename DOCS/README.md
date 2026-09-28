# RentalShield 360 – Documentation

## Quick Links

### Phase 1: Free B2C App (Current Focus)
**Goal:** Beautiful, free app for car rental inspections + app store distribution

- **[PHASE_1_SPEC.md](PHASE_1_SPEC.md)** — Executive summary, business case, 7 core screens, 6-week timeline
- **[PHASE_1_ARCHITECTURE.md](PHASE_1_ARCHITECTURE.md)** — Complete data schema, database design, API endpoints, offline-first strategy
- **[PHASE_1_UI_COMPONENTS.md](PHASE_1_UI_COMPONENTS.md)** — UI/UX component breakdown, screen designs, design system, accessibility
- **[PHASE_1_COMPETITIVE_ANALYSIS.md](PHASE_1_COMPETITIVE_ANALYSIS.md)** — Competitive landscape (CarRentPal, Not My Dent, DAMAGE iD, Myrentpad) + what we're stealing from each

### Phase 0: Damage Detection Optimization (Previous)
Documented in git history and archived specs.

---

## The Vision: Three-Phase Go-to-Market

```
PHASE 1 (Weeks 1-6): FREE B2C APP
├─ Document parsing (OCR)
├─ 8-angle photo capture (Ghost Mode)
├─ Beautiful dashboard + PDF reports
├─ Offline-first architecture
├─ Monetization: AdMob ads
└─ Target: 100k downloads on App Store

PHASE 2 (Weeks 7-12): PREMIUM AI FEATURES
├─ AI damage detection (background async)
├─ Damage severity scoring
├─ Insurance claim templates
├─ Monetization: $2.99/month subscription
└─ Expected conversion: 5-10% of Phase 1 users

PHASE 3 (Future): B2B PARTNERSHIPS
├─ Insurance company integrations
├─ Rental agency white-label
├─ Enterprise licensing
└─ Monetization: B2B revenue share
```

---

## Why Phase 1?

### The Problem We Solve
Users get false damage charges from rental companies. Our app provides **irrefutable evidence** with:
- GPS-stamped photos (can't be faked)
- Professional comparison reports (pickup vs dropoff)
- Immutable timestamps (EXIF verified)

### Why FREE (not $3 per customer)?
1. **No revenue pressure** — Free app, so no cost constraints
2. **App store visibility** — Easy to get 100k+ downloads
3. **Monetization path** — Ads (Phase 1) + Premium (Phase 2) + B2B (Phase 3)
4. **De-risks launch** — Get user feedback before expensive AI

---

## Key Competitive Advantages

| Feature | CarRentPal | Not My Dent | DAMAGE iD | Ours |
|---------|-----------|-----------|----------|------|
| **Ghost Mode** | ✓ | ✗ | ✗ | ✓✓ |
| **Capture Time** | 3-4 min | 15-20 min 🚨 | 5-7 min | **2-3 min** ⭐ |
| **Document OCR** | ✗ | ✗ | ✗ | ✓ |
| **Side-by-Side Comparison** | ✗ | ✗ | ✓ | ✓ |
| **Beautiful Dashboard** | ✗ | ✗ | ✗ | ✓ |
| **Free** | ✗ | ✗ | ✗ | ✓ |

---

## 7 Core Screens (6 Weeks)

1. **Dashboard** (Revolut-style cards) — 3-4 days
2. **Document Upload + OCR** (auto-populate) — 4-5 days
3. **Photo Capture** (Ghost Mode, 8 angles) — 5-6 days
4. **Interactive Car Diagram** (damage zones) — 3-4 days
5. **Side-by-Side Comparison** (pickup vs dropoff) — 3-4 days
6. **Rental Passport PDF** (professional export) — 4-5 days
7. **Settings + Share** — 2-3 days

**Total:** 24-31 days frontend + 15-20 days backend + 7-10 days testing = **6 weeks**

---

## Tech Stack

### Frontend
- React Native + Expo
- SQLite (local storage)
- React Navigation (routing)
- Google AdMob (ads)

### Backend
- FastAPI + Uvicorn
- PostgreSQL
- Claude Vision API (OCR)
- S3 / Google Cloud Storage
- ReportLab (PDF generation)
- Firebase Cloud Messaging (push)

### Deployment
- Heroku / Railway (backend)
- GitHub Actions (CI/CD)
- App Store / Google Play

---

## Getting Started

### Prerequisites
```bash
# Backend
python 3.9+
postgresql
redis (for Celery)

# Frontend
nodejs 16+
npm / yarn
```

### Project Structure
```
rentalshield/
├── DOCS/                    # Documentation (you are here)
│   ├── PHASE_1_SPEC.md
│   ├── PHASE_1_ARCHITECTURE.md
│   ├── PHASE_1_UI_COMPONENTS.md
│   └── PHASE_1_COMPETITIVE_ANALYSIS.md
├── src/
│   ├── rentalshield/        # Backend FastAPI app
│   │   ├── api/
│   │   ├── models/
│   │   ├── db/
│   │   └── services/
│   └── frontend/            # React Native (TBD)
│       ├── screens/
│       ├── components/
│       ├── hooks/
│       └── services/
├── requirements.txt         # Python dependencies
├── .env.example            # Environment variables
└── README.md               # Project root README
```

### Next Steps

1. **Design:** Create Figma mockups for all 7 screens
2. **Backend:** Set up FastAPI + PostgreSQL schema
3. **Frontend:** Initialize React Native + Expo
4. **Build:** Implement screens in order (Dashboard first)
5. **Test:** E2E testing + crash-free validation
6. **Launch:** App Store + Google Play submission

---

## Timeline

```
Week 1:  Backend foundation (FastAPI + DB)
Week 2-3: Frontend foundation + Screens 1-3 (Dashboard, OCR, Photo Capture)
Week 4:  Screens 4-6 (Car Diagram, Comparison, PDF)
Week 5:  Polish, ads, background sync
Week 6:  Testing, app store submission
Week 7:  Public launch + growth campaigns
```

---

## Success Metrics (Phase 1)

- [ ] 0 unhandled crashes (Sentry clean)
- [ ] < 1s dashboard load time
- [ ] 2-3 minute photo capture (8 angles)
- [ ] 99%+ upload success rate
- [ ] 100k downloads by week 16
- [ ] 5-10% Phase 2 conversion rate

---

## Questions?

See individual docs for detailed specs:
- **Architecture:** [PHASE_1_ARCHITECTURE.md](PHASE_1_ARCHITECTURE.md)
- **UI/UX:** [PHASE_1_UI_COMPONENTS.md](PHASE_1_UI_COMPONENTS.md)
- **Competitive:** [PHASE_1_COMPETITIVE_ANALYSIS.md](PHASE_1_COMPETITIVE_ANALYSIS.md)
- **Executive:** [PHASE_1_SPEC.md](PHASE_1_SPEC.md)

---

**Ready to build!** 🚀

Generated: September 28, 2026  
Author: evgeny.zlotnikov@nextsilicon.com  
Status: Phase 1 Ready for Development
