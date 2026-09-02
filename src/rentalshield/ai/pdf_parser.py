"""
Rental company PDF parser.
Extracts text from the company's condition report, then uses the
configured AI provider (Gemini or Claude) to pull out the damage list.
"""

from __future__ import annotations

import json
from pathlib import Path

import pdfplumber
from loguru import logger

from rentalshield.ai.base import BaseAnalyzer


_MAX_TEXT_CHARS = 6_000

_PARSE_PROMPT_TEMPLATE = """\
You are reading a car rental pre-inspection / condition report document.

Extract EVERY damage or pre-existing condition mentioned.

For each item output a JSON object:
{{
  "type":     "SCRATCH | DENT | CHIP | CRACK | SCUFF | RUST | MISSING | OTHER",
  "location": "car part or zone as written in the document",
  "severity": "MINOR | MODERATE | SEVERE | UNKNOWN",
  "notes":    "verbatim quote or short paraphrase from the document"
}}

Return a JSON array. If the document lists no damages (clean car), return [].
Reply with ONLY the raw JSON array — no markdown, no explanation.

--- DOCUMENT TEXT ---
{text}
--- END ---"""


class RentalPDFParser:
    """
    Parses rental company condition-report PDFs.
    Uses whichever AI provider (Gemini / Claude) is passed in.
    """

    def __init__(self, analyzer: BaseAnalyzer):
        self._analyzer = analyzer

    def extract_text(self, pdf_path: Path) -> str:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        parts = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)

        full_text = "\n".join(parts)
        if not full_text.strip():
            raise ValueError(
                f"No text extracted from '{pdf_path.name}'. "
                "The PDF may be image-only (scanned)."
            )

        logger.info("Extracted {} chars from {} ({} pages)",
                    len(full_text), pdf_path.name, len(parts))
        return full_text

    def parse_damages(self, pdf_path: Path) -> list[dict]:
        text   = self.extract_text(pdf_path)
        prompt = _PARSE_PROMPT_TEMPLATE.format(text=text[:_MAX_TEXT_CHARS])

        logger.info("Asking AI to parse company damage list …")
        raw = self._analyzer.generate_text(prompt)

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        damages = json.loads(raw)
        logger.info("Company report lists {} damage(s)", len(damages))
        return damages
