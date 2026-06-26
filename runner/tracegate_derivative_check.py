#!/usr/bin/env python3
"""Check declared symbolic derivatives against their source expressions.

This runner is dependency-free by design. It supports a conservative algebraic
subset used by most model builders: +, -, *, /, powers, parentheses, and common
elementary functions. Unsupported expressions BLOCK rather than silently pass.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from tracegate_common import Check, load_json, make_report, print_report, status_code


SAFE_FUNCTIONS = {
    "abs": abs,
    "cos": math.cos,
    "exp": math.exp,
    "ln": math.log,
    "log": math.log,
    "sin": math.sin,
    "sqrt": math.sqrt,
    "tan": math.tan,
}

KNOWN_CONSTANTS = {
    "E": math.e,
    "F": 96485.33212,
    "R": 8.314462618,
    "T": 298.15,
    "e": math.e,
    "pi": math.pi,
}

SAMPLES = [0.2, 0.5, 1.0, 1.7, 3.0]


class DerivativeError(ValueError):
    """Raised when an expression cannot be verified safely."""


def preprocess_expression(expression: str) -> str:
    text = str(expression)
    text = text.replace("−", "-").replace("×", "*").replace("^", "**")
    text = re.sub(r"\bln\s*\(", "log(", text)
    return text


def parse_expression(expression: str) -> ast.AST:
    try:
        tree = ast.parse(preprocess_expression(expression), mode="eval")
    except SyntaxError as exc:
        raise DerivativeError(f"parse failed: {exc}") from exc
    validate_ast(tree)
    return tree.body


def validate_ast(node: ast.AST) -> None:
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.USub,
        ast.UAdd,
    )
    for child in ast.walk(node):
        if not isinstance(child, allowed):
            raise DerivativeError(f"unsupported syntax: {type(child).__name__}")
        if isinstance(child, ast.Call):
            if not isinstance(child.func, ast.Name) or child.func.id not in SAFE_FUNCTIONS:
                raise DerivativeError("unsupported function call")


def const(value: float | int) -> ast.Constant:
    return ast.Constant(value=value)


def clone(node: ast.AST) -> ast.AST:
    return copy.deepcopy(node)


def call(name: str, *args: ast.AST) -> ast.Call:
    return ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=[clone(arg) for arg in args], keywords=[])


def binop(left: ast.AST, op: ast.operator, right: ast.AST) -> ast.AST:
    return simplify(ast.BinOp(left=clone(left), op=op, right=clone(right)))


def is_number(node: ast.AST, value: float | None = None) -> bool:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, int | float):
        return False
    if value is None:
        return True
    return float(node.value) == float(value)


def simplify(node: ast.AST) -> ast.AST:
    if isinstance(node, ast.UnaryOp):
        node.operand = simplify(node.operand)
        if isinstance(node.op, ast.UAdd):
            return node.operand
        if isinstance(node.op, ast.USub) and is_number(node.operand):
            return const(-float(node.operand.value))
        return node
    if not isinstance(node, ast.BinOp):
        return node
    node.left = simplify(node.left)
    node.right = simplify(node.right)
    if isinstance(node.op, ast.Add):
        if is_number(node.left, 0):
            return node.right
        if is_number(node.right, 0):
            return node.left
    if isinstance(node.op, ast.Sub):
        if is_number(node.right, 0):
            return node.left
    if isinstance(node.op, ast.Mult):
        if is_number(node.left, 0) or is_number(node.right, 0):
            return const(0)
        if is_number(node.left, 1):
            return node.right
        if is_number(node.right, 1):
            return node.left
    if isinstance(node.op, ast.Div):
        if is_number(node.left, 0):
            return const(0)
        if is_number(node.right, 1):
            return node.left
    if isinstance(node.op, ast.Pow):
        if is_number(node.right, 0):
            return const(1)
        if is_number(node.right, 1):
            return node.left
    if is_number(node.left) and is_number(node.right):
        try:
            return const(eval_ast(node, {}))
        except Exception:
            return node
    return node


def depends_on(node: ast.AST, variable: str) -> bool:
    return any(isinstance(child, ast.Name) and child.id == variable for child in ast.walk(node))


def differentiate(node: ast.AST, variable: str) -> ast.AST:
    if isinstance(node, ast.Constant):
        return const(0)
    if isinstance(node, ast.Name):
        return const(1 if node.id == variable else 0)
    if isinstance(node, ast.UnaryOp):
        d_operand = differentiate(node.operand, variable)
        if isinstance(node.op, ast.USub):
            return simplify(ast.UnaryOp(op=ast.USub(), operand=d_operand))
        if isinstance(node.op, ast.UAdd):
            return d_operand
    if isinstance(node, ast.BinOp):
        left = node.left
        right = node.right
        d_left = differentiate(left, variable)
        d_right = differentiate(right, variable)
        if isinstance(node.op, ast.Add):
            return binop(d_left, ast.Add(), d_right)
        if isinstance(node.op, ast.Sub):
            return binop(d_left, ast.Sub(), d_right)
        if isinstance(node.op, ast.Mult):
            return binop(binop(d_left, ast.Mult(), right), ast.Add(), binop(left, ast.Mult(), d_right))
        if isinstance(node.op, ast.Div):
            numerator = binop(binop(d_left, ast.Mult(), right), ast.Sub(), binop(left, ast.Mult(), d_right))
            denominator = binop(right, ast.Pow(), const(2))
            return binop(numerator, ast.Div(), denominator)
        if isinstance(node.op, ast.Pow):
            if not depends_on(right, variable):
                exponent_minus_one = binop(right, ast.Sub(), const(1))
                return binop(binop(right, ast.Mult(), binop(left, ast.Pow(), exponent_minus_one)), ast.Mult(), d_left)
            term = binop(d_right, ast.Mult(), call("log", left))
            term = binop(term, ast.Add(), binop(right, ast.Mult(), binop(d_left, ast.Div(), left)))
            return binop(binop(left, ast.Pow(), right), ast.Mult(), term)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if len(node.args) != 1:
            raise DerivativeError("only one-argument functions are supported")
        arg = node.args[0]
        d_arg = differentiate(arg, variable)
        name = node.func.id
        if name in {"log", "ln"}:
            return binop(d_arg, ast.Div(), arg)
        if name == "exp":
            return binop(call("exp", arg), ast.Mult(), d_arg)
        if name == "sqrt":
            return binop(d_arg, ast.Div(), binop(const(2), ast.Mult(), call("sqrt", arg)))
        if name == "sin":
            return binop(call("cos", arg), ast.Mult(), d_arg)
        if name == "cos":
            return simplify(ast.UnaryOp(op=ast.USub(), operand=binop(call("sin", arg), ast.Mult(), d_arg)))
        if name == "tan":
            return binop(d_arg, ast.Div(), binop(call("cos", arg), ast.Pow(), const(2)))
        if name == "abs":
            raise DerivativeError("abs() derivative is not supported")
    raise DerivativeError(f"unsupported derivative syntax: {type(node).__name__}")


def collect_names(node: ast.AST) -> set[str]:
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def deterministic_value(name: str) -> float:
    if name in KNOWN_CONSTANTS:
        return KNOWN_CONSTANTS[name]
    total = sum(ord(ch) for ch in name)
    return 0.75 + (total % 37) / 10.0


def eval_ast(node: ast.AST, env: dict[str, float]) -> float:
    ast.fix_missing_locations(node)
    compiled = compile(ast.Expression(body=clone(node)), "<tracegate-expression>", "eval")
    namespace: dict[str, Any] = dict(SAFE_FUNCTIONS)
    namespace.update(KNOWN_CONSTANTS)
    namespace.update(env)
    return float(eval(compiled, {"__builtins__": {}}, namespace))


def equivalent(computed: ast.AST, declared: ast.AST, variable: str, tolerance: float) -> tuple[bool, float, str | None]:
    names = collect_names(computed) | collect_names(declared)
    max_rel = 0.0
    for sample in SAMPLES:
        env = {name: deterministic_value(name) for name in names}
        env[variable] = sample
        try:
            left = eval_ast(computed, env)
            right = eval_ast(declared, env)
        except Exception as exc:  # noqa: BLE001
            return False, max_rel, f"evaluation failed at {variable}={sample}: {exc}"
        if not (math.isfinite(left) and math.isfinite(right)):
            return False, max_rel, f"non-finite value at {variable}={sample}"
        rel = abs(left - right) / max(1.0, abs(left), abs(right))
        max_rel = max(max_rel, rel)
    return max_rel <= tolerance, max_rel, None


def expression_index(runtime: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    entries = runtime.get("expressions", runtime.get("equations", runtime.get("functions", [])))
    if isinstance(entries, dict):
        for key, value in entries.items():
            if isinstance(value, str):
                out[str(key)] = value
            elif isinstance(value, dict) and "expression" in value:
                out[str(key)] = str(value["expression"])
    elif isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key = entry.get("expression_id") or entry.get("equation_id") or entry.get("function_id") or entry.get("id") or entry.get("name")
            expression = entry.get("expression")
            if key and expression is not None:
                out[str(key)] = str(expression)
    return out


def load_runtime(project: Path) -> tuple[dict[str, str], str | None]:
    runtime_path = project / "runtime_expression_dump.json"
    if not runtime_path.is_file():
        return {}, "runtime_expression_dump.json is missing"
    runtime, err = load_json(runtime_path)
    if err or not isinstance(runtime, dict):
        return {}, f"runtime_expression_dump.json parse failed: {err}"
    return expression_index(runtime), None


def get_pair_expression(pair: dict[str, Any], runtime: dict[str, str], direct_keys: list[str], id_keys: list[str]) -> tuple[str | None, str | None]:
    for key in direct_keys:
        value = pair.get(key)
        if isinstance(value, str) and value.strip():
            return value, None
    for key in id_keys:
        expr_id = pair.get(key)
        if isinstance(expr_id, str) and expr_id:
            if expr_id in runtime:
                return runtime[expr_id], None
            return None, f"runtime expression missing for id {expr_id!r}"
    return None, "expression is not declared"


def derivative_pairs(manifest: dict[str, Any]) -> list[dict[str, Any]] | None:
    pairs = manifest.get("derivative_pairs", manifest.get("derivatives"))
    if isinstance(pairs, list):
        return [pair for pair in pairs if isinstance(pair, dict)]
    return None


def run(project: Path) -> dict[str, Any]:
    project = project.resolve()
    checks: list[Check] = []
    manifest_path = project / "EQUATION_MANIFEST.json"
    if not manifest_path.is_file():
        checks.append(Check("SKIPPED_NOT_CONFIGURED", "derivative_check_skipped", "EQUATION_MANIFEST.json is absent"))
        return make_report(project, "tracegate_derivative_check", checks)
    manifest, err = load_json(manifest_path)
    if err or not isinstance(manifest, dict):
        checks.append(Check("BLOCK", "equation_manifest_parse_error", f"EQUATION_MANIFEST.json parse failed: {err}"))
        return make_report(project, "tracegate_derivative_check", checks)
    pairs = derivative_pairs(manifest)
    if not pairs:
        checks.append(Check("SKIPPED_NOT_CONFIGURED", "derivative_pairs_missing", "EQUATION_MANIFEST.json has no derivative_pairs[]"))
        return make_report(project, "tracegate_derivative_check", checks)

    runtime, runtime_err = load_runtime(project)
    if runtime_err and any(not any(key in pair for key in ["function_expression", "source_expression", "mu_expression"]) or not any(key in pair for key in ["derivative_expression", "declared_derivative_expression", "dmu_dc_expression"]) for pair in pairs):
        checks.append(Check("BLOCK", "runtime_expression_dump_missing", runtime_err))
        return make_report(project, "tracegate_derivative_check", checks)

    for idx, pair in enumerate(pairs):
        pair_id = str(pair.get("pair_id") or pair.get("id") or f"derivative_pair_{idx}")
        variable = pair.get("with_respect_to") or pair.get("derivative_var") or pair.get("variable")
        if not isinstance(variable, str) or not variable:
            checks.append(Check("BLOCK", "derivative_variable_missing", f"{pair_id}: derivative variable is missing"))
            continue
        function_expression, function_err = get_pair_expression(
            pair,
            runtime,
            ["function_expression", "source_expression", "mu_expression"],
            ["function_id", "function", "source_id"],
        )
        derivative_expression, derivative_err = get_pair_expression(
            pair,
            runtime,
            ["derivative_expression", "declared_derivative_expression", "dmu_dc_expression"],
            ["derivative_id", "derivative_declared", "declared_derivative_id"],
        )
        if function_err or function_expression is None:
            checks.append(Check("BLOCK", "derivative_function_missing", f"{pair_id}: {function_err}"))
            continue
        if derivative_err or derivative_expression is None:
            checks.append(Check("BLOCK", "derivative_expression_missing", f"{pair_id}: {derivative_err}"))
            continue
        try:
            source_ast = parse_expression(function_expression)
            declared_ast = parse_expression(derivative_expression)
            computed_ast = simplify(differentiate(source_ast, variable))
        except DerivativeError as exc:
            checks.append(Check("BLOCK", "derivative_parse_or_symbolic_error", f"{pair_id}: {exc}"))
            continue
        tolerance = float(pair.get("numeric_tolerance", pair.get("tolerance", 1e-8)))
        ok, max_rel, eval_err = equivalent(computed_ast, declared_ast, variable, tolerance)
        computed_text = ast.unparse(ast.fix_missing_locations(computed_ast))
        if eval_err:
            checks.append(Check("BLOCK", "derivative_eval_error", f"{pair_id}: {eval_err}"))
        elif ok:
            checks.append(Check("PASS", "derivative_consistency", f"{pair_id}: d/d{variable} matches declared derivative; max_rel={max_rel:.3g}"))
        else:
            checks.append(
                Check(
                    "BLOCK",
                    "derivative_consistency_mismatch",
                    f"{pair_id}: declared derivative does not match symbolic derivative; max_rel={max_rel:.3g}; computed={computed_text}",
                )
            )
    return make_report(project, "tracegate_derivative_check", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TraceGate derivative consistency gates.")
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(Path(args.project_dir))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report("TraceGate Derivative Check", report)
    return status_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
