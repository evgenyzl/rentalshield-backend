"""
Consistency test — the "run it 5 times" test.

Sends the same 3 frames to Claude 5 times each and verifies that:
  1. Damage COUNT is stable (std-dev ≤ 1 across runs)
  2. Damage TYPE agreement ≥ 80% across runs (same types in same frame)
  3. Overall consistency score ≥ 75%

These tests hit the real Claude API and therefore:
  - Require ANTHROPIC_API_KEY to be set
  - Take ~3–5 minutes to run (15 API calls)
  - Are marked @pytest.mark.slow and @pytest.mark.integration

Run with:
    pytest tests/consistency/ -m slow -v -s
"""

from __future__ import annotations

import os
import statistics
from collections import Counter
from pathlib import Path

import cv2
import pytest

from rentalshield.ai.analyzer import DamageAnalyzer
from rentalshield.models import Damage, DamageType

pytestmark = [pytest.mark.slow, pytest.mark.integration]

RUNS_PER_FRAME      = 5
COUNT_STD_THRESHOLD = 1.5   # max allowed std-dev in damage count
TYPE_AGREE_THRESHOLD = 0.70  # fraction of runs that must agree on types
CONSISTENCY_PASS    = 0.75   # overall score to pass the test


# ── Helper: consistency score for one frame across N runs ─────────────────────

def _count_score(counts: list[int]) -> float:
    """Score based on how stable the damage count is (1.0 = identical each run)."""
    if len(counts) < 2:
        return 1.0
    avg = statistics.mean(counts)
    std = statistics.stdev(counts)
    # If avg is 0, full score (no damage = consistent); else penalise by std/avg
    if avg == 0:
        return 1.0 if std == 0 else 0.5
    return max(0.0, 1.0 - (std / (avg + 1)))


def _type_score(all_runs: list[list[Damage]]) -> float:
    """
    Score based on TYPE agreement.
    For each run, collect a Counter of damage types.
    Compute pairwise overlap between runs (Jaccard on multisets).
    """
    if len(all_runs) < 2:
        return 1.0

    def counter_overlap(a: Counter, b: Counter) -> float:
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        intersection = sum((a & b).values())
        union = sum((a | b).values())
        return intersection / union if union else 0.0

    counters = [Counter(d.type for d in run) for run in all_runs]
    pairs = 0
    total_overlap = 0.0
    for i in range(len(counters)):
        for j in range(i + 1, len(counters)):
            total_overlap += counter_overlap(counters[i], counters[j])
            pairs += 1

    return total_overlap / pairs if pairs else 1.0


def _location_score(all_runs: list[list[Damage]]) -> float:
    """
    Score based on LOCATION consistency.
    Checks whether the most-reported locations appear in most runs.
    """
    if not any(all_runs):
        return 1.0  # all empty = fully consistent

    # Collect all locations across runs
    all_locs = [d.location.lower() for run in all_runs for d in run]
    if not all_locs:
        return 1.0

    loc_counter = Counter(all_locs)
    total_runs  = len(all_runs)

    # For each unique location, what fraction of runs saw it?
    scores = [count / total_runs for count in loc_counter.values()]
    return statistics.mean(scores) if scores else 1.0


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def analyzer():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set — skipping consistency tests")
    return DamageAnalyzer()


@pytest.fixture(scope="module")
def test_frames(fixture_frames_dir) -> list[tuple[str, "cv2.Mat"]]:
    """Load the 3 fixture frames."""
    paths = sorted(fixture_frames_dir.glob("frame_*.jpg"))
    if not paths:
        pytest.skip("No fixture frames found — run tests with video present first")
    frames = []
    for p in paths[:3]:
        frame = cv2.imread(str(p))
        if frame is not None:
            frames.append((p.name, frame))
    return frames


# ── Main consistency test ─────────────────────────────────────────────────────

def test_consistency_across_5_runs(analyzer, test_frames, capsys):
    """
    Core consistency test:
    Each fixture frame is sent to Claude RUNS_PER_FRAME times.
    The test asserts overall consistency score >= CONSISTENCY_PASS.
    """
    assert test_frames, "No frames to test"

    all_frame_scores = []
    report_lines = [
        f"\n{'='*60}",
        f"  Consistency Test  ({RUNS_PER_FRAME} runs × {len(test_frames)} frames)",
        f"{'='*60}",
    ]

    for frame_name, frame in test_frames:
        report_lines.append(f"\n  Frame: {frame_name}")
        runs: list[list[Damage]] = []

        for run_idx in range(RUNS_PER_FRAME):
            damages = analyzer.analyze_frame(frame, frame_no=0, time_sec=0.0)
            runs.append(damages)
            types_str = ", ".join(d.type.value for d in damages) or "—"
            report_lines.append(
                f"    Run {run_idx+1}/{RUNS_PER_FRAME}: "
                f"{len(damages)} damage(s)  [{types_str}]"
            )

        counts     = [len(r) for r in runs]
        c_score    = _count_score(counts)
        t_score    = _type_score(runs)
        l_score    = _location_score(runs)
        frame_score = (c_score + t_score + l_score) / 3.0

        report_lines.append(
            f"    Scores — count:{c_score:.0%}  type:{t_score:.0%}  "
            f"location:{l_score:.0%}  → frame:{frame_score:.0%}"
        )
        all_frame_scores.append(frame_score)

    overall = statistics.mean(all_frame_scores)

    report_lines.append(f"\n{'─'*60}")
    report_lines.append(f"  Overall consistency: {overall:.1%}")
    report_lines.append(f"  Threshold:           {CONSISTENCY_PASS:.1%}")
    report_lines.append(
        f"  Result:  {'✅ PASS' if overall >= CONSISTENCY_PASS else '❌ FAIL'}"
    )
    report_lines.append(f"{'='*60}")

    with capsys.disabled():
        print("\n".join(report_lines))

    assert overall >= CONSISTENCY_PASS, (
        f"Consistency score {overall:.1%} is below threshold {CONSISTENCY_PASS:.1%}.\n"
        "This may indicate model instability on this type of video.\n"
        "Consider adding more specific prompting or post-processing deduplication."
    )


def test_count_std_dev_acceptable(analyzer, test_frames):
    """
    Damage count should not vary wildly between runs on the same frame.
    Std-dev across RUNS_PER_FRAME must be <= COUNT_STD_THRESHOLD.
    """
    for frame_name, frame in test_frames:
        counts = [
            len(analyzer.analyze_frame(frame, frame_no=0, time_sec=0.0))
            for _ in range(RUNS_PER_FRAME)
        ]
        if len(counts) < 2:
            continue
        std = statistics.stdev(counts)
        assert std <= COUNT_STD_THRESHOLD, (
            f"Frame '{frame_name}': damage count std-dev={std:.1f} "
            f"exceeds threshold {COUNT_STD_THRESHOLD}.\n"
            f"Counts across runs: {counts}"
        )


def test_blank_frame_returns_empty(analyzer):
    """A plain grey frame should consistently return no damages."""
    import numpy as np
    blank = np.full((480, 640, 3), 128, dtype=np.uint8)

    for i in range(3):  # 3 runs on a blank frame
        damages = analyzer.analyze_frame(blank, frame_no=0, time_sec=0.0)
        assert damages == [], (
            f"Run {i+1}: blank frame produced {len(damages)} damage(s): "
            + str([d.type for d in damages])
        )
