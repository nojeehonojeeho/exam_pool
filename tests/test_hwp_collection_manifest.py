import hashlib
import zipfile
import pytest
from app.hwp_collection_manifest import (
    CollectionGateError, assert_exact_pair, assert_partition,
    assert_bound_file, release_decision,
    classify_korean_render_fonts,
    audit_native_references,
    assert_declared_symbol_upgrade,
)


def test_pair_requires_order_not_just_counts():
    with pytest.raises(CollectionGateError):
        assert_exact_pair(["A", "B"], ["B", "A"])


def test_pair_rejects_duplicate():
    with pytest.raises(CollectionGateError):
        assert_exact_pair(["A", "A"], ["A", "A"])


def test_pair_accepts_matching_unique_ids():
    assert_exact_pair(["A", "B"], ["A", "B"])


def test_shared_preamble_retained():
    assert_partition(8, [(2, 5), (6, 8)], [0, 1, 5])


@pytest.mark.parametrize("regions,context", [
    ([(2, 5), (6, 8)], [0, 1]),
    ([(2, 6), (5, 8)], [0, 1]),
    ([(2, 5), (6, 8)], [0, 1, 5, 5]),
    ([(2, 5), (6, 9)], [0, 1, 5]),
    ([(2, 2), (6, 8)], [0, 1, 5]),
])
def test_partition_rejects_loss_overlap_or_out_of_bounds(regions, context):
    with pytest.raises(CollectionGateError):
        assert_partition(8, regions, context)


def test_binding_detects_mutation(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_bytes(b"before")
    digest = hashlib.sha256(b"before").hexdigest()
    assert_bound_file(path, digest)
    path.write_bytes(b"after")
    with pytest.raises(CollectionGateError):
        assert_bound_file(path, digest)


def test_static_success_is_not_full_release():
    result = release_decision({"style": True, "com": True}, {})
    assert result["FINAL"] is False
    assert "source" in result["unresolved_gates"]
    assert "all_pages" in result["unresolved_gates"]


def test_release_requires_every_hash_bound_gate(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_bytes(b"evidence")
    gates = dict.fromkeys(["source", "math", "equations", "figures", "style", "com", "all_pages"], True)
    evidence = {k: {"path": str(path), "sha256": hashlib.sha256(b"evidence").hexdigest()} for k in gates}
    assert release_decision(gates, evidence)["FINAL"] is True
    path.write_bytes(b"stale")
    assert release_decision(gates, evidence)["FINAL"] is False


def test_math_korean_font_exception_is_bound_to_equation():
    result = classify_korean_render_fonts([{"text": "또는", "font": "Haansoft Batang"}], ["x=1 또는 x=2"])
    assert result["body_font_substitution_count"] == 0
    assert result["native_math_text_font_exceptions"][0]["native_equation_occurrences"] == [0]


def test_pdf_can_omit_spaces_inside_korean_math_text():
    result = classify_korean_render_fonts([{"text": "는자연수", "font": "Haansoft Batang"}], ["k는 자연수"])
    assert result["native_math_text_font_exceptions"][0]["native_equation_occurrences"] == [0]


@pytest.mark.parametrize("text,font", [("본문", "Haansoft Batang"), ("또는", "Arial")])
def test_font_substitution_is_not_silently_accepted(text, font):
    with pytest.raises(CollectionGateError, match="KOPUB_FONT_NOT_ACTIVE"):
        classify_korean_render_fonts([{"text": text, "font": font}], ["x=1 또는 x=2"])


def native_fixture(path, body_ref="0"):
    header = '<head><charPr id="0"/><paraPr id="0"><heading type="NONE"/></paraPr><style id="0"/><numbering><paraHead charPrIDRef="4294967295"/></numbering></head>'
    section = f'<sec><p paraPrIDRef="0" styleIDRef="0"><run charPrIDRef="{body_ref}"><t>synthetic</t></run></p></sec>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", section)
        archive.writestr("Contents/content.hpf", "<package/>")


def test_unused_numbering_template_is_not_body_reference(tmp_path):
    path = tmp_path / "synthetic.hwpx"
    native_fixture(path)
    result = audit_native_references(path)
    assert result["unused_numbering_auto_char_records"] == 1


def test_invalid_body_font_reference_still_fails(tmp_path):
    path = tmp_path / "synthetic.hwpx"
    native_fixture(path, "4294967295")
    with pytest.raises(CollectionGateError, match="UNBOUND_charPrIDRef"):
        audit_native_references(path)


def test_non_kopub_rubric_is_not_a_native_math_exception():
    with pytest.raises(CollectionGateError, match="KOPUB_FONT_NOT_ACTIVE"):
        classify_korean_render_fonts([{"text": "채점 기준", "font": "Gulim"}], ["alpha"])


def test_declared_symbol_upgrade_preserves_other_content():
    before = [[["text", "상수 α 계산"]], [["text", "unchanged"]]]
    after = [[["text", "상수 "], ["equation", "alpha"], ["text", " 계산"]], before[1]]
    assert assert_declared_symbol_upgrade(before, after, 0, "α", "alpha")["other_content_unchanged"]


def test_symbol_upgrade_cannot_hide_another_change():
    before = [[["text", "상수 α 계산"]], [["text", "unchanged"]]]
    after = [[["text", "상수 "], ["equation", "alpha"], ["text", " 계산"]], [["text", "changed"]]]
    with pytest.raises(CollectionGateError, match="UNDECLARED_SYMBOL_UPGRADE_CHANGE"):
        assert_declared_symbol_upgrade(before, after, 0, "α", "alpha")
