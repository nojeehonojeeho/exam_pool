import pytest

from app.hwp_equation_compiler import EquationCompileError, compile_equation, validate_hancom_script


def compile_tex(value):
    return compile_equation(value, dialect="latex")


@pytest.mark.parametrize("source,expected", [
    (r"x^2+3x+1", "x^{2} + 3 x + 1"),
    (r"a_n+a_{n+1}", "a_{n} + a_{n + 1}"),
    (r"x^12", "x^{1} 2"),
    (r"x^{12}", "x^{12}"),
    (r"a_{n_{k+1}}^2", "a_{n_{k + 1}}^{2}"),
    (r"\frac{x+1}{x-1}", "{{x + 1} over {x - 1}}"),
    (r"\frac12", "{{1} over {2}}"),
    (r"\sqrt[3]{x^{2}+1}", "root {3} of {x^{2} + 1}"),
    (r"\{a,b\}", "lbrace a , b rbrace"),
    (r"\vec{AB}", "vec {A B}"),
    (r"\sqrt{x}^{2}", "{sqrt {x}}^{2}"),
    (r"\sum_{k=1}^{n}k^2", "sum_{k = 1}^{n} k^{2}"),
    (r"\lim_{x\to 0^{+}}\frac{f(x)}{x}", "lim_{x → 0^{+}} {{f ( x )} over {x}}"),
    (r"\int_{-1}^{2}x^2\,dx", "int_{- 1}^{2} x^{2} ` d x"),
    (r"\begin{cases}x^2&x\leq 0\\x+1&x>0\end{cases}", "cases {x^{2} & ~~ x ≤ 0 # x + 1 & ~~ x > 0}"),
    (r"\begin{pmatrix}a&b\\c&d\end{pmatrix}", "pmatrix {a & ~~ b # c & ~~ d}"),
    (r"\left.x\right|_{0}^{1}", "left . x right |_{0}^{1}"),
    (r"\boxed{4}", "box {4}"),
    (r"0\square\square\square\square", "0 □ □ □ □"),
    (r"\left|\frac{x}{2}\right|", "left | {{x} over {2}} right |"),
])
def test_preserves_atom_boundaries(source, expected):
    result = compile_tex(source)
    assert result.script == expected
    assert result.tree is not None
    assert result.tree.end == len(source)
    assert not result.to_dict()["source_pdf_verified"]
    assert validate_hancom_script(result.script) == expected


@pytest.mark.parametrize("source,code", [
    (r"\notImplemented{x}", "UNSUPPORTED_COMMAND"),
    (r"x^{2", "UNCLOSED_GROUP"),
    (r"x_", "MISSING_ARGUMENT"),
    (r"x^{}", "EMPTY_SCRIPT"),
    (r"x^2^3", "DUPLICATE_SCRIPT"),
    (r"\begin{cases}x&x>0\\0\end{cases}", "MATRIX_SHAPE"),
    (r"\begin{unknown}x\end{unknown}", "UNSUPPORTED_ENVIRONMENT"),
    (r"x&y", "UNCONSUMED_INPUT"),
    (r"\left(x", "UNPAIRED_DELIMITER"),
    (r"\mathcal{A}", "UNSUPPORTED_COMMAND"),
    (r"\sum N", "OPERATOR_BOUNDS"),
    (r"\sum_{n=1}a_n", "OPERATOR_BOUNDS"),
    (r"\lim_{0}f(x)", "OPERATOR_BOUNDS"),
    (r"\int_{0}f(x)dx", "OPERATOR_BOUNDS"),
    (r"\frac{}{2}", "EMPTY_ARGUMENT"),
    (r"\sqrt{}", "EMPTY_ARGUMENT"),
    (r"{}", "EMPTY_EQUATION"),
    ("", "EMPTY_EQUATION"),
])
def test_never_turns_failed_formula_into_text(source, code):
    with pytest.raises(EquationCompileError) as exc:
        compile_tex(source)
    assert exc.value.code == code


def test_nested_fraction_tree_and_distinct_visible_braces():
    result = compile_tex(r"\frac{1}{1+\frac{1}{x}}")
    assert result.script == "{{1} over {1 + {{1} over {x}}}}"
    assert compile_tex(r"{a,b}").script != compile_tex(r"\{a,b\}").script


@pytest.mark.parametrize("value", [r"x^2+1", r"a_n+1", r"\frac{1}{2}", "x_{}\\foo", "{x"])
def test_native_input_is_not_guessed_or_repaired(value):
    with pytest.raises(EquationCompileError):
        compile_equation(value, dialect="hancom")


def test_native_validation_does_not_fabricate_mathir():
    result = compile_equation("x^{2}+1", dialect="hancom")
    assert result.tree is None
    assert not result.to_dict()["source_pdf_verified"]
    with pytest.raises(EquationCompileError, match="DIALECT_REQUIRED"):
        compile_equation("x", dialect="auto")


def test_source_operator_exceptions_are_local_and_explicit():
    assert compile_equation(r"\sum_{n\geq 1}a_n", dialect="latex", operator_policies={0: "lower_only"}).script == "sum_{n ≥ 1} a_{n}"
    assert compile_equation(r"\sum", dialect="latex", operator_policies={0: "symbol_only"}).script == "sum"
    with pytest.raises(EquationCompileError, match="UNUSED_OPERATOR_POLICY"):
        compile_equation("x", dialect="latex", operator_policies={0: "symbol_only"})
