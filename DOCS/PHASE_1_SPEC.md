# RentalShield 360 – Phase 1 Specification
**Free B2C App + Beautiful UX (No Live AI)**

**Version:** 1.0  
**Date:** September 2026  
**Author:** evgeny.zlotnikov@nextsilicon.com  
**Status:** Ready for Development  

---

## Executive Summary

**Pivot Decision:** Move away from damage detection optimization. Instead, build a **beautiful, free B2C app** that combines document parsing, photo capture, and offline-first design.

**Timeline:** 6-7 weeks development → App Store launch  
**Target Users:** Car rental customers (B2C) + Insurance companies (B2B upsell)  
**Monetization:** Phase 1 = Free (ads), Phase 2 = $2.99/mo (damage AI)  

---

## What Changed from Phase 0?

| Aspect | Phase 0 (Original) | Phase 1 (New) |
|--------|------------|----------|
| **Focus** | Improve damage detection accuracy | Build beautiful UX + get users |
| **Revenue Model** | B2B sales ($3 per customer) | B2C free + ads, then premium Phase 2 |
| **Launch Timeline** | Blocked on damage accuracy | 6 weeks → App Store |
| **Live AI in App** | Yes (real-time analysis) | No (background analysis in Phase 2) |
| **Cost Pressure** | HIGH (₪3.8 vs ₪1-2 needed) | ZERO (free app, no cost constraints) |
| **Core Value** | Damage detection accuracy | Document parsing + photo capture |

---

## The Business Case

### Why Phase 1 Works

1. **No revenue pressure:** App is free, so no need to solve cost issues yet
2. **App store visibility:** Beautiful UX gets featured in Travel category
3. **User acquisition:** Free downloads are easy vs $3 B2B sales
4. **Monetization path:** Ads (Phase 1) + Premium (Phase 2) + B2B (Phase 3)
5. **De-risks launch:** Get user feedback before expensive Phase 2

### Target Numbers

```
Week 6: Launch on App Store
Week 8: 1,000 downloads
Week 12: 10,000 downloads
Week 16: 100,000 downloads

Revenue (Phase 1 with ads):
100k users × $0.05/user/month (ad revenue) = $5,000/month

Revenue (Phase 2 Premium):
100k users × 5% conversion × $2.99/month = $15,000/month
```

---

## 7 Core Screens

### Screen 1: Dashboard (Revolut-style Cards)
**Inspiration:** Revolut's card-based account design  
**Dev Time:** 3-4 days  

Features:
- Active rental card (large, prominent)
- Status badges (🔴 Active, ✓ Completed, ⚠️ Disputed)
- Quick stats: photos captured, documents uploaded, sync status
- Past rentals scrollable list
- FAB: "Upload Document"
- Smooth animations (150ms transitions)

**Why:** Premium feel, immediate visual feedback

---

### Screen 2: Document Upload + OCR
**Inspiration:** Myrentpad's form extraction  
**Dev Time:** 4-5 days  

Features:
- Upload PDF/image (camera or gallery)
- Claude Vision OCR (temp: 0.0, deterministic)
- Extract: provider, car, plate, dates, locations, pre-existing damages
- Confidence scoring per field (high/medium/low)
- Auto-populate car profile
- User review + manual edit if needed

**Why:** Saves users 5-10 minutes of typing

---

### Screen 3: 8-Angle Photo Capture (Ghost Mode)
**Inspiration:** CarRentPal's Ghost Mode + Not My Dent's angle structure  
**Dev Time:** 5-6 days  

Features:
- 8 angles: FRONT, REAR, LEFT, RIGHT, FRONT_DETAIL, REAR_DETAIL, LEFT_DETAIL, RIGHT_DETAIL
- **Ghost Mode:** Semi-transparent overlay of last capture (ensures consistency)
- Real-time quality score: blur, brightness, framing
- On-screen guidance ("Position left side parallel to ground")
- Auto-advance to next angle
- Immutable metadata: GPS lock + timestamp lock
- **Speed:** 2-3 minutes total (vs Not My Dent's 15-20)

**Why:** Ghost Mode makes photos consistent for side-by-side comparison

---

### Screen 4: Interactive Car Diagram
**Inspiration:** DAMAGE iD's damage zone marking  
**Dev Time:** 3-4 days  

Features:
- Visual car silhouette (sedan, SUV, hatchback variants)
- Tap zones to mark pre-existing damages: bumpers, doors, hood, roof, windows
- Severity picker: Minor (green) | Moderate (yellow) | Major (red)
- Link actual photos to each marked damage
- Visual reference used in dropoff comparison
- Editable: change marks, delete, add notes

**Why:** Faster than text entry + creates visual dispute evidence

---

### Screen 5: Side-by-Side Photo Comparison
**Inspiration:** DAMAGE iD's comparison view  
**Dev Time:** 3-4 days  

Features:
- Pickup vs Dropoff photos (same angle)
- Swipe to switch angles
- Shows date, time, location for both
- Auto-flags NEW damages
- Highlights pre-existing vs new
- Links to car diagram zones
- Quick CTA: "Generate Report"

**Why:** Instantly spot new damages = powerful dispute evidence

---

### Screen 6: Rental Passport PDF Export (Flighty-style)
**Inspiration:** Flighty's timeline-style flight "passport" reports  
**Dev Time:** 4-5 days  

Features:
- 4-page professional report:
  - **Page 1:** Cover (car image, provider logo, rental dates)
  - **Page 2:** Pickup inspection (date, location, GPS, pre-existing damages, 8 photos)
  - **Page 3:** Dropoff inspection (date, location, GPS, new damages, 8 photos)
  - **Page 4:** Summary (estimated repair costs, recommended actions, tamper-proof badges)
- GPS-stamped (immutable location)
- EXIF-verified (tamper detection)
- Print-ready (300dpi)
- Share options: email, WhatsApp, save, print

**Why:** Ready to show rental company/insurance immediately

---

### Screen 7: Settings + Share
**Dev Time:** 2-3 days  

Features:
- Profile (name, email, photo)
- Notifications (on/off, frequency)
- Privacy (data sharing preferences)
- Help & Support
- Export history (all rentals as CSV/PDF)
- About app + version

---

## Data Schema (Ready for Phase 2)

All data structured for async damage analysis backend:

```typescript
CarProfile {
  id, customer_id, rental_provider, make, model, year,
  license_plate, vin, rental_start, rental_end,
  pickup_location, dropoff_location, status, timestamps
}

RentalSession {
  id, car_profile_id, session_type ('pickup'|'dropoff'),
  timestamp, gps_location, pre_existing_damages[],
  inspection_photos[], is_complete, sync_status
}

InspectionPhoto {
  id, rental_session_id, angle_code, timestamp, gps_location,
  local_uri, cloud_uri, exif_data, upload_status, quality_score
}

RentalDocument {
  id, car_profile_id, document_type, extracted_data{},
  ocr_confidence, needs_manual_review, upload_status
}

DisputeReport {
  id, car_profile_id, report_title, sections{}, pdf_uri, status
}
```

---

## Competitive Advantage

### vs CarRentPal
- ✓ Have Ghost Mode
- ✓ PLUS: OCR document parsing
- ✓ PLUS: Interactive car diagram
- ✓ PLUS: Side-by-side comparison
- ✓ PLUS: Beautiful dashboard

### vs Not My Dent
- ✓ Have timestamp/GPS immutability
- **✓ PLUS: 2-3 min capture (vs their 15-20 min)**
- ✓ PLUS: Ghost Mode for consistency
- ✓ PLUS: Free (they charge premium)

### vs DAMAGE iD
- ✓ Have side-by-side + car diagram
- ✓ PLUS: Ghost Mode overlay
- ✓ PLUS: Document OCR
- ✓ PLUS: Free & beautiful (they charge $15+/mo)

### vs Myrentpad
- ✓ Have document OCR
- ✓ PLUS: Photo capture UX
- ✓ PLUS: Beautiful dashboard
- ✓ PLUS: Free (they charge $5/mo)

**WINNER:** RentalShield Phase 1 = Best-of-breed features + FREE + FASTEST

---

## Technology Stack

### Frontend (React Native + Expo)
```
expo init rentalshield
├── React Navigation (routing)
├── React Native Camera (photo capture)
├── SQLite (local storage)
├── Redux / Zustand (state)
├── Lottie (animations)
├── Google AdMob (ads)
└── react-native-image-crop-picker
```

### Backend (FastAPI)
```
FastAPI + Uvicorn
├── PostgreSQL (main database)
├── SQLAlchemy (ORM)
├── Claude Vision API (OCR)
├── S3 / Google Cloud Storage (photo uploads)
├── Celery (async tasks)
├── ReportLab (PDF generation)
└── Firebase Cloud Messaging (push notifications)
```

### Infrastructure
```
Deployment:
├── Heroku / Railway (backend)
├── S3 / GCS (photo storage)
├── Firebase Auth (login)
├── Sentry (error tracking)
└── GitHub Actions (CI/CD)
```

---

## 6-Week Timeline

### Week 1: Backend Foundation
- [ ] FastAPI project setup
- [ ] PostgreSQL schema (all tables)
- [ ] Claude Vision OCR integration
- [ ] S3/GCS configuration
- [ ] Firebase Auth setup

### Week 2-3: Frontend Foundation + Screens 1-3
- [ ] React Native project setup
- [ ] Navigation (auth + main)
- [ ] Dashboard (Revolut-style cards)
- [ ] Document Upload + OCR preview
- [ ] Photo Capture (Ghost Mode)
- [ ] Local SQLite setup

### Week 4: Screens 4-6
- [ ] Interactive Car Diagram
- [ ] Side-by-Side Comparison
- [ ] PDF generation (ReportLab)
- [ ] PDF export & share

### Week 5: Polish + Ads
- [ ] Animations (150ms transitions)
- [ ] Error boundaries
- [ ] AdMob integration (banner + rewarded)
- [ ] Background sync
- [ ] Push notifications

### Week 6: Testing + Launch
- [ ] E2E testing (all 7 screens)
- [ ] iOS App Store submission
- [ ] Google Play Store submission
- [ ] Soft launch + beta feedback
- [ ] Final fixes

### Week 7+: Growth
- [ ] Social media launch
- [ ] Press release
- [ ] Influencer partnerships
- [ ] Reddit/Twitter communities

---

## Quality Targets

| Metric | Target |
|--------|--------|
| Dashboard load time | < 1 second |
| Photo capture speed | 2-3 minutes (8 angles) |
| PDF generation | < 5 seconds |
| Crash-free rate | > 99.9% |
| Upload success rate | > 99% |
| Scroll FPS | 60 FPS (smooth) |
| Accessibility | WCAG AA |
| Offline functionality | 100% |

---

## Monetization

### Phase 1 (Free + Ads)
```
Revenue sources:
- Google AdMob banner ads: $2-5 per 1000 impressions
- Rewarded video ads: $10-30 per 1000 views
- Sponsored insurance ads (native)

Projected:
- 100k users → $500-2,000/month
```

### Phase 2 (Premium, $2.99/mo)
```
Teased in Phase 1:
- "AI Damage Detection (Coming Soon)"
- Email waitlist when available
- Show Phase 2 preview in PDF export

Phase 2 Features:
✓ Automatic damage detection (Gemini Vision)
✓ Damage severity scoring
✓ Insurance claim templates
✓ Ad-free experience
✓ Priority support

Conversion:
- 5-10% of Phase 1 users → 5-10k subscribers
- Revenue: $15,000-30,000/month
```

---

## Next Steps

**This Week:**
1. Review Phase 1 spec
2. Set up GitHub repo (frontend + backend folders)
3. Create Figma design mockups (all 7 screens)
4. Finalize tech stack decision

**Week 1:**
- Start FastAPI backend
- Initialize React Native project
- Design Dashboard screen first

**Deliverable:** Week 6 = App Store launch

---

## Appendix: Competitive Feature Matrix

| Feature | CarRentPal | Not My Dent | DAMAGE iD | Myrentpad | **Ours** |
|---------|-----------|-----------|----------|----------|---------|
| Ghost Mode | ✓ | ✗ | ✗ | ✗ | ✓✓ |
| Capture Speed | 3-4 min | **15-20 min** 🚨 | 5-7 min | 5-7 min | **2-3 min** ⭐ |
| Document OCR | ✗ | ✗ | ✗ | ✓ | ✓ |
| Car Diagram | ✗ | ✗ | ✓ | ✗ | ✓ |
| Side-by-Side | ✗ | ✗ | ✓ | ✗ | ✓ |
| Dashboard | ✗ | ✗ | ✗ | ✗ | ✓ |
| Offline | ✓ | ✓ | ✗ | ✗ | ✓✓ |
| Free | ✗ | ✗ | ✗ | ✗ | **✓** |
| PDF Report | ✓ | ✗ | ✓ | ✗ | ✓ |

**Verdict:** RentalShield Phase 1 beats all competitors on combination of features + speed + free + beautiful.

---

## References

- Architecture Doc: `DOCS/PHASE_1_ARCHITECTURE.md`
- UI Components: `DOCS/PHASE_1_UI_COMPONENTS.md`
- Competitive Analysis: `DOCS/PHASE_1_COMPETITIVE_ANALYSIS.md`

---

**Ready to build!** 🚀
