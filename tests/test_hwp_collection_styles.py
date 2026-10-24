import zipfile
from app.hwp_collection_styles import resolved_body_style_signatures


def fixture(path, key=0, widow="1", border="NONE"):
    header = f'''<head><fontface lang="HANGUL"><font id="{key}" face="Synthetic Font"/></fontface>
    <charPr id="{key}" height="1150"><fontRef hangul="{key}"/></charPr>
    <borderFill id="{key}"><leftBorder type="{border}"/></borderFill><tabPr id="{key}"/>
    <paraPr id="{key}" tabPrIDRef="{key}"><breakSetting widowOrphan="{widow}"/>
    <border borderFillIDRef="{key}"/></paraPr></head>'''
    section = f'''<sec xmlns:p="http://www.hancom.co.kr/hwpml/2011/paragraph">
    <p:p paraPrIDRef="{key}"><p:run charPrIDRef="{key}"><p:t>Synthetic</p:t></p:run></p:p></sec>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", section)


def test_renumbered_ids_do_not_change_resolved_style(tmp_path):
    a, b = tmp_path / "a.hwpx", tmp_path / "b.hwpx"
    fixture(a, 0); fixture(b, 71)
    assert resolved_body_style_signatures(a) == resolved_body_style_signatures(b)


def test_same_reference_id_cannot_hide_a_border_semantic_change(tmp_path):
    a, b = tmp_path / "a.hwpx", tmp_path / "b.hwpx"
    fixture(a); fixture(b, border="SOLID")
    assert resolved_body_style_signatures(a) != resolved_body_style_signatures(b)


def test_imported_widow_flag_loss_is_detected(tmp_path):
    a, b = tmp_path / "a.hwpx", tmp_path / "b.hwpx"
    fixture(a); fixture(b, widow="0")
    assert resolved_body_style_signatures(a) != resolved_body_style_signatures(b)
