# SPDX-License-Identifier: PMM-1.0
# Guardrail test: prevent EventLog.read_all() regressions into hot-path runtime functions.

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_module_ast(relative_path: str) -> ast.Module:
    path = PROJECT_ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path))


def _find_function_def(module: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function {name!r} not found in module")


def _collect_read_all_calls(func: ast.FunctionDef) -> List[Tuple[int, int]]:
    calls: List[Tuple[int, int]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            func_expr = node.func
            if isinstance(func_expr, ast.Attribute) and func_expr.attr == "read_all":
                calls.append((node.lineno, node.col_offset))
    return calls


def _allowed_run_turn_read_all_calls(func: ast.FunctionDef) -> List[Tuple[int, int]]:
    """Allow read_all() only in the replay guard at the top of run_turn.

    The intended structure is:

        def run_turn(...):
            if self.replay:
                return self.eventlog.read_all()
            ...
    """

    if not func.body:
        return []

    first_stmt = func.body[0]
    if not isinstance(first_stmt, ast.If):
        return []

    test = first_stmt.test
    is_self_replay = (
        isinstance(test, ast.Attribute)
        and test.attr == "replay"
        and isinstance(test.value, ast.Name)
        and test.value.id == "self"
    )
    if not is_self_replay:
        return []

    allowed: List[Tuple[int, int]] = []
    for node in ast.walk(first_stmt):
        if isinstance(node, ast.Call):
            func_expr = node.func
            if isinstance(func_expr, ast.Attribute) and func_expr.attr == "read_all":
                allowed.append((node.lineno, node.col_offset))
    return allowed


def _assert_no_forbidden_read_all(
    relative_path: str, func_name: str, allow_replay: bool = False
) -> None:
    module = _load_module_ast(relative_path)
    func = _find_function_def(module, func_name)

    calls = _collect_read_all_calls(func)

    if allow_replay and func_name == "run_turn":
        allowed = set(_allowed_run_turn_read_all_calls(func))
        violations = [(ln, col) for (ln, col) in calls if (ln, col) not in allowed]
    else:
        violations = calls

    if violations:
        loc_str = ", ".join(f"line {ln}" for (ln, _col) in violations)
        raise AssertionError(
            f"Forbidden read_all() call(s) in {relative_path}:{func_name} at {loc_str}. "
            "Hot-path functions must use read_tail() or projections instead."
        )


def test_hot_path_functions_do_not_call_read_all() -> None:
    """Ensure hot-path runtime functions avoid EventLog.read_all().

    This enforces the architectural rule that per-turn and per-tick paths
    (`run_turn`, `run_tick`, `synthesize_reflection`, `maybe_append_summary`)
    must never regress back to full-ledger scans. Replay-mode in run_turn is
    explicitly allowed to use read_all().
    """

    # RuntimeLoop hot paths
    _assert_no_forbidden_read_all("runtime/loop.py", "run_turn", allow_replay=True)
    _assert_no_forbidden_read_all("runtime/loop.py", "run_tick")

    # Reflection synthesizer (user-turn path)
    _assert_no_forbidden_read_all(
        "runtime/reflection_synthesizer.py", "synthesize_reflection"
    )

    # Identity summary (per-turn periodic summaries)
    _assert_no_forbidden_read_all("runtime/identity_summary.py", "maybe_append_summary")
