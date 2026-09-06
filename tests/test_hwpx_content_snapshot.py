import xml.etree.ElementTree as ET
import pytest
from app.hwpx_content_snapshot import snapshot_node


def node(value):
    return ET.fromstring(value)


def test_run_splits_and_note_autonumber_do_not_change_content():
    source = node('<subList><p><run><t>Heading</t></run></p><p><run><t>Complete sentence.</t></run></p></subList>')
    note = node('<endNote><subList><p><run><ctrl><autoNum num="1"/></ctrl><t> </t></run><run><t>Heading</t></run></p><p><run><t>Complete </t></run><run><t>sentence.</t></run></p></subList></endNote>')
    assert snapshot_node(source) == snapshot_node(note)


def test_equation_to_plaintext_and_lost_paragraph_are_detected():
    source = node('<subList><p><run><equation><script>x^{2}</script></equation></run></p><p><run><t>Conclusion.</t></run></p></subList>')
    changed = node('<subList><p><run><t>x^{2}</t></run></p><p><run><t>Conclusion.</t></run></p></subList>')
    assert snapshot_node(source) != snapshot_node(changed)
    assert snapshot_node(source) != snapshot_node(node('<subList><p><run><equation><script>x^{2}</script></equation></run></p></subList>'))


def test_table_cell_order_and_hard_break_remain_significant():
    def table(a, b):
        return node(f'<p><run><tbl><tr><tc><subList><p><run><t>{a}</t></run></p></subList></tc><tc><subList><p><run><t>{b}</t></run></p></subList></tc></tr></tbl></run></p>')
    assert snapshot_node(table('A', 'B')) != snapshot_node(table('B', 'A'))
    assert snapshot_node(node('<p><run><t>A<lineBreak/>B</t></run></p>')) != snapshot_node(node('<p><run><t>A B</t></run></p>'))


def test_unresolved_picture_is_not_silently_skipped():
    with pytest.raises(ValueError, match="picture resource"):
        snapshot_node(node('<p><run><pic><img binaryItemIDRef="image1"/></pic></run></p>'))


def test_unimplemented_vector_snapshot_does_not_claim_equal_content():
    with pytest.raises(ValueError, match="unsupported visible"):
        snapshot_node(node('<p><run><ellipse id="1"/></run></p>'))
