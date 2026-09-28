# RentalShield 360 – Phase 1 UI/UX Component Breakdown
**Premium Travel App Experience (Inspired by Airbnb, Trip.com, Rydoo)**

---

## VISUAL DESIGN DIRECTION

**Aesthetic:** Modern, minimal, high-trust
- **Color Palette:** Deep blue (#1A365D) + coral accent (#FF6B5B) + cream (#F7F3EF)
- **Typography:** Outfit (display) + Inter (body) + JetBrains Mono (data)
- **Spacing:** 8px grid, generous whitespace
- **Components:** Soft rounded cards, no harsh shadows, subtle glassmorphism overlays
- **Interaction:** Smooth transitions (200-300ms), haptic feedback on captures, no jarring loads

---

## FEATURE BREAKDOWN & COMPONENTS

---

## 1. ONBOARDING & AUTHENTICATION

### 1.1 Welcome Screen
```
┌─────────────────────────────────┐
│  🚗 RentalShield                │
│  Inspect. Protect. Document.    │
│                                 │
│  [Tap to Continue] ────────────►│
└─────────────────────────────────┘
```

**Components:**
- Hero image (car silhouette, premium photography)
- Brand tagline
- CTA button with arrow animation
- Optional: Testimonial carousel

**Tech Stack:**
```typescript
// OnboardingWelcome.tsx
export const OnboardingWelcome = () => {
  const navigation = useNavigation()
  return (
    <SafeAreaView style={styles.container}>
      <LottieView
        source={require('./animations/car-reveal.json')}
        autoPlay
        loop={false}
        duration={1200}
      />
      <Text style={styles.tagline}>Inspect. Protect. Document.</Text>
      <PrimaryButton
        label="Get Started"
        onPress={() => navigation.navigate('DocumentUpload')}
        loading={false}
      />
    </SafeAreaView>
  )
}
```

### 1.2 Sign Up / Login Flow
- Email + password (or Apple ID / Google SSO)
- Simple 2-step form
- Error states with inline validation
- Loading state with spinner

**Components:**
- TextInput (custom: blue border on focus, error state)
- PrimaryButton
- SecondaryButton (forgot password link)
- ErrorBoundary (wrap entire form)

---

## 2. DOCUMENT UPLOAD & PARSING

### 2.1 Smart Document Ingestion Screen
```
┌─────────────────────────────────┐
│ 📄 Upload Rental Documents      │
│                                 │
│ [📱 Take Photo] [📁 Choose PDF] │
│                                 │
│ Supported: PDF, JPG, PNG        │
│ Size: < 10MB                    │
│                                 │
│ 📋 What we'll extract:          │
│  ✓ Rental provider              │
│  ✓ Car make & model             │
│  ✓ License plate                │
│  ✓ Rental dates                 │
│  ✓ Pre-existing damages         │
└─────────────────────────────────┘
```

**Components:**
- DocumentUploadCard (drag & drop for web, tap for mobile)
- FilePickerButton (camera + gallery options)
- InfoBox (what data we extract)
- LoadingIndicator (uploading...)
- ProgressBar (OCR processing)

**Tech Stack:**
```typescript
// DocumentUploadScreen.tsx
export const DocumentUploadScreen = () => {
  const [document, setDocument] = useState<RentalDocument | null>(null)
  const [parsing, setParsing] = useState(false)
  const [extractedData, setExtractedData] = useState(null)
  
  const handleDocumentPicked = async (file: File) => {
    setParsing(true)
    try {
      const response = await api.post('/documents/parse', {
        file,
        document_type: 'rental_contract'
      })
      setExtractedData(response.data)
      setDocument({ ...file, ...response.data })
    } catch (error) {
      showError('Failed to parse document. Please try again.')
    } finally {
      setParsing(false)
    }
  }
  
  return (
    <SafeAreaView style={styles.container}>
      <Header title="Upload Rental Documents" />
      <DocumentUploadCard onDocumentPicked={handleDocumentPicked} />
      {parsing && <ProgressIndicator label="Extracting rental details..." />}
      {extractedData && <ReviewExtractedData data={extractedData} />}
    </SafeAreaView>
  )
}
```

### 2.2 Review Extracted Data
```
┌─────────────────────────────────┐
│ ✓ Rental Details Extracted      │
│                                 │
│ Provider: Hertz ✓               │
│ Car: Ford Focus 2023 ✓          │
│ Plate: ABC-1234 ⚠️ (edit)       │
│ Rental: Sep 28 - Oct 5 ✓        │
│                                 │
│ Pre-existing:                   │
│ □ Front bumper scratch          │
│ □ Door ding (passenger side)    │
│                                 │
│ [Edit] [Confirm & Continue] ──►│
└─────────────────────────────────┘
```

**Components:**
- ExtractedFieldCard (editable, with confidence indicator)
- EditableTextField (inline edit with confirm/cancel)
- DamagePreviewList (checklist of pre-existing damages)
- ConfirmationButtons (Back, Confirm)
- InfoToast (high confidence: green checkmark, low: yellow warning)

---

## 3. CAR PROFILE & RENTAL SESSION SETUP

### 3.1 Auto-Populated Car Profile
```
┌─────────────────────────────────┐
│ 🚗 Your Rental Car              │
│                                 │
│ [Car Image Placeholder]         │
│  Ford Focus (2023)              │
│  Silver | License: ABC-1234     │
│                                 │
│ Rental Dates                    │
│ Sep 28, 10:00 AM → Oct 5, 10 AM│
│                                 │
│ Pickup: LAX Terminal 3          │
│ Dropoff: LAX Terminal 1         │
│                                 │
│ [View Full Details] [Next] ────►│
└─────────────────────────────────┘
```

**Components:**
- CarHeaderCard (image, name, plate, color)
- RentalTimelineCard (dates, locations)
- EditableProfileButton (pencil icon)
- PreExistingDamagesPreview (expandable list)

**Tech Stack:**
```typescript
// CarProfileScreen.tsx
export const CarProfileScreen = ({ carId }: Props) => {
  const [car, setCar] = useState<CarProfile | null>(null)
  const [loading, setLoading] = useState(true)
  
  useEffect(() => {
    const fetchCar = async () => {
      try {
        const data = await api.get(`/car-profiles/${carId}`)
        setCar(data)
      } catch (error) {
        showError('Failed to load car profile')
      } finally {
        setLoading(false)
      }
    }
    fetchCar()
  }, [carId])
  
  if (loading) return <LoadingScreen />
  if (!car) return <ErrorScreen />
  
  return (
    <SafeAreaView style={styles.container}>
      <CarHeaderCard car={car} />
      <RentalTimelineCard car={car} />
      <PreExistingDamagesCard damages={car.pre_existing_damages} />
      <PrimaryButton
        label="Start Inspection"
        onPress={() => navigation.navigate('PhotoCapture')}
      />
    </SafeAreaView>
  )
}
```

---

## 4. GUIDED PHOTO CAPTURE (8-ANGLE ROUTINE)

### 4.1 Photo Capture Layout
```
ANGLE GUIDE INTERFACE:

┌─────────────────────────────────┐
│ 🚗 Pickup Inspection (1/8)      │
│                                 │
│ [Live Camera Feed]              │
│  (with frame overlay)           │
│                                 │
│ 📍 FRONT - Full View            │
│ Make sure: Entire front is      │
│ visible, good lighting, no      │
│ shadows across bumper           │
│                                 │
│ ✓ Quality score: Good (92%)     │
│                                 │
│ [Tap to Capture] or [Hold 3s]  │
│ Captured: 1 photo               │
│ Next: FRONT_DETAIL              │
│                                 │
│ [← Back] [Skip] [Next →]        │
└─────────────────────────────────┘
```

**Components:**
- CameraViewport (with frame overlay guide)
- AngleGuidance (title + instructions)
- QualityIndicator (blur/brightness/framing score)
- CaptureButton (tap or 3-second hold)
- AngleProgressBar (1/8, 2/8, etc.)
- PhotoPreviewThumbnails (captured angles)
- ActionButtons (Back, Skip, Next)

**Tech Stack:**
```typescript
// PhotoCaptureScreen.tsx
import { Camera, useCameraDevice } from 'react-native-vision-camera'

export const PhotoCaptureScreen = ({ sessionId }) => {
  const camera = useRef<Camera>(null)
  const [currentAngleIndex, setCurrentAngleIndex] = useState(0)
  const [capturedPhotos, setCapturedPhotos] = useState<Record<string, boolean>>({})
  const [qualityScore, setQualityScore] = useState(0)
  
  const ANGLES = [
    { code: 'FRONT', desc: 'Front - Full View' },
    { code: 'REAR', desc: 'Rear - Full View' },
    { code: 'LEFT', desc: 'Left Side - Full View' },
    { code: 'RIGHT', desc: 'Right Side - Full View' },
    { code: 'FRONT_DETAIL', desc: 'Front Bumper - Detail' },
    { code: 'REAR_DETAIL', desc: 'Rear Bumper - Detail' },
    { code: 'LEFT_DETAIL', desc: 'Left Side - Detail' },
    { code: 'RIGHT_DETAIL', desc: 'Right Side - Detail' },
  ]
  
  const currentAngle = ANGLES[currentAngleIndex]
  
  const capturePhoto = async () => {
    if (!camera.current) return
    
    try {
      const photo = await camera.current.takePhoto({
        qualityPrioritization: 'speed',
        skipMetadata: false,
      })
      
      // Extract EXIF + validate
      const exif = await extractExifData(photo.path)
      const quality = await assessImageQuality(photo.path)
      setQualityScore(quality.score)
      
      // If quality < 60%, show warning but allow retry
      if (quality.score < 60) {
        showWarning(quality.suggestion)
        return
      }
      
      // Compress & save to local storage
      const optimized = await compressImage(photo.path, {
        maxWidth: 1024,
        maxHeight: 1024,
        quality: 0.8,
      })
      
      // Save to SQLite + local filesystem
      const savedPhoto = await savePhotoToLocal({
        session_id: sessionId,
        angle_code: currentAngle.code,
        file_path: optimized.path,
        exif: exif,
        timestamp: new Date().toISOString(),
        gps: await getDeviceLocation(),
      })
      
      setCapturedPhotos(prev => ({
        ...prev,
        [currentAngle.code]: true
      }))
      
      // Auto-advance to next angle
      if (currentAngleIndex < ANGLES.length - 1) {
        setCurrentAngleIndex(prev => prev + 1)
      } else {
        navigation.navigate('SessionReview', { sessionId })
      }
    } catch (error) {
      showError('Failed to capture photo')
      console.error(error)
    }
  }
  
  return (
    <SafeAreaView style={styles.container}>
      <CameraViewport
        camera={camera}
        angleCode={currentAngle.code}
        qualityScore={qualityScore}
      />
      <AngleGuidanceCard
        angle={currentAngle}
        qualityScore={qualityScore}
      />
      <AngleProgressBar
        current={currentAngleIndex + 1}
        total={ANGLES.length}
        capturedCount={Object.values(capturedPhotos).filter(Boolean).length}
      />
      <PhotoPreviewThumbnails
        photos={capturedPhotos}
        angles={ANGLES}
      />
      <CaptureButton
        onPress={capturePhoto}
        holdDuration={3000}
      />
      <ActionButtonRow
        onBack={() => setCurrentAngleIndex(prev => Math.max(0, prev - 1))}
        onSkip={() => setCurrentAngleIndex(prev => Math.min(prev + 1, ANGLES.length - 1))}
        onNext={() => setCurrentAngleIndex(prev => Math.min(prev + 1, ANGLES.length - 1))}
      />
    </SafeAreaView>
  )
}
```

### 4.2 Photo Quality Validation
```
Quality Checks (Real-time Feedback):
┌─────────────────────┐
│ Blur Detection  ✓   │
│ Brightness      ✓   │
│ Framing         ⚠️  │ ← adjust camera angle
│ Plate Visible   ✓   │
│ Glare           ⚠️  │ ← move to shade
│                     │
│ Overall: 78% Good   │
└─────────────────────┘
```

**Components:**
- QualityScoreMeter (circular progress with color: red < 60, yellow 60-80, green > 80)
- QualityCheckList (blur, brightness, framing, plate, glare)
- SuggestionToast (contextual guidance)

---

## 5. SESSION REVIEW & COMPLETION

### 5.1 Session Summary
```
┌─────────────────────────────────┐
│ ✓ Pickup Inspection Complete    │
│                                 │
│ All 8 angles captured           │
│ ✓ FRONT                         │
│ ✓ REAR                          │
│ ✓ LEFT                          │
│ ✓ RIGHT                         │
│ ✓ FRONT_DETAIL                  │
│ ✓ REAR_DETAIL                   │
│ ✓ LEFT_DETAIL                   │
│ ✓ RIGHT_DETAIL                  │
│                                 │
│ Photos: 8 (12.3 MB total)       │
│ Status: Uploading... (3/8)      │
│                                 │
│ [Save & Continue] or [Retake]  │
└─────────────────────────────────┘
```

**Components:**
- SessionHeaderCard (status, timestamp, location)
- CapturedAnglesGrid (thumbnail + angle name)
- StorageIndicator (total photos, MB used)
- SyncProgressBar (uploading status)
- ActionButtons (Save, Retake)

**Tech Stack:**
```typescript
// SessionReviewScreen.tsx
export const SessionReviewScreen = ({ sessionId }) => {
  const [session, setSession] = useState<RentalSession | null>(null)
  const [uploadProgress, setUploadProgress] = useState({
    total: 8,
    completed: 0,
  })
  
  useEffect(() => {
    const loadSession = async () => {
      const data = await getSessionFromDB(sessionId)
      setSession(data)
      
      // Auto-start background sync
      startBackgroundSync(sessionId, (progress) => {
        setUploadProgress(progress)
      })
    }
    loadSession()
  }, [sessionId])
  
  const handleSaveAndComplete = async () => {
    try {
      await updateSessionStatus(sessionId, {
        is_complete: true,
        completed_at: new Date().toISOString(),
      })
      showSuccess('Inspection saved & syncing in background')
      navigation.navigate('Dashboard')
    } catch (error) {
      showError('Failed to save session')
    }
  }
  
  return (
    <SafeAreaView style={styles.container}>
      <SessionHeaderCard session={session} />
      <CapturedAnglesGrid session={session} />
      <StorageIndicator session={session} />
      {uploadProgress.completed < uploadProgress.total && (
        <SyncProgressBar progress={uploadProgress} />
      )}
      <PrimaryButton
        label="Save & Continue"
        onPress={handleSaveAndComplete}
      />
      <SecondaryButton
        label="Retake Photos"
        onPress={() => navigation.goBack()}
      />
    </SafeAreaView>
  )
}
```

---

## 6. DASHBOARD & RENTAL HISTORY

### 6.1 Dashboard Overview
```
┌─────────────────────────────────┐
│ 👤 Welcome, John                │
│                                 │
│ 🔴 ACTIVE RENTAL                │
│ ┌─────────────────────────────┐ │
│ │ [Car Image]                 │ │
│ │ Ford Focus (Silver)         │ │
│ │ ABC-1234                    │ │
│ │ Hertz | LAX                 │ │
│ │ Pickup: Sep 28, 10 AM       │ │
│ │ Dropoff: Oct 5, 10 AM       │ │
│ │ Status: ✓ Inspected         │ │
│ │ [View Details] [Add Damage]│ │
│ └─────────────────────────────┘ │
│                                 │
│ 📋 PAST RENTALS                 │
│ ┌─────────────────────────────┐ │
│ │ Avis | Ford Mustang 2022    │ │
│ │ JKL-5678 | NYC              │ │
│ │ Sep 1 - Sep 10              │ │
│ │ Status: ✓ Completed         │ │
│ │ [View Report]               │ │
│ └─────────────────────────────┘ │
│                                 │
│ [Upload New Document] [Settings]│
└─────────────────────────────────┘
```

**Components:**
- DashboardHeader (user greeting, active rental count)
- ActiveRentalCard (large, with CTA actions)
- PastRentalsList (scrollable, with tap-to-expand)
- EmptyState (no rentals)
- FAB (upload new document)

**Tech Stack:**
```typescript
// DashboardScreen.tsx
export const DashboardScreen = () => {
  const [carProfiles, setCarProfiles] = useState<CarProfile[]>([])
  const [activeRental, setActiveRental] = useState<CarProfile | null>(null)
  const [pastRentals, setPastRentals] = useState<CarProfile[]>([])
  const [loading, setLoading] = useState(true)
  
  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const profiles = await getAllCarProfiles()
        setCarProfiles(profiles)
        
        // Separate active vs past
        const now = new Date()
        const active = profiles.find(p =>
          new Date(p.rental_end_date) > now
        )
        const past = profiles.filter(p =>
          new Date(p.rental_end_date) <= now
        )
        
        setActiveRental(active || null)
        setPastRentals(past)
      } catch (error) {
        showError('Failed to load dashboard')
      } finally {
        setLoading(false)
      }
    }
    loadDashboard()
  }, [])
  
  if (loading) return <LoadingScreen />
  
  return (
    <SafeAreaView style={styles.container}>
      <ScrollView>
        <DashboardHeader activeCount={activeRental ? 1 : 0} />
        
        {activeRental && (
          <ActiveRentalCard
            car={activeRental}
            onViewDetails={() => navigation.navigate('CarProfile', { carId: activeRental.id })}
            onAddDamage={() => navigation.navigate('PhotoCapture', { carId: activeRental.id })}
          />
        )}
        
        {pastRentals.length > 0 && (
          <PastRentalsList
            rentals={pastRentals}
            onRentalPress={(car) => navigation.navigate('CarProfile', { carId: car.id })}
          />
        )}
        
        {carProfiles.length === 0 && <EmptyStateGetStarted />}
      </ScrollView>
      
      <FAB
        icon="plus"
        label="Upload Document"
        onPress={() => navigation.navigate('DocumentUpload')}
      />
    </SafeAreaView>
  )
}
```

### 6.2 Car Profile Details
```
┌─────────────────────────────────┐
│ ← Ford Focus (ABC-1234)         │
│                                 │
│ 🎯 INSPECTION STATUS            │
│ Pickup: ✓ Sep 28 10:23 AM       │
│ Location: LAX Terminal 3        │
│ Photos: 8/8 captured            │
│ Status: ✓ Synced                │
│                                 │
│ Dropoff: ○ Not started          │
│ Location: LAX Terminal 1        │
│ Estimated: Oct 5 10:00 AM       │
│                                 │
│ 📸 SIDE-BY-SIDE COMPARISON      │
│ [Pickup Carousel] [Dropoff]     │
│                                 │
│ 📄 RENTAL DOCUMENTS             │
│ ✓ Rental Contract               │
│ ✓ Pickup Form                   │
│                                 │
│ [Generate Report] [Edit Profile]│
└─────────────────────────────────┘
```

**Components:**
- InspectionStatusCard (pickup/dropoff progress)
- ComparisonCarousel (side-by-side photo viewer)
- DocumentsList (uploaded PDFs, with view option)
- ReportGeneratorButton (export PDF passport)

---

## 7. DISPUTE REPORT GENERATOR

### 7.1 Report Generation Flow
```
User taps: "Generate Inspection Passport"
  ↓
Backend prepares PDF:
  1. Cover page (car details, dates, provider logo)
  2. Pickup inspection section
     - Timestamp, location, GPS
     - Pre-existing damages checklist
     - Photos (all 8 angles)
  3. Dropoff inspection section (if completed)
     - Timestamp, location, GPS
     - Found damages
     - Photos (all 8 angles)
  4. Summary & next steps
  ↓
PDF saved to local storage + cloud
  ↓
Share options: Email, WhatsApp, Save to Files, Print
```

**Components:**
- ReportGenerationModal (show progress)
- ReportPreviewScreen (PDF viewer)
- ShareOptionsMenu (email, whatsapp, save, print)

**Tech Stack:**
```typescript
// ReportGeneratorScreen.tsx
export const ReportGeneratorScreen = ({ carId }) => {
  const [generating, setGenerating] = useState(false)
  const [reportId, setReportId] = useState<string | null>(null)
  const [pdfUri, setPdfUri] = useState<string | null>(null)
  
  const generateReport = async () => {
    setGenerating(true)
    try {
      const response = await api.post(`/reports/${carId}/generate`, {
        report_type: 'dispute_passport'
      })
      
      setReportId(response.data.report_id)
      
      // Poll for completion
      let completed = false
      let attempts = 0
      while (!completed && attempts < 60) {
        const status = await api.get(`/reports/${response.data.report_id}/status`)
        if (status.data.status === 'ready') {
          setPdfUri(status.data.pdf_uri)
          completed = true
        }
        attempts++
        await new Promise(r => setTimeout(r, 1000))
      }
    } catch (error) {
      showError('Failed to generate report')
    } finally {
      setGenerating(false)
    }
  }
  
  const shareReport = async () => {
    if (!pdfUri) return
    
    try {
      await Share.open({
        url: pdfUri,
        title: 'Inspection Passport',
        message: 'Here is my rental car inspection report',
      })
    } catch (error) {
      console.error(error)
    }
  }
  
  return (
    <SafeAreaView style={styles.container}>
      {!pdfUri ? (
        <>
          <Header title="Generate Report" />
          <ReportInfoCard />
          <PrimaryButton
            label={generating ? 'Generating...' : 'Generate Inspection Passport'}
            onPress={generateReport}
            loading={generating}
          />
        </>
      ) : (
        <>
          <PDFViewer uri={pdfUri} />
          <ShareButtonRow
            onShare={shareReport}
            onDownload={() => downloadPDF(pdfUri)}
          />
        </>
      )}
    </SafeAreaView>
  )
}
```

---

## 8. COMPONENT LIBRARY (Reusable Building Blocks)

```typescript
// components/buttons/
- PrimaryButton.tsx      // Main CTA (blue, 48px height)
- SecondaryButton.tsx    // Alternative action (outline)
- DangerButton.tsx       // Destructive action (red)
- FAB.tsx               // Floating action button

// components/inputs/
- TextField.tsx         // Text input with label, error state
- DatePicker.tsx        // Date selection
- FileUpload.tsx        // File picker

// components/cards/
- ProfileCard.tsx       // Car profile preview
- SessionCard.tsx       // Inspection session card
- DocumentCard.tsx      // Document preview

// components/indicators/
- LoadingSpinner.tsx    // Animated loading
- ProgressBar.tsx       // Linear progress
- CircleProgress.tsx    // Circular progress meter
- Badge.tsx            // Status badges

// components/layout/
- SafeAreaView.tsx      // Consistent safe area padding
- Container.tsx         // Standard padding container
- Header.tsx           // Screen header with back button
- BottomSheet.tsx      // Modal sheet from bottom

// components/feedback/
- Toast.tsx            // Temporary notification
- Alert.tsx            // Modal alert
- ErrorBoundary.tsx    // Error boundary wrapper
- EmptyState.tsx       // Empty list fallback

// hooks/
- useAsync.ts          // Async data fetching
- useForm.ts           // Form state management
- useStorage.ts        // Local storage access
- useSync.ts           // Background sync management
```

---

## 9. OFFLINE-FIRST ARCHITECTURE

### Local Storage Strategy

```typescript
// Database: SQLite (via expo-sqlite or WatermelonDB)
// File Storage: FileSystem (expo-file-system)
// State Management: Redux or Zustand
// Background Tasks: Expo TaskManager + Background Fetch

// Sync Manager (runs every 30s or on WiFi detection)
export const useSyncManager = () => {
  const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'error'>('idle')
  
  useEffect(() => {
    const syncInterval = setInterval(async () => {
      try {
        setSyncStatus('syncing')
        
        // Get pending items from queue
        const pendingItems = await db.getSync queue.get_pending()
        
        if (pendingItems.length === 0) {
          setSyncStatus('idle')
          return
        }
        
        // Check connectivity
        const isOnline = await NetInfo.fetch().then(s => s.isConnected)
        if (!isOnline) {
          setSyncStatus('idle')
          return
        }
        
        // Process sync queue (batch uploads)
        for (const item of pendingItems) {
          try {
            await uploadToBackend(item)
            await db.syncQueue.markSynced(item.id)
          } catch (error) {
            await db.syncQueue.recordError(item.id, error.message)
          }
        }
        
        setSyncStatus('idle')
      } catch (error) {
        setSyncStatus('error')
      }
    }, 30000) // Every 30 seconds
    
    return () => clearInterval(syncInterval)
  }, [])
  
  return { syncStatus }
}
```

---

## 10. ERROR HANDLING & LOADING STATES

### Global Error Boundary
```typescript
// Root error boundary wraps entire app
<AppErrorBoundary>
  <Navigation />
</AppErrorBoundary>

// Per-screen error boundaries
<ScreenContainer>
  <SafePhotoViewer />  // ← wrapped in error boundary
  <SafeSessionView />  // ← wrapped in error boundary
</ScreenContainer>
```

### Loading State Patterns
```
// Skeleton loading (preferred for perceived performance)
if (loading) return <CarProfileSkeleton />

// Spinner (for short async operations)
if (loading) return <LoadingSpinner />

// Full screen loader (rare, for critical operations)
if (initializing) return <InitialLoadingScreen />
```

---

## 11. PHASE 1 SCREEN HIERARCHY

```
RootStack
├── AuthStack
│   ├── Onboarding
│   ├── SignUp
│   └── Login
└── MainStack
    ├── Dashboard
    ├── DocumentUpload
    │   └── ReviewExtractedData
    ├── CarProfile
    │   ├── PhotoCapture (8-angle loop)
    │   ├── SessionReview
    │   └── ReportGenerator
    └── Settings
        ├── Profile
        ├── Notifications
        └── Help & Support
```

---

## 12. PERFORMANCE TARGETS

| Screen | First Load | Interaction Response | Scroll FPS |
|--------|-----------|----------------------|-----------|
| Dashboard | < 1.0s | < 100ms | 60 FPS |
| Car Profile | < 0.8s | < 100ms | 60 FPS |
| Photo Capture | < 1.5s | < 50ms | 60 FPS |
| Report Preview | < 2.0s | < 150ms | 60 FPS |

---

## 13. ACCESSIBILITY & INTERNATIONALIZATION

### Accessibility (A11y)
```typescript
// All interactive elements have accessible labels
<TouchableOpacity
  accessible={true}
  accessibilityLabel="Capture photo"
  accessibilityHint="Double tap to take a photo of the car angle"
  onPress={capturePhoto}
>
  <Text>📷 Capture</Text>
</TouchableOpacity>

// Color contrast: WCAG AA (4.5:1 minimum)
// Font size: 14pt minimum for body text
// Touch targets: 48x48 minimum
```

### i18n Support
```typescript
// Supported: EN, ES, IT, FR, DE
// Uses i18next + react-i18next
import { useTranslation } from 'react-i18next'

export const DashboardScreen = () => {
  const { t } = useTranslation()
  return <Text>{t('dashboard.welcome', { name: 'John' })}</Text>
}
```

---

## SUMMARY: Phase 1 is UI-First, Backend-Ready

This component architecture delivers a **premium travel-app experience** (Airbnb-quality) while keeping the codebase structured for Phase 2's async damage analysis. Every screen is:

✓ Offline-capable  
✓ Background-sync friendly  
✓ Error-boundary protected  
✓ Accessibility-compliant  
✓ Performance-optimized  

**Next: Phase 1 Deliverables** → React Native codebase + FastAPI backend endpoints ready for Phase 2 ML integration.
