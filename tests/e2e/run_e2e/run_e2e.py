#!/usr/bin/env python3
"""Forwarding CLI test runner wrapper (`tests/e2e/run_e2e/run_e2e.py`).

Delegates directly to `tests/e2e/run_e2e.py:main()` so both:
  - `python3 tests/e2e/run_e2e.py --tier all`
  - `python3 tests/e2e/run_e2e/run_e2e.py --tier all`
execute the full 4-tier E2E test suite and exit with code 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.e2e.run_e2e import build_suite, main  # noqa: E402,F401


if __name__ == "__main__":
    sys.exit(main())
