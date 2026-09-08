"""Meaning-preserving content invariants for HWP/HWPX release gating."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


def canonical_text(value: Any) -> str:
    """Normalize only transport whitespace; never rewrite symbols or numbers."""

    text = unicodedata.normalize("NFC", "" if value is None else str(value))
    return " ".join(text.split())


def content_fingerprint(value: Any) -> str:
    """Stable SHA-256 fingerprint for a JSON-like content snapshot."""

    if isinstance(value, Mapping):
        normalized = {str(k): value[k] for k in sorted(value, key=str)}
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        normalized = list(value)
    else:
        normalized = canonical_text(value)
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_content(expected: Any, actual: Any, *, label: str = "content") -> dict[str, Any]:
    """Compare two snapshots and report a blocking finding on any difference."""

    expected_hash = content_fingerprint(expected)
    actual_hash = content_fingerprint(actual)
    findings: list[dict[str, Any]] = []
    if expected_hash != actual_hash:
        findings.append({
            "code": "CONTENT_INVARIANT_MISMATCH",
            "label": label,
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
            "blocking": True,
        })
    return {
        "status": "PASS" if not findings else "FAIL",
        "expected_sha256": expected_hash,
        "actual_sha256": actual_hash,
        "findings": findings,
    }


__all__ = ["canonical_text", "compare_content", "content_fingerprint"]
