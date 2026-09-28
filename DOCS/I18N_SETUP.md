# RentalShield i18n (Internationalization) Setup

**Supported Languages:** English (en), Italiano (it), Español (es), Français (fr)

---

## Overview

RentalShield Phase 1 is fully internationalized from day 1. All text is translated into 4 languages with a fallback to English.

### Architecture

```
Backend (FastAPI):
├── Language middleware (detects user's language preference)
├── Translation JSON files (4 languages)
└── get_text() function for retrieving translations

Frontend (React Native):
├── i18next configuration
├── useTranslation() hook
└── Same JSON files (shared)

Language Detection Priority:
1. ?lang=en (query parameter)
2. Accept-Language header
3. User preference (cookie/database)
4. Default: English
```

---

## Backend Usage (FastAPI)

### 1. Add Middleware to App

```python
# src/rentalshield/api/app.py

from fastapi import FastAPI
from rentalshield.i18n.middleware import LanguageMiddleware

app = FastAPI()
app.add_middleware(LanguageMiddleware)
```

### 2. Use in Route Handlers

```python
from fastapi import Request
from rentalshield.i18n import get_text
from rentalshield.i18n.middleware import get_language

@app.get("/dashboard")
async def get_dashboard(request: Request):
    lang = get_language(request)
    
    # Get translated text
    welcome_text = get_text("dashboard.welcome", language=lang, name="John")
    # Returns: "Welcome, John" (or localized version)
    
    return {
        "welcome": welcome_text,
        "language": lang
    }
```

### 3. Get All Supported Languages

```python
from rentalshield.i18n import list_languages, SUPPORTED_LANGUAGES

@app.get("/languages")
async def get_languages(request: Request):
    lang = get_language(request)
    return {
        "languages": list_languages(),
        "current": lang,
        "supported": SUPPORTED_LANGUAGES
    }
```

---

## Frontend Usage (React Native)

### 1. Setup i18next

```typescript
// frontend/i18n.ts
import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from '@/i18n/translations/en.json';
import it from '@/i18n/translations/it.json';
import es from '@/i18n/translations/es.json';
import fr from '@/i18n/translations/fr.json';

i18next
  .use(initReactI18next)
  .init({
    resources: { en, it, es, fr },
    lng: 'en',
    fallbackLng: 'en',
    defaultNS: 'translation',
    ns: ['translation'],
    interpolation: {
      escapeValue: false,
      formatSeparator: ','
    },
    react: {
      useSuspense: false
    }
  });
```

### 2. Use in Components

```typescript
// frontend/screens/DashboardScreen.tsx
import { useTranslation } from 'react-i18next';

export const DashboardScreen = () => {
  const { t, i18n } = useTranslation();

  return (
    <View>
      <Text>{t('dashboard.welcome', { name: 'John' })}</Text>
      <Text>{t('dashboard.activeRental')}</Text>
      <TouchableOpacity onPress={() => i18n.changeLanguage('it')}>
        <Text>Italiano</Text>
      </TouchableOpacity>
    </View>
  );
};
```

### 3. Language Selector

```typescript
// frontend/screens/SettingsScreen.tsx
import { SUPPORTED_LANGUAGES } from '@/i18n/config';

export const SettingsScreen = () => {
  const { t, i18n } = useTranslation();

  return (
    <View>
      <Text>{t('settings.selectLanguage')}</Text>
      {SUPPORTED_LANGUAGES.map(lang => (
        <TouchableOpacity
          key={lang}
          onPress={() => i18n.changeLanguage(lang)}
        >
          <Text>
            {t(`common.language`)} {i18n.language === lang && '✓'}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
};
```

---

## Translation File Structure

Each translation file (en.json, it.json, es.json, fr.json) has the same structure:

```json
{
  "app": {
    "name": "RentalShield",
    "tagline": "Inspect. Protect. Document."
  },
  "dashboard": {
    "welcome": "Welcome, {{name}}",
    "activeRental": "Active Rental"
  },
  "common": {
    "ok": "OK",
    "cancel": "Cancel"
  }
}
```

### Key Naming Convention

- Nested keys use dot notation: `dashboard.welcome`
- Variables are wrapped in `{{variable}}`
- Plural forms use `_singular` and `_plural` suffixes
- Status/enum keys should match possible values

---

## Adding New Translations

### Step 1: Add to All Language Files

**en.json:**
```json
{
  "newFeature": {
    "title": "New Feature",
    "description": "This is a {{value}}"
  }
}
```

**it.json:**
```json
{
  "newFeature": {
    "title": "Nuova Funzione",
    "description": "Questo è {{value}}"
  }
}
```

**es.json & fr.json:** (same structure, different translations)

### Step 2: Use in Code

```typescript
// Frontend
const title = t('newFeature.title');
const description = t('newFeature.description', { value: 'example' });

// Backend
text = get_text('newFeature.title', language='en')
```

---

## Testing Translations

### Backend Test

```python
# tests/test_i18n.py

def test_get_text_english():
    from rentalshield.i18n import get_text
    
    text = get_text('dashboard.welcome', language='en', name='John')
    assert text == 'Welcome, John'


def test_get_text_italian():
    from rentalshield.i18n import get_text
    
    text = get_text('dashboard.welcome', language='it', name='Giovanni')
    assert 'Benvenuto' in text
```

### Frontend Test

```typescript
// frontend/__tests__/i18n.test.ts

import i18next from 'i18next';

describe('i18n', () => {
  it('should translate to English', () => {
    i18next.changeLanguage('en');
    expect(i18next.t('dashboard.welcome', { name: 'John' }))
      .toBe('Welcome, John');
  });

  it('should translate to Italian', () => {
    i18next.changeLanguage('it');
    expect(i18next.t('dashboard.welcome', { name: 'Giovanni' }))
      .toContain('Benvenuto');
  });
});
```

---

## Language Codes

| Code | Language | Region | Currency |
|------|----------|--------|----------|
| en | English | Global | USD |
| it | Italiano | Italia | EUR |
| es | Español | España/Latam | EUR/USD |
| fr | Français | France/Canada | EUR/CAD |

---

## API Language Header

All API responses should include:

```json
{
  "data": { ... },
  "language": "en",
  "supported_languages": ["en", "it", "es", "fr"],
  "timestamp": "2026-09-28T12:00:00Z"
}
```

### Example: GET /dashboard

**Request (English):**
```
GET /dashboard?lang=en
```

**Response:**
```json
{
  "language": "en",
  "data": {
    "welcome": "Welcome, John",
    "activeRental": "Active Rental"
  }
}
```

**Request (Italian):**
```
GET /dashboard?lang=it
```

**Response:**
```json
{
  "language": "it",
  "data": {
    "welcome": "Benvenuto, Giovanni",
    "activeRental": "Noleggio Attivo"
  }
}
```

---

## Best Practices

✅ **DO:**
- Use dot-notation keys (dashboard.welcome)
- Use variables for dynamic content ({{name}})
- Keep translations concise and clear
- Test all 4 languages before commit
- Update all 4 files when adding new strings

❌ **DON'T:**
- Hard-code strings in UI components
- Use string concatenation for translations
- Add UI-specific formatting in translations
- Forget to add English as fallback
- Mix different languages in same key

---

## Phase 2: RTL Languages

Future: Add support for right-to-left languages (Arabic, Hebrew) by adding:
- `"textDirection": "rtl"` to language config
- Layout adjustments in RTL mode
- File: `translations/ar.json`

---

## Files

```
src/rentalshield/i18n/
├── __init__.py                 # Main i18n functions
├── middleware.py               # FastAPI language middleware
├── models.py                   # Pydantic models
└── translations/
    ├── en.json                 # English (US)
    ├── it.json                 # Italian
    ├── es.json                 # Spanish
    └── fr.json                 # French

frontend/i18n/
├── config.ts                   # i18next config
├── hooks/useTranslation.ts     # React hook
└── translations/
    ├── en.json
    ├── it.json
    ├── es.json
    └── fr.json
```

---

## Useful Commands

```bash
# Test i18n loading
python -c "from rentalshield.i18n import list_languages; print(list_languages())"

# Validate JSON syntax
python -m json.tool src/rentalshield/i18n/translations/en.json

# Count total keys per language
for f in src/rentalshield/i18n/translations/*.json; do
  echo "$f: $(python -c "import json; print(len(json.load(open('$f'))))")"
done
```

---

**Ready to build Phase 1 in 4 languages!** 🌍

Generated: September 28, 2026  
Version: 1.0.0
