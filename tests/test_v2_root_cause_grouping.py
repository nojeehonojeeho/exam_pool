from app.v2_root_cause_grouping import group_findings, summarize


def test_groups_duplicate_metadata_without_deleting_raw_findings():
    findings = [
        {"item_id": "HE-P-023", "path": "solution_blocks/2/segments/0", "code": "DIALECT_REQUIRED"},
        {"item_id": "HE-P-023", "path": "solution_blocks/2/segments/0", "code": "FORMULA_MARKUP_IN_TEXT"},
        {"item_id": "HE-P-023", "path": "solution_blocks/3/segments/0", "code": "DIALECT_REQUIRED"},
    ]
    groups = group_findings(findings)
    assert sum(g["raw_finding_count"] for g in groups) == 3
    assert len(groups) == 2
    assert all(g["candidate_only"] and not g["resolved"] for g in groups)


def test_distinct_formula_categories_do_not_merge():
    findings = [
        {"item_id": "HE-P-001", "path": "problem_blocks/1/segments/0", "code": "DIALECT_REQUIRED"},
        {"item_id": "HE-P-001", "path": "problem_blocks/1/segments/0", "code": "FIGURE_ASSET_MISSING"},
    ]
    groups = group_findings(findings)
    assert len(groups) == 2
    assert {g["category"] for g in groups} == {"formula-authoring-contract", "figure-evidence"}


def test_summary_preserves_raw_count_and_never_passes():
    summary = summarize({"status": "FAIL", "findings": [{"code": "X"}, {"code": "Y"}]})
    assert summary["raw_finding_count"] == 2
    assert summary["release_blocker_count"] == 2
    assert summary["status"] == "DIAGNOSTIC_ONLY"


def test_root_cause_id_uses_deterministic_source_key():
    finding = {
        "document_role": "solution",
        "item_id": "HE-P-007",
        "stage": "source-evidence",
        "evidence_key": "formula-occurrence:HE-P-007-F-02",
        "source_hash": "sha256:abc",
        "path": "solution_blocks/2/segments/0",
        "code": "FORMULA_OCCURRENCE_UNVERIFIED",
    }
    first = group_findings([finding])[0]
    second = group_findings([dict(reversed(list(finding.items())))])[0]
    assert first["root_cause_id"] == "solution|HE-P-007|source-evidence|formula-occurrence:HE-P-007-F-02|sha256:abc"
    assert first["root_cause_id"] == second["root_cause_id"]
    assert first["source_hash"] == "sha256:abc"
