from app.pdf_hwp_scope_reconciliation import (
    expand_step_b_variants,
    materialize_candidate_items,
    reconcile_manifests,
    reconcile_scope,
)


def test_step_b_variants_are_expanded_with_stable_ids() -> None:
    rows = expand_step_b_variants(
        [{"chapter": "I", "section": "B", "printed_nums": ["01", "02"], "source_page_physical": 13}]
    )
    assert [row["item_id"] for row in rows] == [
        "HIGH-MATH-DOWN-I-B-01",
        "HIGH-MATH-DOWN-I-B-01-1",
        "HIGH-MATH-DOWN-I-B-02",
        "HIGH-MATH-DOWN-I-B-02-1",
    ]


def test_verified_label_alone_is_not_evidence_closure() -> None:
    result = reconcile_scope(
        [{"item_id": "Q-1"}],
        [{"item_id": "Q-1", "review_status": "VERIFIED"}],
    )
    assert result.legacy_reviewed_scope_count == 1
    assert result.evidence_closed_item_count == 0
    assert result.evidence_open_item_count == 1
    assert result.final_eligible is False


def test_explicit_source_evidence_closes_only_the_same_candidate_id() -> None:
    result = reconcile_scope(
        [{"item_id": "Q-1"}, {"item_id": "Q-2"}],
        [
            {
                "item_id": "Q-1",
                "review_status": "VERIFIED",
                "evidence_status": "CLOSED",
                "source_evidence": {
                    "source_pdf_sha256": "a" * 64,
                    "source_page": 1,
                    "bbox_pt": [1, 2, 3, 4],
                    "source_crop_sha256": "b" * 64,
                    "review_id": "run-1",
                },
            },
            {"item_id": "Q-9", "evidence_status": "CLOSED"},
        ],
    )
    assert result.evidence_closed_ids == ()
    assert result.source_evidence_claim_ids == ("Q-1",)
    assert result.open_ids == ("Q-1", "Q-2")
    assert result.unexpected_reviewed_ids == ("Q-9",)


def test_generator_inputs_are_materialized_before_closure_is_calculated() -> None:
    result = reconcile_scope(
        (item for item in [{"item_id": "Q-1"}]),
        (
            item
            for item in [
                {
                    "item_id": "Q-1",
                    "evidence_status": "CLOSED",
                    "source_evidence": {
                        "source_pdf_sha256": "a" * 64,
                        "source_page": 1,
                        "bbox_pt": [1, 2, 3, 4],
                        "source_crop_sha256": "b" * 64,
                        "review_id": "run-1",
                    },
                }
            ]
        ),
    )
    assert result.evidence_closed_ids == ()
    assert result.source_evidence_claim_ids == ("Q-1",)
    assert result.final_eligible is False


def test_empty_scope_never_releases():
    assert reconcile_scope([], []).final_eligible is False


def test_legacy_count_excludes_pending_and_missing_status():
    result = reconcile_scope(
        [{"item_id": key} for key in ("A", "B", "C")],
        [{"item_id": "A", "review_status": "VERIFIED"},
         {"item_id": "B", "review_status": "NEEDS_REVIEW"},
         {"item_id": "C"}], declared_item_count=4,
    )
    assert result.legacy_reviewed_ids == ("A",)
    assert result.as_dict()["declared_count_matches_candidates"] is False


def test_page_manifest_materialization_counts_step_b_variants() -> None:
    items, details = materialize_candidate_items(
        {
            "item_count": 8,
            "pages": [
                {
                    "chapter": "I",
                    "section": "A",
                    "printed_nums": ["01", "02"],
                    "item_count": 2,
                    "source_page_physical": 11,
                },
                {
                    "chapter": "I",
                    "section": "B",
                    "printed_nums": ["01", "02", "03"],
                    "item_count": 6,
                    "source_page_physical": 13,
                },
            ],
        }
    )
    assert len(items) == 8
    assert details["mode"] == "pages_step_b_variant_expansion"
    assert details["page_declared_item_count"] == 8
    assert details["page_expansion_count"] == 8
    assert details["page_count_mismatches"] == []
    assert items[-1]["item_id"] == "HIGH-MATH-DOWN-I-B-03-1"


def test_page_manifest_count_mismatch_is_preserved_as_diagnostic() -> None:
    _, details = materialize_candidate_items(
        {
            "pages": [
                {
                    "chapter": "I",
                    "section": "B",
                    "printed_nums": ["01", "02", "03"],
                    "item_count": 3,
                    "source_page_physical": 13,
                }
            ]
        }
    )
    assert details["page_expansion_count"] == 6
    assert details["page_count_mismatches"] == [
        {
            "source_page_physical": 13,
            "source_page_printed": None,
            "declared_item_count": 3,
            "expanded_item_count": 6,
        }
    ]


def test_reconcile_manifests_materializes_page_candidates_before_scope_classification() -> None:
    report = reconcile_manifests(
        {
            "item_count": 8,
            "pages": [
                {
                    "chapter": "I",
                    "section": "A",
                    "printed_nums": ["01", "02"],
                    "item_count": 2,
                },
                {
                    "chapter": "I",
                    "section": "B",
                    "printed_nums": ["01", "02", "03"],
                    "item_count": 6,
                },
            ],
        },
        {"review_status": "VERIFIED", "items": [{"item_id": "HIGH-MATH-DOWN-I-A-01"}]},
    )
    assert report["candidate_id_count"] == 8
    assert report["declared_item_count"] == 8
    assert report["candidate_materialization"]["mode"] == "pages_step_b_variant_expansion"
    assert report["scope_assessment"]["classification"] == "PARTIAL_SCOPE"
    assert report["scope_assessment"]["unreviewed_candidate_item_count"] == 7
    assert report["scope_assessment"]["full_book_coverage"] is False
    assert report["scope_assessment"]["full_book_release_eligible"] is False


def test_reviewed_ids_can_be_noncontiguous_but_are_still_partial_scope() -> None:
    result = reconcile_scope(
        [{"item_id": f"Q-{index}"} for index in range(1, 7)],
        [{"item_id": "Q-1"}, {"item_id": "Q-4"}],
    )
    assert result.reviewed_candidate_ids == ("Q-1", "Q-4")
    assert result.unreviewed_candidate_scope_count == 4
    assert result.scope_classification == "PARTIAL_SCOPE"
    assert result.coverage_ratio == 2 / 6


def test_duplicate_ids_never_qualify_as_full_book_coverage() -> None:
    result = reconcile_scope(
        [{"item_id": "Q-1"}, {"item_id": "Q-1"}],
        [{"item_id": "Q-1"}],
    )
    assert result.duplicate_candidate_ids == ("Q-1",)
    assert result.scope_classification == "DUPLICATE_SCOPE_IDS"
