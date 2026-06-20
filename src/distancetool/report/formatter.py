"""
Format DiffResult as a human-readable distance report.

Output structure
----------------
  === Distance Report: <func_name> ===

  Result: EQUIVALENT  (if provably identical)
    or
  Result: DIFFERS

  Symbolic distance:  |f_old(x) - f_new(x)| = <Z3 expression>
  Differs when:       <Z3 condition>

  Counterexamples (inputs where outputs differ):
    x=3 → old: 6, new: 9, distance: 3
    ...

  Agree example (inputs where outputs match):
    x=-2 → both return -2

  Test recommendation:
    Must re-run:  tests covering inputs where <condition>
    Can skip:     tests provably covering only the agree region
"""

from __future__ import annotations
import json
from typing import List

from ..engine.differencer import DiffResult, Example
from ..ir.types import IRType


# --------------------------------------------------------------------------- #
# Human-readable report                                                         #
# --------------------------------------------------------------------------- #

def format_report(result: DiffResult) -> str:
    lines: List[str] = []
    _header(lines, result.func_name, result.params)

    if result.error:
        lines += ["", f"Analysis error: {result.error}", ""]
        return "\n".join(lines)

    if result.equivalent:
        lines += [
            "",
            "Result:  EQUIVALENT",
            "",
            "The two versions are provably identical on all inputs.",
            "",
        ]
        return "\n".join(lines)

    # ── non-equivalent ───────────────────────────────────────────────────────
    lines += ["", "Result:  DIFFERS", ""]

    if result.symbolic_distance:
        lines.append(f"Symbolic distance:  |f_old − f_new| = {result.symbolic_distance}")
    if result.diff_condition:
        lines.append(f"Differs when:       {result.diff_condition}")
    lines.append("")

    if result.counterexamples:
        lines.append("Counterexamples (inputs where outputs differ):")
        for ex in result.counterexamples:
            inputs_str = ", ".join(f"{k}={v}" for k, v in ex.inputs.items())
            lines.append(
                f"  {inputs_str}  →  old: {ex.old_output},  new: {ex.new_output}"
                f"  (distance: {ex.distance})"
            )
        lines.append("")

    if result.agree_example:
        ex = result.agree_example
        inputs_str = ", ".join(f"{k}={v}" for k, v in ex.inputs.items())
        lines.append(f"Agree example (functions match):  {inputs_str} → {ex.old_output}")
        lines.append("")

    _test_recommendation(lines, result)
    return "\n".join(lines)


def _header(lines: List[str], func_name: str, params: list) -> None:
    param_str = ", ".join(f"{n}: {t}" for n, t in params)
    lines.append(f"=== Distance Report: {func_name}({param_str}) ===")


def _test_recommendation(lines: List[str], result: DiffResult) -> None:
    lines.append("Test recommendation:")
    if result.diff_condition:
        lines.append(f"  Must re-run:  tests covering inputs where {result.diff_condition}")
    else:
        lines.append("  Must re-run:  all tests (diff region could not be characterised)")
    if result.agree_example:
        lines.append(
            "  Can skip:     tests provably limited to the agree region "
            "(check against diff condition above)"
        )
    lines.append("")


# --------------------------------------------------------------------------- #
# JSON output                                                                   #
# --------------------------------------------------------------------------- #

def format_json(result: DiffResult) -> str:
    def ex_to_dict(ex: Example) -> dict:
        return {
            "inputs": ex.inputs,
            "old_output": ex.old_output,
            "new_output": ex.new_output,
            "distance": ex.distance,
        }

    payload = {
        "func_name": result.func_name,
        "params": [[n, str(t)] for n, t in result.params],
        "equivalent": result.equivalent,
        "symbolic_distance": result.symbolic_distance,
        "diff_condition": result.diff_condition,
        "counterexamples": [ex_to_dict(e) for e in result.counterexamples],
        "agree_example": ex_to_dict(result.agree_example) if result.agree_example else None,
        "error": result.error,
    }
    return json.dumps(payload, indent=2)
