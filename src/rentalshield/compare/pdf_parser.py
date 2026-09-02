"""
Parse rental company inspection PDFs to extract their pre-existing damage list.

Supports Italian, English, French, Spanish, and German language contracts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pdfplumber
from loguru import logger

from rentalshield.ai.base import BaseAnalyzer


_PARSE_PROMPT = """\
You are reading a car rental inspection / condition report.  The text may be in
Italian, English, French, Spanish, German, or another language — translate as
needed.

Your task: extract EVERY damage item listed in this document.

For each damage, return a JSON object:
{{
  "type":     "SCRATCH | DENT | CHIP | CRACK | SCUFF | RUST | MISSING | OTHER",
  "location": "translated English description of the car part/zone",
  "severity": "MINOR | MODERATE | SEVERE | UNKNOWN",
  "notes":    "verbatim quote or short paraphrase from the document (original language OK)"
}}

Common Italian → English translations for car parts:
  parabrezza → windshield   |  paraurti → bumper   |  porta → door
  cofano → hood/bonnet      |  parafango → fender   |  cerchione → wheel rim
  retrovisore → mirror      |  tetto → roof         |  portellone → trunk/boot
  graffio → scratch         |  ammaccatura → dent   |  scheggiatura → chip
  anteriore → front         |  posteriore → rear    |  destro → right  |  sinistro → left
  grave → severe            |  lieve → minor        |  modanatura → moulding/trim

Return a JSON array.  If no damages are listed, return [].
Reply with ONLY the raw JSON array — no markdown, no explanation.

--- DOCUMENT TEXT ---
{text}
--- END ---"""


class CompanyPDFParser:
    """Extracts the rental company's pre-existing damage list from their PDF."""

    def __init__(self, analyzer: BaseAnalyzer):
        self._analyzer = analyzer

    def parse(self, pdf_path: Path) -> list[dict[str, Any]]:
        """
        Parse a rental company inspection PDF.

        Returns a list of dicts:
          {type, location, severity, notes}
        """
        text = self._extract_damage_pages(pdf_path)
        if not text:
            logger.warning("CompanyPDFParser: no text extracted from {}", pdf_path.name)
            return []

        logger.info("CompanyPDFParser: sending {} chars to AI", len(text))

        prompt = _PARSE_PROMPT.format(text=text[:12000])
        raw = self._analyzer.generate_text(prompt)

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            items: list[dict] = json.loads(raw)
            logger.info("CompanyPDFParser: found {} damage item(s)", len(items))
            return items
        except json.JSONDecodeError as exc:
            logger.error("CompanyPDFParser: JSON parse failed — {!r} ({})", raw[:200], exc)
            return []

    @staticmethod
    def _extract_damage_pages(pdf_path: Path) -> str:
        """
        Intelligently extract only the damage-list pages from the PDF.

        Strategy:
        1. Scan every page for damage-list keywords (LISTA DANNI, OLD DAMAGES, scratch, dent…)
        2. Return only those pages (usually the last 1–3 pages of a rental contract)
        3. Fall back to the last 3 pages if no keyword pages found
        4. Fall back to the full document if still empty
        """
        # Keywords that indicate the DAMAGE TABLE page specifically.
        # Use precise multi-word phrases to avoid matching T&C pages that
        # happen to mention "scratch" or "graffio" in legal boilerplate.
        _DAMAGE_KEYWORDS = {
            "lista danni presenti", "old damages list",
            "danni presenti", "damage glossary",
            "pre-existing damage", "vehicle condition report",
            "check out del", "km uscita",        # Noleggiare table header
        }

        all_pages: list[tuple[int, str]] = []
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for i, page in enumerate(pdf.pages):
                    t = page.extract_text() or ""
                    all_pages.append((i, t))
        except Exception as exc:
            logger.error("PDF extraction failed for {}: {}", pdf_path.name, exc)
            return ""

        if not all_pages:
            return ""

        # Find pages with damage keywords
        damage_pages = [
            (i, t) for i, t in all_pages
            if any(kw in t.lower() for kw in _DAMAGE_KEYWORDS)
        ]

        if damage_pages:
            logger.info("CompanyPDFParser: damage keywords found on page(s) {}",
                        [i + 1 for i, _ in damage_pages])
            # Include those pages + the immediately following page (table may span pages)
            indices = set()
            for i, _ in damage_pages:
                indices.add(i)
                if i + 1 < len(all_pages):
                    indices.add(i + 1)
            selected = [t for i, t in all_pages if i in sorted(indices)]
        else:
            # No keywords found — take the last 3 pages (damage tables are always at the end)
            logger.info("CompanyPDFParser: no damage keywords — using last 3 pages")
            selected = [t for _, t in all_pages[-3:]]

        return "\n\n".join(selected)
