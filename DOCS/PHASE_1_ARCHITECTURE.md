# RentalShield 360 – Phase 1 Architecture & Design
**Premium B2C UX + Document Parsing (No Live AI)**

---

## 1. DATA SCHEMA

### 1.1 Core Data Models (SQLite + Watermelon Sync)

```typescript
// ============================================
// CAR PROFILE (Rental Vehicle Details)
// ============================================
interface CarProfile {
  id: string                          // UUID
  customer_id: string                 // User who owns this profile
  
  // Auto-populated from rental document
  rental_provider: string             // e.g., "Hertz", "Sixt", "Avis"
  make: string                        // e.g., "Ford"
  model: string                       // e.g., "Focus"
  year?: number                       // e.g., 2023
  license_plate: string               // e.g., "ABC-1234"
  vin?: string                        // Vehicle ID Number (if extractable)
  color?: string                      // e.g., "Silver"
  mileage_at_pickup?: number          // From rental document
  
  // Rental timeline
  rental_start_date: ISO8601string    // e.g., "2026-09-28T10:00:00Z"
  rental_end_date: ISO8601string
  pickup_location: string             // e.g., "LAX Terminal 3"
  dropoff_location: string
  
  // Status & metadata
  status: "active" | "completed" | "disputed"
  created_at: ISO8601string
  updated_at: ISO8601string
  
  // Relations
  rental_sessions: RentalSession[]    // (pickup + dropoff inspections)
  rental_documents: RentalDocument[]  // PDFs, photos of contracts
}

// ============================================
// RENTAL SESSION (Pickup & Dropoff Inspection)
// ============================================
interface RentalSession {
  id: string                          // UUID
  car_profile_id: string              // FK to CarProfile
  
  // Session type
  session_type: "pickup" | "dropoff"  // or "interim-check"
  
  // Time & location stamp
  timestamp: ISO8601string            // When inspection happened
  gps_location?: {
    latitude: number
    longitude: number
    accuracy_meters?: number
    address?: string
  }
  
  // Pre-existing damages (from rental doc, user input)
  // Only populated for pickup sessions
  pre_existing_damages?: {
    location: string                  // e.g., "front bumper"
    description: string               // e.g., "small scratch"
    severity: "minor" | "moderate" | "major"
    photo_ids?: string[]              // References to InspectionPhoto[]
  }[]
  
  // Photos taken during this session
  inspection_photos: InspectionPhoto[]
  
  // Session completion
  is_complete: boolean                // All 8 angles captured?
  completed_at?: ISO8601string
  sync_status: "pending" | "syncing" | "synced" | "error"
  sync_error?: string
  
  created_at: ISO8601string
  updated_at: ISO8601string
}

// ============================================
// INSPECTION PHOTO (Damage Evidence)
// ============================================
interface InspectionPhoto {
  id: string                          // UUID
  rental_session_id: string           // FK to RentalSession
  
  // Angle & metadata
  angle_code: "FRONT" | "REAR" | "LEFT" | "RIGHT" 
           | "FRONT_DETAIL" | "REAR_DETAIL" | "LEFT_DETAIL" | "RIGHT_DETAIL"
  angle_description: string           // e.g., "Front bumper - full view"
  
  // File metadata
  original_filename: string
  local_uri: string                   // file:// URI for offline access
  cloud_uri?: string                  // s3:// or gs:// URI after upload
  
  // Immutable metadata (set at capture, never changed)
  timestamp: ISO8601string            // Exact time photo was taken
  gps_location?: {
    latitude: number
    longitude: number
    accuracy_meters?: number
  }
  
  // Image data
  original_size_bytes: number         // Original resolution
  optimized_size_bytes: number        // After compression (max 1024x1024)
  width: number                       // Original dimensions
  height: number
  
  // Quality & processing
  image_quality: "high" | "medium" | "low"
  is_blurry?: boolean                 // Basic local analysis
  is_dark?: boolean
  
  // EXIF data (tamper detection)
  exif_data?: {
    device_make: string               // e.g., "Apple"
    device_model: string              // e.g., "iPhone 14 Pro"
    timestamp: ISO8601string          // From EXIF
    is_tampered?: boolean             // Mismatch with local timestamp?
  }
  
  // Sync & status
  upload_status: "pending" | "uploading" | "uploaded" | "error"
  upload_error?: string
  
  created_at: ISO8601string
  updated_at: ISO8601string
}

// ============================================
// RENTAL DOCUMENT (Contracts, Check-in PDFs)
// ============================================
interface RentalDocument {
  id: string                          // UUID
  car_profile_id: string              // FK to CarProfile
  
  document_type: "rental_contract" | "checkout_form" | "insurance" | "other"
  
  // File metadata
  original_filename: string
  file_size_bytes: number
  mime_type: string                   // "application/pdf" or "image/jpeg"
  local_uri: string                   // Offline storage path
  cloud_uri?: string
  
  // Extracted data (from OCR/parsing)
  extracted_data?: {
    rental_provider: string?
    car_make: string?
    car_model: string?
    car_year: number?
    license_plate: string?
    vin: string?
    rental_start: ISO8601string?
    rental_end: ISO8601string?
    pickup_location: string?
    dropoff_location: string?
    pickup_mileage: number?
    pre_existing_damages: {
      location: string
      description: string
      severity: "minor" | "moderate" | "major"
    }[]
  }
  
  // Quality & confidence
  ocr_confidence: number              // 0.0 to 1.0
  needs_manual_review: boolean        // High confidence issue?
  
  // Sync status
  upload_status: "pending" | "uploading" | "uploaded" | "error"
  
  uploaded_at?: ISO8601string
  created_at: ISO8601string
  updated_at: ISO8601string
}

// ============================================
// DISPUTE REPORT (Generated PDF Export)
// ============================================
interface DisputeReport {
  id: string                          // UUID
  car_profile_id: string              // FK to CarProfile
  
  report_title: string                // e.g., "Inspection Passport - Ford Focus"
  
  // Report contents (structured)
  sections: {
    cover_page: {
      title: string
      rental_provider: string
      car_details: string
      rental_dates: string
      generated_timestamp: ISO8601string
    }
    pickup_inspection: {
      timestamp: ISO8601string
      location: string
      pre_existing_damages: string[]
      photos: { angle: string, uri: string }[]
    }
    dropoff_inspection: {
      timestamp: ISO8601string
      location: string
      found_damages?: string[]
      photos: { angle: string, uri: string }[]
    }
    summary: {
      new_damages_found: string[]
      estimated_cost?: string
      recommended_action: string
    }
  }
  
  // Export state
  pdf_generated_at?: ISO8601string
  pdf_uri?: string                    // file:// or s3://
  pdf_size_bytes?: number
  
  created_at: ISO8601string
  updated_at: ISO8601string
}
```

---

## 2. DATABASE SCHEMA (SQLite + WatermelonDB)

```sql
-- Car Profiles (auto-populated from rental documents)
CREATE TABLE car_profiles (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  rental_provider TEXT,
  make TEXT,
  model TEXT,
  year INTEGER,
  license_plate TEXT NOT NULL UNIQUE,
  vin TEXT,
  color TEXT,
  mileage_at_pickup INTEGER,
  rental_start_date TEXT,
  rental_end_date TEXT,
  pickup_location TEXT,
  dropoff_location TEXT,
  status TEXT DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(customer_id) REFERENCES users(id)
);

-- Rental Sessions (Pickup & Dropoff inspections)
CREATE TABLE rental_sessions (
  id TEXT PRIMARY KEY,
  car_profile_id TEXT NOT NULL,
  session_type TEXT NOT NULL, -- 'pickup' | 'dropoff'
  timestamp TEXT NOT NULL,
  gps_latitude REAL,
  gps_longitude REAL,
  gps_accuracy REAL,
  gps_address TEXT,
  pre_existing_damages_json TEXT, -- JSON array
  is_complete BOOLEAN DEFAULT 0,
  completed_at TEXT,
  sync_status TEXT DEFAULT 'pending',
  sync_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(car_profile_id) REFERENCES car_profiles(id)
);

-- Inspection Photos (8 angles per session)
CREATE TABLE inspection_photos (
  id TEXT PRIMARY KEY,
  rental_session_id TEXT NOT NULL,
  angle_code TEXT NOT NULL, -- FRONT, REAR, etc.
  angle_description TEXT,
  original_filename TEXT,
  local_uri TEXT NOT NULL,
  cloud_uri TEXT,
  timestamp TEXT NOT NULL,
  gps_latitude REAL,
  gps_longitude REAL,
  gps_accuracy REAL,
  original_size_bytes INTEGER,
  optimized_size_bytes INTEGER,
  width INTEGER,
  height INTEGER,
  image_quality TEXT DEFAULT 'medium',
  is_blurry BOOLEAN,
  is_dark BOOLEAN,
  exif_device_make TEXT,
  exif_device_model TEXT,
  exif_timestamp TEXT,
  is_tampered BOOLEAN,
  upload_status TEXT DEFAULT 'pending',
  upload_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(rental_session_id) REFERENCES rental_sessions(id)
);

-- Rental Documents (PDFs, photos of contracts)
CREATE TABLE rental_documents (
  id TEXT PRIMARY KEY,
  car_profile_id TEXT NOT NULL,
  document_type TEXT NOT NULL,
  original_filename TEXT,
  file_size_bytes INTEGER,
  mime_type TEXT,
  local_uri TEXT NOT NULL,
  cloud_uri TEXT,
  extracted_data_json TEXT, -- JSON with OCR results
  ocr_confidence REAL,
  needs_manual_review BOOLEAN,
  upload_status TEXT DEFAULT 'pending',
  uploaded_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(car_profile_id) REFERENCES car_profiles(id)
);

-- Dispute Reports (Generated PDFs)
CREATE TABLE dispute_reports (
  id TEXT PRIMARY KEY,
  car_profile_id TEXT NOT NULL,
  report_title TEXT,
  sections_json TEXT, -- Full report structure
  pdf_generated_at TEXT,
  pdf_uri TEXT,
  pdf_size_bytes INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(car_profile_id) REFERENCES car_profiles(id)
);

-- Indexes for common queries
CREATE INDEX idx_car_profiles_customer_id ON car_profiles(customer_id);
CREATE INDEX idx_rental_sessions_car_profile_id ON rental_sessions(car_profile_id);
CREATE INDEX idx_inspection_photos_rental_session_id ON inspection_photos(rental_session_id);
CREATE INDEX idx_rental_documents_car_profile_id ON rental_documents(car_profile_id);
```

---

## 3. API ENDPOINTS (Backend - Phase 1)

### Document Parsing & OCR

```
POST /api/v1/documents/parse
  Params: { file: File (PDF/Image), document_type: string }
  Returns: {
    extracted_data: { ... },
    ocr_confidence: 0.0-1.0,
    needs_review: boolean,
    parsed_at: ISO8601string
  }

POST /api/v1/documents/upload
  Params: { file: File, document_id: string }
  Returns: { cloud_uri: string, status: 'uploaded' }

GET /api/v1/documents/{document_id}
  Returns: { ... RentalDocument data ... }
```

### Photo Upload & Sync

```
POST /api/v1/photos/upload
  Params: { photo_id: string, file: File, metadata: {...} }
  Returns: { cloud_uri: string, status: 'uploaded' }

POST /api/v1/sessions/{session_id}/sync
  Params: { photos: [{ id, status }], metadata: {...} }
  Returns: { synced_count: number, errors: [...] }
```

### Car Profiles & Sessions

```
GET /api/v1/car-profiles
  Returns: [CarProfile]

POST /api/v1/car-profiles
  Params: { make, model, license_plate, ... }
  Returns: { id: string, ... }

GET /api/v1/car-profiles/{car_id}
  Returns: { CarProfile + nested sessions + photos }

POST /api/v1/car-profiles/{car_id}/sessions
  Params: { session_type: 'pickup'|'dropoff', timestamp, gps_location }
  Returns: { session_id: string, status: 'active' }

POST /api/v1/sessions/{session_id}/complete
  Params: { timestamp: ISO8601string }
  Returns: { completed: true, all_8_angles: boolean }
```

### Report Generation

```
POST /api/v1/reports/{car_id}/generate
  Params: { report_type: 'dispute_passport' }
  Returns: { report_id: string, pdf_uri: string, status: 'generating' }

GET /api/v1/reports/{report_id}/status
  Returns: { status: 'generating' | 'ready' | 'error', pdf_uri?: string }

POST /api/v1/reports/{report_id}/download
  Returns: { File (PDF) }
```

---

## 4. LOCAL SYNC & OFFLINE STRATEGY

### Sync Queue (SQLite)

```typescript
interface SyncQueueItem {
  id: string
  entity_type: "photo" | "document" | "session_metadata"
  entity_id: string
  action: "create" | "update" | "delete"
  payload: Record<string, any>
  retry_count: number
  last_error?: string
  created_at: ISO8601string
}
```

**Sync Behavior:**
- Local changes → added to sync queue immediately
- Background sync worker processes queue (batched every 30s or on WiFi detection)
- Exponential backoff on failure: 5s → 10s → 30s → 2min → 5min
- No blocking: UI remains responsive while syncing
- Conflict resolution: server timestamp wins, but user is notified

---

## 5. OFFLINE DATA FLOW

```
User Takes Photo
  ↓
Local Metadata Capture (timestamp, GPS)
  ↓
Image Optimization (1024x1024, JPEG 80%)
  ↓
SQLite + Device Storage (file://)
  ↓
Sync Queue Entry Created
  ↓
Background Sync Worker
  ├─ WiFi detected? → Prioritize upload
  ├─ Upload to S3/GCS
  └─ Update cloud_uri + sync_status
  
Offline: User can continue capturing, app works normally
  ↓
Online: Auto-sync in background (non-blocking)
  ↓
All photos synced → Session marked "ready for analysis" (Phase 2)
```

---

## 6. DOCUMENT PARSING FLOW (OCR/Vision)

```
User Uploads Rental Contract PDF
  ↓
Client: Local file storage + sync queue
  ↓
Backend: Process with Claude Vision API (temp: 0.0)
  ├─ Extract: Provider, Car, License Plate, Dates, Locations
  ├─ Extract: Pre-existing Damages (structured list)
  └─ Confidence scoring per field
  ↓
Return: { extracted_data, ocr_confidence, needs_review }
  ↓
Client: Display results
  ├─ High confidence → Auto-populate car profile
  └─ Low confidence → User review + manual edit
  ↓
Save to CarProfile (auto-sync to backend)
```

**Parsing Prompt (temperature: 0.0, deterministic):**

```
You are a rental document OCR specialist.
Extract the following fields from this rental contract/inspection form:
1. Rental Provider (e.g., "Hertz", "Sixt")
2. Car: Make, Model, Year
3. License Plate
4. VIN (if visible)
5. Rental Start Date (ISO 8601)
6. Rental End Date (ISO 8601)
7. Pick-up Location
8. Drop-off Location
9. Pre-existing Damages (list with location + severity: minor/moderate/major)

Return ONLY valid JSON (no markdown, no explanation):
{
  "rental_provider": "string",
  "car_make": "string",
  "car_model": "string",
  "car_year": number,
  "license_plate": "string",
  "vin": "string or null",
  "rental_start": "ISO8601",
  "rental_end": "ISO8601",
  "pickup_location": "string",
  "dropoff_location": "string",
  "pre_existing_damages": [
    {"location": "string", "description": "string", "severity": "minor|moderate|major"}
  ]
}
```

---

## 7. QUALITY ASSURANCE & ERROR HANDLING

### Local Validation (before upload)

```typescript
validatePhoto(photo: InspectionPhoto): ValidationResult {
  // ✓ File exists at local_uri
  // ✓ EXIF timestamp within 1 minute of capture time
  // ✓ Image dimensions match expected range
  // ✓ File size < 5MB
  // ✓ Angle code valid
  return { isValid, errors: [] }
}

validateSession(session: RentalSession): ValidationResult {
  // ✓ All 8 angles captured
  // ✓ All photos validated
  // ✓ Session completed within rental dates
  return { isValid, errors: [] }
}
```

### Error Boundaries

```typescript
// SafePhoto Component
export const SafePhotoViewer = ({ photoId }) => {
  return (
    <ErrorBoundary fallback={<PhotoNotAvailable />}>
      <Photo id={photoId} />
    </ErrorBoundary>
  )
}

// SafeSession Component
export const SafeSessionView = ({ sessionId }) => {
  return (
    <ErrorBoundary fallback={<SessionError />}>
      <SessionDetail id={sessionId} />
    </ErrorBoundary>
  )
}
```

---

## 8. PERFORMANCE & DETERMINISM

| Metric | Target |
|--------|--------|
| Photo capture → ready to upload | < 2 seconds |
| 8 photos captured + compressed | < 30 seconds |
| Session sync completion (good WiFi) | < 60 seconds |
| Dashboard load (from cache) | < 500ms |
| Document OCR (backend) | < 5 seconds |
| PDF report generation | < 10 seconds |
| Temperature setting (OCR) | 0.0 (deterministic) |

---

## SUMMARY: Data is "Phase-2 Ready"

All photo metadata, rental details, and documents are structured to feed directly into Phase 2's async damage analysis pipeline. The backend will simply process the sync queue and run Gemini Vision on the stored photos — **no client-side blocking**.

