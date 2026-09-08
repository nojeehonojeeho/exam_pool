"""Small, explicit-dialect equation compiler; never strip unknown commands.

This is a syntax compiler, NOT evidence that OCR matches the source PDF.
LaTeX input produces a source-spanned presentation tree. Unsupported syntax
must be reviewed/implemented, never silently downgraded to ordinary text.
Hancom input can be conservatively checked but cannot acquire a LaTeX tree
or a source-verification claim merely by being accepted here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any


COMPILER_VERSION = "hwp-equation-compiler-v1"


class EquationCompileError(ValueError):
    def __init__(self, code: str, message: str, offset: int = 0):
        self.code, self.offset = code, offset
        super().__init__(f"{code} at {offset}: {message}")


@dataclass
class Node:
    kind: str
    value: str = ""
    children: list["Node"] = field(default_factory=list)
    start: int = 0
    end: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value, "span": [self.start, self.end],
                "children": [child.to_dict() for child in self.children]}


@dataclass
class CompiledEquation:
    source: str
    dialect: str
    script: str
    tree: Node | None

    def to_dict(self) -> dict[str, Any]:
        return {"compiler_version": COMPILER_VERSION, "source": self.source,
                "script_language": self.dialect, "script": self.script,
                "source_sha256": hashlib.sha256(self.source.encode()).hexdigest(),
                "script_sha256": hashlib.sha256(self.script.encode()).hexdigest(),
                "mathir": self.tree.to_dict() if self.tree else None,
                "source_pdf_verified": False}


_SYMBOLS = {
    "times": "times", "cdot": "cdot", "div": "div", "pm": "±", "mp": "∓",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "lt": "<", "gt": ">", "to": "→", "rightarrow": "→", "leftarrow": "←",
    "leftrightarrow": "↔", "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
    "infty": "∞", "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂",
    "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇", "cup": "∪", "cap": "∩",
    "emptyset": "∅", "varnothing": "∅", "setminus": "∖", "mid": "|",
    "vert": "|", "Vert": "∥", "parallel": "∥", "perp": "⊥", "angle": "∠",
    "triangle": "△", "square": "□", "sim": "∼", "approx": "≈", "equiv": "≡", "cong": "≅",
    "ldots": "…", "dots": "…", "cdots": "⋯", "vdots": "⋮", "ddots": "⋱",
    "circ": "∘", "forall": "∀", "exists": "∃", "partial": "∂", "nabla": "∇",
    "ell": "ℓ", "prime": "′", "therefore": "∴", "because": "∵", "%": "%", "bigcirc": "○",
}
_GREEK = "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega".split()
_SYMBOLS.update({name: name for name in _GREEK})
_FUNCTIONS = set("sin cos tan cot sec csc cosec arcsin arccos arctan sinh cosh tanh log ln exp max min det gcd".split())
_OPERATORS = {"sum": "sum", "prod": "prod", "int": "int", "iint": "dint", "iiint": "tint", "oint": "oint", "lim": "lim"}
_ACCENTS = {"vec": "vec", "overrightarrow": "vec", "overline": "bar", "bar": "bar", "hat": "hat", "widehat": "hat", "tilde": "tilde", "dot": "dot", "ddot": "ddot", "underline": "under", "boxed": "box"}
_ENVS = {"cases": "cases", "matrix": "matrix", "pmatrix": "pmatrix", "bmatrix": "bmatrix", "vmatrix": "dmatrix", "aligned": "eqalign", "gathered": "pile"}
_DELIMS = {"{": "lbrace", "}": "rbrace", "lbrace": "lbrace", "rbrace": "rbrace", "langle": "langle", "rangle": "rangle", "vert": "|", "Vert": "∥", "|": "∥"}


class _LatexParser:
    def __init__(self, source: str):
        self.source, self.i = source, 0

    def fail(self, code: str, message: str, offset: int | None = None):
        raise EquationCompileError(code, message, self.i if offset is None else offset)

    def space(self):
        while self.i < len(self.source) and self.source[self.i].isspace():
            self.i += 1

    def starts_command(self, command: str) -> bool:
        return bool(re.match(r"\\" + re.escape(command) + r"(?![A-Za-z])", self.source[self.i:]))

    def command(self) -> str:
        self.i += 1
        match = re.match(r"[A-Za-z]+|.", self.source[self.i:], re.S)
        if not match:
            self.fail("TRAILING_BACKSLASH", "missing command")
        self.i += len(match[0])
        return match[0]

    def sequence(self, stop: str | None = None) -> Node:
        start, nodes = self.i, []
        while True:
            self.space()
            if self.i >= len(self.source):
                if stop:
                    self.fail("UNCLOSED_GROUP", f"expected {stop}", start)
                break
            if stop and self.source[self.i] == stop:
                break
            if self.source[self.i] == "}":
                self.fail("UNEXPECTED_GROUP_END", "extra closing brace")
            if self.starts_command("right") or self.starts_command("end"):
                break
            if self.source.startswith(r"\\", self.i) or self.source[self.i] == "&":
                break
            node = self.atom()
            script_keys: set[str] = set()
            scripts = []
            while True:
                self.space()
                if self.i >= len(self.source) or self.source[self.i] not in "^_":
                    break
                key, script_start = self.source[self.i], self.i
                self.i += 1
                if key in script_keys:
                    self.fail("DUPLICATE_SCRIPT", f"duplicate {key} on one atom", script_start)
                script_keys.add(key)
                arg = self.argument()
                if arg.kind == "group" and not arg.children[0].children:
                    self.fail("EMPTY_SCRIPT", "empty upper/lower limit", script_start)
                scripts.append(Node("sup" if key == "^" else "sub", children=[arg], start=script_start, end=self.i))
            if scripts:
                node = Node("scripts", children=[node, *scripts], start=node.start, end=self.i)
            nodes.append(node)
        return Node("sequence", children=nodes, start=start, end=self.i)

    def argument(self) -> Node:
        self.space()
        if self.i == len(self.source) or self.source[self.i] in "^_}&":
            self.fail("MISSING_ARGUMENT", "expected a group or one LaTeX atom")
        # TeX consumes ONE unbraced character; ^12 is ^{1} followed by 2.
        return self.atom(single=True)

    def raw_group(self) -> str:
        self.space()
        if self.i == len(self.source) or self.source[self.i] != "{":
            self.fail("GROUP_REQUIRED", "command requires an explicit group")
        self.i += 1
        start = self.i
        while self.i < len(self.source) and self.source[self.i] != "}":
            if self.source[self.i] in "{\\":
                self.fail("UNSUPPORTED_TEXT_GROUP", "nested/escaped text requires explicit review")
            self.i += 1
        if self.i == len(self.source):
            self.fail("UNCLOSED_GROUP", "missing closing text brace", start)
        value = self.source[start:self.i]
        self.i += 1
        return value

    def delimiter(self) -> str:
        self.space()
        if self.i == len(self.source):
            self.fail("MISSING_DELIMITER", "expected visible delimiter")
        if self.source[self.i] == "\\":
            command = self.command()
            if command not in _DELIMS:
                self.fail("UNSUPPORTED_DELIMITER", command)
            return _DELIMS[command]
        value = self.source[self.i]
        self.i += 1
        if value not in "()[]|.":
            self.fail("UNSUPPORTED_DELIMITER", value)
        return value

    def environment(self, start: int) -> Node:
        name = self.raw_group()
        if name not in _ENVS:
            self.fail("UNSUPPORTED_ENVIRONMENT", name, start)
        rows, cells = [], []
        while True:
            cell = self.sequence()
            if not cell.children:
                self.fail("EMPTY_MATRIX_CELL", "empty matrix/case cell")
            cells.append(cell)
            self.space()
            if self.i < len(self.source) and self.source[self.i] == "&":
                self.i += 1
                continue
            rows.append(Node("row", children=cells, start=cells[0].start, end=self.i))
            cells = []
            if self.source.startswith(r"\\", self.i):
                self.i += 2
                self.space()
                if not self.starts_command("end"):
                    continue
            if not self.starts_command("end"):
                self.fail("UNCLOSED_ENVIRONMENT", name, start)
            self.command()
            if self.raw_group() != name:
                self.fail("ENVIRONMENT_MISMATCH", name, start)
            break
        widths = {len(row.children) for row in rows}
        if len(widths) != 1 or (name == "cases" and widths != {2}):
            self.fail("MATRIX_SHAPE", "ragged matrix or cases without value/condition pairs", start)
        return Node("environment", name, rows, start, self.i)

    def atom(self, single: bool = False) -> Node:
        self.space()
        start = self.i
        if self.i >= len(self.source):
            self.fail("MISSING_ARGUMENT", "unexpected end")
        char = self.source[self.i]
        self.i += 1
        if char == "{":
            body = self.sequence("}")
            if self.i == len(self.source) or self.source[self.i] != "}":
                self.fail("UNCLOSED_GROUP", "missing closing brace", start)
            self.i += 1
            return Node("group", children=[body], start=start, end=self.i)
        if char == "\\":
            self.i = start
            name = self.command()
            if name in _SYMBOLS:
                return Node("symbol", _SYMBOLS[name], start=start, end=self.i)
            if name in _FUNCTIONS or name in _OPERATORS:
                return Node("operator" if name in _OPERATORS else "function", _OPERATORS.get(name, name), start=start, end=self.i)
            if name in {"{", "}", "|"}:
                return Node("delimiter", _DELIMS[name], start=start, end=self.i)
            if name in {",", ";", ":", "!", " ", "quad", "qquad"}:
                return Node("space", name, start=start, end=self.i)
            if name in {"frac", "dfrac", "tfrac", "binom"}:
                args = [self.argument(), self.argument()]
                if any(not _has_content(arg) for arg in args):
                    self.fail("EMPTY_ARGUMENT", "fraction/binomial has an empty operand", start)
                return Node("binomial" if name == "binom" else "fraction", children=args, start=start, end=self.i)
            if name == "sqrt":
                self.space()
                degree = None
                if self.i < len(self.source) and self.source[self.i] == "[":
                    self.i += 1
                    degree = self.sequence("]")
                    if not degree.children:
                        self.fail("EMPTY_ROOT_INDEX", "missing root degree", start)
                    self.i += 1
                radicand = self.argument()
                if not _has_content(radicand):
                    self.fail("EMPTY_ARGUMENT", "root has an empty radicand", start)
                return Node("root", children=([degree, radicand] if degree else [radicand]), start=start, end=self.i)
            if name in _ACCENTS or name in {"mathrm", "operatorname", "mathbf", "mathit"}:
                arg = self.argument()
                keyword = _ACCENTS.get(name, {"mathrm": "rm", "operatorname": "rm", "mathbf": "bold", "mathit": "it"}.get(name))
                return Node("decoration", keyword, [arg], start, self.i)
            if name == "text":
                value = self.raw_group()
                if '"' in value or "\n" in value:
                    self.fail("UNSUPPORTED_TEXT_GROUP", "quote or line break in equation text", start)
                return Node("text", value, start=start, end=self.i)
            if name == "mathbb":
                letter = self.raw_group()
                symbols = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ"}
                if letter not in symbols:
                    self.fail("UNSUPPORTED_BLACKBOARD", letter, start)
                return Node("symbol", symbols[letter], start=start, end=self.i)
            if name == "left":
                left = self.delimiter()
                body = self.sequence()
                if not self.starts_command("right"):
                    self.fail("UNPAIRED_DELIMITER", "left without right", start)
                self.command()
                right = self.delimiter()
                return Node("fenced", f"{left}\t{right}", [body], start, self.i)
            if name == "begin":
                return self.environment(start)
            self.fail("UNSUPPORTED_COMMAND", "\\" + name, start)
        if char in "^_$&#%" or char == "}":
            self.fail("UNEXPECTED_TOKEN", char, start)
        if char.isdigit() and not single:
            while self.i < len(self.source) and (self.source[self.i].isdigit() or self.source[self.i] == "."):
                self.i += 1
        if "가" <= char <= "힣":
            self.fail("UNWRAPPED_TEXT", "prose must be native text or explicit text group", start)
        return Node("atom", self.source[start:self.i], start=start, end=self.i)


def _has_content(node: Node) -> bool:
    return bool(node.value.strip()) if node.kind in {"atom", "symbol", "text", "operator", "function", "delimiter"} else any(_has_content(child) for child in node.children)


def _inner(node: Node) -> str:
    return _render(node.children[0]) if node.kind == "group" else _render(node)


def _render(node: Node) -> str:
    kind = node.kind
    if kind in {"atom", "symbol", "operator", "function", "delimiter"}:
        return node.value
    if kind == "space":
        return {"!": "", ",": "`", ":": "`", ";": "~", "quad": "~~", "qquad": "~~~~"}.get(node.value, "~")
    if kind == "sequence":
        # Lexical spaces separate Hancom keywords; they are not paragraph breaks.
        return " ".join(_render(child) for child in node.children).strip()
    if kind == "group":
        return "{" + _render(node.children[0]) + "}"
    if kind == "scripts":
        base = node.children[0]
        rendered = _render(base)
        if base.kind in {"root", "decoration", "environment", "binomial", "text"}:
            rendered = "{" + rendered + "}"
        return rendered + "".join(("^" if child.kind == "sup" else "_") + "{" + _inner(child.children[0]) + "}" for child in node.children[1:])
    if kind == "fraction":
        return "{{" + _inner(node.children[0]) + "} over {" + _inner(node.children[1]) + "}}"
    if kind == "binomial":
        return "left ( {" + _inner(node.children[0]) + "} atop {" + _inner(node.children[1]) + "} right )"
    if kind == "root":
        if len(node.children) == 2:
            return "root {" + _inner(node.children[0]) + "} of {" + _inner(node.children[1]) + "}"
        return "sqrt {" + _inner(node.children[0]) + "}"
    if kind == "decoration":
        return node.value + " {" + _inner(node.children[0]) + "}"
    if kind == "text":
        return 'rm {"' + node.value + '"}'
    if kind == "fenced":
        left, right = node.value.split("\t")
        return "left " + left + " " + _render(node.children[0]) + " right " + right
    if kind == "environment":
        # Hanword's default matrix/cases column gap can be zero. A native
        # math-space token keeps adjacent expression/condition cells distinct.
        separator = " & " if node.value in {"aligned", "gathered"} else " & ~~ "
        return _ENVS[node.value] + " {" + " # ".join(separator.join(_render(cell) for cell in row.children) for row in node.children) + "}"
    raise AssertionError(kind)


def validate_hancom_script(script: str) -> str:
    if not isinstance(script, str) or not script.strip():
        raise EquationCompileError("EMPTY_EQUATION", "an equation cannot be replaced by x")
    if "\\" in script:
        raise EquationCompileError("RAW_BACKSLASH", "Hancom input may not contain LaTeX commands")
    if re.search(r"\b(?:frac|dfrac|tfrac|begin|end)\b", script):
        raise EquationCompileError("LATEX_IN_HANCOM", "declare the actual input dialect")
    depth, quoted = 0, False
    for i, char in enumerate(script):
        if char == '"':
            quoted = not quoted
        if quoted:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise EquationCompileError("UNBALANCED_GROUP", "extra closing brace", i)
        elif char in "^_":
            if not re.match(r"\s*\{", script[i + 1:]):
                raise EquationCompileError("UNGROUPED_SCRIPT", "Hancom script extent must be explicit", i)
    if depth or quoted:
        raise EquationCompileError("UNBALANCED_GROUP", "unclosed group or text quote")
    return script.strip()


def _check_operators(tree: Node, policies: dict[int, str]) -> None:
    used: set[int] = set()

    def visit(node: Node, attached: dict[str, Node] | None = None):
        if node.kind == "scripts":
            visit(node.children[0], {child.kind: child.children[0] for child in node.children[1:]})
            for child in node.children[1:]:
                visit(child)
            return
        if node.kind == "operator":
            limits = attached or {}
            policy = policies.get(node.start, "default")
            if node.start in policies:
                used.add(node.start)
            if policy not in {"default", "symbol_only", "lower_only"}:
                raise EquationCompileError("INVALID_OPERATOR_POLICY", policy, node.start)
            if policy == "symbol_only":
                good = not limits
            elif policy == "lower_only":
                good = set(limits) == {"sub"} and node.value != "lim"
            elif node.value in {"sum", "prod"}:
                good = set(limits) == {"sub", "sup"}
            elif node.value == "lim":
                good = set(limits) == {"sub"} and "→" in _render(limits["sub"])
            else:
                good = not limits or set(limits) == {"sub", "sup"}
            if not good:
                raise EquationCompileError("OPERATOR_BOUNDS", f"{node.value}: missing/inconsistent limits or approach condition ({policy})", node.start)
        for child in node.children:
            visit(child)

    visit(tree)
    if used != set(policies):
        raise EquationCompileError("UNUSED_OPERATOR_POLICY", "exception must name an actual source operator span")


def compile_equation(source: str, *, dialect: str, operator_policies: dict[int, str] | None = None) -> CompiledEquation:
    if not isinstance(source, str) or not source.strip():
        raise EquationCompileError("EMPTY_EQUATION", "equation source is empty")
    if dialect == "hancom":
        return CompiledEquation(source, dialect, validate_hancom_script(source), None)
    if dialect != "latex":
        raise EquationCompileError("DIALECT_REQUIRED", "use explicit latex or hancom; auto-detection is unsafe")
    parser = _LatexParser(source)
    tree = parser.sequence()
    parser.space()
    if parser.i != len(source):
        parser.fail("UNCONSUMED_INPUT", "unexpected alignment/end/delimiter command")
    if not _has_content(tree):
        raise EquationCompileError("EMPTY_EQUATION", "no mathematical content")
    _check_operators(tree, {int(key): value for key, value in (operator_policies or {}).items()})
    script = validate_hancom_script(_render(tree))
    return CompiledEquation(source, dialect, script, tree)
