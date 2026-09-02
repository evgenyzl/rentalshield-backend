# RentalShield 🛡️

**AI-powered car rental damage protection.**

Film your rental car before driving away. RentalShield detects all visible damages using Claude Vision and compares them against the rental company's pre-existing condition report — so you're never wrongly charged for damage you didn't cause.

---

## Quick Start

```bash
# 1. Install
pip install -e ".[test]"

# 2. Configure
cp .env.example .env
#  → Add your ANTHROPIC_API_KEY to .env

# 3. Add your files
cp your_video.mp4        data/input/videos/
cp company_report.pdf    data/input/company_reports/rental_company_report.pdf

# 4. Run the audit (analyzes video with Claude Vision)
python scripts/audit.py data/input/videos/your_video.mp4

# 5. Compare with company report
python scripts/compare.py <session_id_from_step_4>
```

---

## Project Structure

```
rentalshield/
├── src/rentalshield/          # Core library
│   ├── models.py              # Data types (Damage, AuditSession, …)
│   ├── config.py              # Settings & env vars
│   ├── pipeline.py            # Orchestrator (audit + compare)
│   ├── video/extractor.py     # Frame extraction from video
│   ├── ai/
│   │   ├── analyzer.py        # Claude Vision damage detection
│   │   └── pdf_parser.py      # Parse rental company PDF
│   ├── compare/reconciler.py  # Match YOUR damages vs company list
│   ├── report/generator.py    # PDF report builder
│   └── utils/image.py         # Damage crop saving
│
├── scripts/                   # CLI entry points
│   ├── audit.py
│   └── compare.py
│
├── tests/
│   ├── unit/                  # Fast — no API calls, mocked Claude
│   │   ├── test_models.py
│   │   ├── test_reconciler.py
│   │   └── test_extractor.py
│   ├── integration/           # Slow — real Claude API + real video
│   │   └── test_pipeline.py
│   └── consistency/           # Key test: same frame × 5 runs
│       └── test_consistency.py
│
└── data/
    ├── input/
    │   ├── videos/            # Your car walkthrough videos (git-ignored)
    │   └── company_reports/   # Rental company PDFs (git-ignored)
    └── output/
        └── sessions/          # Per-run results (git-ignored)
            └── 20240814_143022/
                ├── damages.json       # Raw damage list (used by compare)
                ├── audit_report.pdf   # Full visual audit PDF
                └── crops/            # Cropped damage proof images
```

---

## Running Tests

```bash
# Fast unit tests (no API calls, ~5 seconds)
pytest tests/unit/ -v

# Consistency test — runs same 3 frames through Claude 5× each (~5 min)
pytest tests/consistency/ -m slow -v -s

# Full integration test (real video + real API, ~10 min)
pytest tests/integration/ -m integration -v -s

# All fast tests
pytest tests/unit/ tests/consistency/ -k "not slow" -v
```

---

## How It Works

```
Video → extract 1 frame/Ns → Claude Vision
                                   ↓
                           [SCRATCH, front left door]
                           [DENT, rear bumper, MODERATE]
                           ...
                                   ↓
                           damages.json + audit_report.pdf

Company PDF → pdfplumber → Claude parses damage list
                                   ↓
                           [existing damage 1, existing damage 2, ...]
                                   ↓
                           Claude reconciles both lists
                                   ↓
                           NEW (unprotected) | MATCHED | UNCERTAIN
                                   ↓
                           protection_report.pdf  ← show this to the company!
```

---

## Phone App Roadmap

The library is designed to be wrapped by a FastAPI backend for a mobile app:

```python
# Future: wrap pipeline.py in FastAPI endpoints
@app.post("/audit")
async def audit_video(video: UploadFile) -> AuditSession: ...

@app.post("/compare/{session_id}")
async def compare(session_id: str, report: UploadFile) -> ComparisonSession: ...
```

Planned:
- [ ] FastAPI backend (`pip install ".[api]"`)
- [ ] iOS / Android React Native app
- [ ] Push notification when analysis is ready
- [ ] Cloud storage for session history
- [ ] Share report link to send directly to rental company

---

## Configuration

All settings via `.env` (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required** |
| `RENTALSHIELD_CLAUDE_MODEL` | `claude-opus-4-5` | Model to use |
| `RENTALSHIELD_FRAME_INTERVAL_S` | `2` | Seconds between analyzed frames |
| `RENTALSHIELD_LOG_LEVEL` | `INFO` | Logging verbosity |
