from app.pdf_hwp_scope_reconciliation import expand_step_b_variants, reconcile_scope


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
