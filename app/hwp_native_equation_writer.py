"""Write already-compiled equations once, and read actual COM controls back."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .hwp_equation_compiler import CompiledEquation, validate_hancom_script


def insert_compiled_equation(hwp: Any, compiled: CompiledEquation, *, base_unit: int = 1100) -> None:
    script = validate_hancom_script(compiled.script)
    action, parameters = hwp.HAction, hwp.HParameterSet.HEqEdit
    action.GetDefault("EquationCreate", parameters.HSet)
    parameters.string = script
    parameters.BaseUnit = base_unit
    if not action.Execute("EquationCreate", parameters.HSet):
        raise RuntimeError("EQUATION_CREATE_FAILED: native equation was not inserted")
    action.Run("Cancel")
    position = tuple(hwp.GetPos())
    hwp.SetPos(position[0], position[1], position[2] + 1)


def read_equation_snapshot(hwp: Any) -> dict[str, Any]:
    controls = list(hwp.ctrl_list)
    rows = []
    for ctrl in controls:
        if str(ctrl.CtrlID).strip() != "eqed":
            continue
        properties = ctrl.Properties
        rows.append({"script": str(properties.Item("String") or "").strip(), "baseUnit": int(properties.Item("BaseUnit"))})
    return {"equations": rows, "equation_count": len(rows), "control_counts": dict(Counter(str(ctrl.CtrlID).strip() for ctrl in controls))}


def compare_equation_snapshot(expected: list[str], snapshot: dict[str, Any], *, base_unit: int = 1100) -> list[dict[str, Any]]:
    rows = snapshot["equations"]
    findings = []
    if len(expected) != len(rows):
        findings.append({"code": "COM_FORMULA_COUNT_MISMATCH", "expected": len(expected), "actual": len(rows)})
    for index, (source, actual) in enumerate(zip(expected, rows), 1):
        if source.strip() != actual["script"]:
            findings.append({"code": "COM_FORMULA_SCRIPT_MISMATCH", "index": index, "expected": source, "actual": actual["script"]})
        if actual["baseUnit"] != base_unit:
            findings.append({"code": "COM_FORMULA_BASEUNIT_MISMATCH", "index": index, "actual": actual["baseUnit"]})
    return findings
