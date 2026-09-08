from tools.highend_writer_protected_text_patch import patch_source
import pytest

SOURCE='''from app.integrations.hwp_security import create_secure_hwp
def _insert_segments(hwp,segment,context):
    if True:
        if True:
            if True:
                hwp.insert_text(str(segment.get("text", "")))
def _insert_text_block(hwp,block,context):
    role = str(block.get("role", "body"))
    if True:
        hwp.insert_text(str(block.get("text", "")))
'''

def test_adapter_only_updates_known_insertion_boundaries():
    result=patch_source(SOURCE)
    assert result.count('insert_protected_text(')==2
    assert patch_source(result)==result

def test_unknown_writer_is_not_treated_as_success():
    with pytest.raises(ValueError):patch_source('def unrelated(): pass\n')
