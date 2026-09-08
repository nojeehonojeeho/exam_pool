"""CLI wrapper for the auditable v2 execution report."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.v2_execution_report import main


if __name__ == "__main__":
    raise SystemExit(main())

