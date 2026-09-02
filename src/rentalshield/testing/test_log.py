"""
RentalShield — Test log.

Tracks every car scan against its company PDF so you can measure
how well the AI is doing across multiple real-world tests.

Each entry records:
  • Car details (plate, model, company)
  • Company's damage count
  • Our damage count
  • How many matched, how many we missed, how many NEW we found
  • Recall: % of company damages we caught
  • Extra: undocumented damages we found (the killer feature)

The log is a JSON file at data/test_log.json — human-readable,
appendable, and safe to edit manually.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

_LOG_PATH = Path(__file__).parent.parent.parent.parent / "data" / "test_log.json"


def _load() -> list[dict]:
    if _LOG_PATH.exists():
        with open(_LOG_PATH) as f:
            return json.load(f)
    return []


def _save(entries: list[dict]) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def log_comparison(
    audit_session_id: str,
    car_plate:        str | None,
    car_model:        str | None,
    rental_company:   str | None,
    company_pdf:      str | None,
    company_count:    int,
    our_count:        int,
    matched:          int,
    new_undocumented: int,
    notes:            str = "",
) -> dict:
    """
    Append one test result to the log and return the entry dict.
    Called automatically by run_comparison().
    """
    missed = max(0, company_count - matched)
    recall = round(matched / company_count * 100, 1) if company_count else 0.0

    entry = {
        "date":             datetime.now().strftime("%Y-%m-%d"),
        "audit_session":    audit_session_id,
        "plate":            car_plate    or "—",
        "car":              car_model    or "—",
        "company":          rental_company or "—",
        "company_pdf":      Path(company_pdf).name if company_pdf else "—",
        "company_count":    company_count,
        "our_count":        our_count,
        "matched":          matched,
        "missed":           missed,
        "new_undocumented": new_undocumented,
        "recall_pct":       recall,
        "notes":            notes,
    }

    entries = _load()
    # Update existing entry for the same session, or append
    for i, e in enumerate(entries):
        if e.get("audit_session") == audit_session_id:
            entries[i] = entry
            _save(entries)
            return entry
    entries.append(entry)
    _save(entries)
    return entry


def all_entries() -> list[dict]:
    return _load()


def summary_text() -> str:
    """Return a formatted summary table for terminal output."""
    entries = _load()
    if not entries:
        return "No test entries yet. Run a comparison first."

    lines = []
    lines.append(f"{'#':<3} {'Date':<12} {'Plate':<12} {'Car':<16} {'Company':<10} "
                 f"{'Co.':<4} {'Ours':<5} {'Match':<6} {'Miss':<5} {'NEW':<5} {'Recall':<8} Notes")
    lines.append("─" * 100)

    totals = dict(company=0, ours=0, matched=0, missed=0, new=0)

    for i, e in enumerate(entries, 1):
        lines.append(
            f"{i:<3} {e['date']:<12} {e['plate']:<12} {e['car'][:15]:<16} "
            f"{e['company'][:9]:<10} {e['company_count']:<4} {e['our_count']:<5} "
            f"{e['matched']:<6} {e['missed']:<5} {e['new_undocumented']:<5} "
            f"{e['recall_pct']:>5.1f}%   {e.get('notes', '')}"
        )
        totals["company"] += e["company_count"]
        totals["ours"]    += e["our_count"]
        totals["matched"] += e["matched"]
        totals["missed"]  += e["missed"]
        totals["new"]     += e["new_undocumented"]

    lines.append("─" * 100)
    avg_recall = round(totals["matched"] / totals["company"] * 100, 1) if totals["company"] else 0
    lines.append(
        f"{'TOT':<3} {'':<12} {'':<12} {'':<16} {'':<10} "
        f"{totals['company']:<4} {totals['ours']:<5} {totals['matched']:<6} "
        f"{totals['missed']:<5} {totals['new']:<5} {avg_recall:>5.1f}%"
    )
    lines.append(f"\n{len(entries)} car(s) tested  |  "
                 f"avg recall {avg_recall}%  |  "
                 f"{totals['new']} undocumented damage(s) found across all cars")
    return "\n".join(lines)
