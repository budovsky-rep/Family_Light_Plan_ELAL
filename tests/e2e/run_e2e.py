#!/usr/bin/env python3
"""CLI test runner for the family_vacation_planner 4-tier E2E test suite.

Supports running individual tiers (`--tier 1|2|3|4`) or the full suite (`--tier all`),
and is 100% compatible with standard unittest discovery:
  python3 -m unittest discover -s tests/e2e -p "test_*.py" -v
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
E2E_DIR = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TIER_MAP: dict[str, tuple[str, int]] = {
    "1": ("test_tier1_features.py", 160),
    "2": ("test_tier2_boundaries.py", 160),
    "3": ("test_tier3_pairwise.py", 32),
    "4": ("test_tier4_scenarios.py", 16),
}


def build_suite(tier: str) -> tuple[unittest.TestSuite, int]:
    """Discover and build the unittest TestSuite for the requested tier(s)."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    min_expected = 0
    selected_tiers = ["1", "2", "3", "4"] if tier == "all" else [tier]
    for t in selected_tiers:
        pattern, threshold = TIER_MAP[t]
        min_expected += threshold
        discovered = loader.discover(
            start_dir=str(E2E_DIR),
            pattern=pattern,
            top_level_dir=str(PROJECT_ROOT),
        )
        suite.addTests(discovered)
    return suite, min_expected


def main(argv: list[str] | None = None) -> int:
    """Execute the E2E test suite and return exit code 0 iff all tests pass."""
    parser = argparse.ArgumentParser(
        description="Run family_vacation_planner E2E test tiers."
    )
    parser.add_argument(
        "--tier",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Which E2E tier to execute (1, 2, 3, 4, or all).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=True,
        help="Verbose test output.",
    )
    args = parser.parse_args(argv)

    suite, min_expected = build_suite(args.tier)
    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1)
    result = runner.run(suite)

    skipped_count = len(getattr(result, "skipped", []))
    print(
        f"\n[E2E Summary] tier={args.tier} ran={result.testsRun} "
        f"min_expected={min_expected} failures={len(result.failures)} "
        f"errors={len(result.errors)} skipped={skipped_count}"
    )
    if result.testsRun < min_expected:
        print(
            f"[E2E FAIL] Ran {result.testsRun} tests, below minimum threshold "
            f"{min_expected} for tier={args.tier}.",
            file=sys.stderr,
        )
        return 1
    if not result.wasSuccessful() or skipped_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
