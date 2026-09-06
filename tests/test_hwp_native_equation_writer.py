from types import SimpleNamespace
import pytest

from app.hwp_equation_compiler import compile_equation
from app.hwp_native_equation_writer import insert_compiled_equation, compare_equation_snapshot, read_equation_snapshot


class FakeHwp:
    def __init__(self, succeeds=True):
        params = SimpleNamespace(HSet=object())
        self.HParameterSet = SimpleNamespace(HEqEdit=params)
        self.calls = []
        self.HAction = SimpleNamespace(GetDefault=lambda *args: None, Execute=lambda *args: succeeds, Run=lambda *args: self.calls.append(args))

    def GetPos(self):
        return (0, 1, 2)

    def SetPos(self, *args):
        self.position = args


def test_compiled_equation_is_not_sent_through_legacy_converter():
    hwp = FakeHwp()
    result = compile_equation(r"\{x^{2}+1\}", dialect="latex")
    insert_compiled_equation(hwp, result)
    assert hwp.HParameterSet.HEqEdit.string == result.script
    assert "lbrace" in result.script
    assert hwp.HParameterSet.HEqEdit.BaseUnit == 1100
    assert hwp.position == (0, 1, 3)


def test_failure_is_exception_not_text_fallback():
    with pytest.raises(RuntimeError, match="EQUATION_CREATE_FAILED"):
        insert_compiled_equation(FakeHwp(False), compile_equation("x", dialect="latex"))


def test_actual_control_readback_compares_order_not_just_count():
    props = [{"String": "y", "BaseUnit": 1100}, {"String": "x", "BaseUnit": 900}]
    hwp = SimpleNamespace(ctrl_list=[SimpleNamespace(CtrlID="eqed", Properties=SimpleNamespace(Item=row.__getitem__)) for row in props])
    snapshot = read_equation_snapshot(hwp)
    assert snapshot["equation_count"] == 2
    findings = compare_equation_snapshot(["x", "y"], snapshot)
    assert [row["code"] for row in findings].count("COM_FORMULA_SCRIPT_MISMATCH") == 2
    assert any(row["code"] == "COM_FORMULA_BASEUNIT_MISMATCH" for row in findings)
