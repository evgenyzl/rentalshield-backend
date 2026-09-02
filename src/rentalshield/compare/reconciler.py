"""
Damage reconciler.
Compares YOUR video audit against the rental company's damage list.
Uses whichever AI provider is configured (Gemini or Claude).

Two-direction comparison:
  forward  — for each user-scan damage: MATCHED / NEW / UNCERTAIN
  reverse  — for each company-listed damage: COVERED / RISK
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from rentalshield.ai.base import BaseAnalyzer
from rentalshield.models import (
    Damage, ComparisonItem, ComparisonStatus, DamageType,
)


def _build_my_summary(damages: list[Damage]) -> str:
    if not damages:
        return "(none)"
    return "\n".join(
        f"[{i}] [{d.type.value}] {d.location}: {d.description}"
        for i, d in enumerate(damages)
    )


def _build_company_summary(company_damages: list[dict]) -> str:
    if not company_damages:
        return "(none)"
    return "\n".join(
        f"- [{d.get('type','?')}] {d.get('location','?')}: {d.get('notes','')}"
        for d in company_damages
    )


_COMPARE_PROMPT_TEMPLATE = """\
You are a car rental damage protection analyst. Your job is to protect the customer.

COMPANY's pre-existing damage list (from their inspection PDF — may be in Italian or other language):
{company_summary}

MY video audit findings (damages I personally filmed before driving):
{my_summary}

Matching rules:
  • Same general car region (front/rear/left/right) + same damage type → MATCHED, even if wording differs
  • "paraurti" = bumper, "anteriore" = front, "posteriore" = rear, "destro" = right, "sinistro" = left,
    "graffio" = scratch, "ammaccatura" = dent, "scheggiatura" = chip, "cerchione" = wheel rim,
    "porta" = door, "cofano" = hood, "parafango" = fender, "specchietto" = mirror
  • Severity does NOT need to match — a "lieve graffio" matches a "SCRATCH" in the same area
  • When in doubt whether locations match, prefer MATCHED (protects the customer)

For EACH item in MY list (referenced by index [0], [1], ...):
  • "MATCHED"   — the company already documented a similar damage in the same area
  • "NEW"       — this damage was NOT listed by the company (customer needs extra protection!)
  • "UNCERTAIN" — genuinely impossible to tell from the descriptions

Return a JSON array with one entry per MY item, in index order:
{{
  "my_index":       0,
  "my_location":    "as in my list",
  "my_type":        "type value",
  "my_description": "description",
  "status":         "MATCHED | NEW | UNCERTAIN",
  "reason":         "one sentence explaining the verdict"
}}

Reply with ONLY the raw JSON array — no markdown, no explanation."""


class DamageReconciler:
    """Compares two damage lists using the configured AI provider."""

    def __init__(self, analyzer: BaseAnalyzer):
        self._analyzer = analyzer

    def compare(
        self,
        my_damages:      list[Damage],
        company_damages: list[dict[str, Any]],
    ) -> list[ComparisonItem]:
        if not my_damages:
            logger.info("No damages to compare.")
            return []

        prompt = _COMPARE_PROMPT_TEMPLATE.format(
            company_summary=_build_company_summary(company_damages),
            my_summary=_build_my_summary(my_damages),
        )

        logger.info("Reconciling {} damage(s) …", len(my_damages))
        raw = self._analyzer.generate_text(prompt)

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        raw_items: list[dict] = json.loads(raw)

        results = []
        for item in raw_items:
            idx = item.get("my_index", 0)
            img = my_damages[idx].img_path if idx < len(my_damages) else None
            results.append(ComparisonItem(
                my_index       = idx,
                my_location    = item.get("my_location", "—"),
                my_type        = DamageType(item.get("my_type", "OTHER")),
                my_description = item.get("my_description", "—"),
                status         = ComparisonStatus(item.get("status", "UNCERTAIN")),
                reason         = item.get("reason", ""),
                img_path       = img,
            ))

        logger.info(
            "Done: {} matched | {} NEW | {} uncertain",
            sum(1 for r in results if r.status == ComparisonStatus.MATCHED),
            sum(1 for r in results if r.status == ComparisonStatus.NEW),
            sum(1 for r in results if r.status == ComparisonStatus.UNCERTAIN),
        )
        return results

    def find_company_risks(
        self,
        my_damages:      list[Damage],
        company_damages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Reverse comparison: for each company-listed damage, decide whether
        the user's scan found a matching item.

        Returns a list of company_damage dicts augmented with:
          "covered": True | False   — True = user's scan found it (protected)
          "reason":  str            — one-sentence explanation
        """
        if not company_damages:
            return []

        # Build a numbered list of company items
        company_indexed = "\n".join(
            f"[{i}] [{d.get('type','?')}] {d.get('location','?')}: {d.get('notes','')}"
            for i, d in enumerate(company_damages)
        )

        prompt = f"""\
You are a car rental damage protection analyst.

COMPANY's pre-existing damage list (may be in Italian or other language, numbered):
{company_indexed}

USER's video scan findings:
{_build_my_summary(my_damages) or "(none)"}

Translation reference: paraurti=bumper, anteriore=front, posteriore=rear,
destro=right, sinistro=left, graffio=scratch, ammaccatura=dent,
scheggiatura=chip, porta=door, cofano=hood, parafango=fender, cerchione=wheel rim.

For EACH company item [0], [1], ... decide whether the user's scan filmed a
similar damage in the same general car region (same side + same part):
  "covered" : true  — user's scan has a matching damage (user is protected)
  "covered" : false — user's scan has NO match (company could charge for this!)

Be generous with matching: same car zone + same damage type = covered,
even if exact wording differs. Severity difference alone is NOT a mismatch.

Return a JSON array — one entry per company item, in index order:
{{
  "company_index": 0,
  "location":      "company's location text",
  "covered":       true,
  "reason":        "one sentence explaining the verdict"
}}

Reply with ONLY the raw JSON array — no markdown, no explanation."""

        logger.info("Reverse reconcile: {} company item(s) vs {} scan item(s)",
                    len(company_damages), len(my_damages))
        raw = self._analyzer.generate_text(prompt)

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            verdicts: list[dict] = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Reverse reconcile JSON parse failed — {!r} ({})", raw[:200], exc)
            # Fall back: mark all as uncovered (safest assumption)
            verdicts = [
                {"company_index": i, "location": d.get("location","?"),
                 "covered": False, "reason": "parse error — assume not covered"}
                for i, d in enumerate(company_damages)
            ]

        # Merge verdict back into original company_damage dicts
        results: list[dict] = []
        for v in verdicts:
            idx = v.get("company_index", 0)
            base = company_damages[idx].copy() if idx < len(company_damages) else {}
            base["covered"] = v.get("covered", False)
            base["reason"]  = v.get("reason", "")
            results.append(base)

        covered = sum(1 for r in results if r.get("covered"))
        risk    = len(results) - covered
        logger.info("Reverse done: {} company items covered | {} RISK (user scan missed)",
                    covered, risk)
        return results
