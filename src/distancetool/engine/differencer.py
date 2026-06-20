"""
Compute the DLR-style distance between two versions of a function.

The core approach:
1. Encode both functions against shared symbolic parameters → Z3 expressions
   out_old(x), out_new(x).
2. Check satisfiability of (out_old ≠ out_new):
   - UNSAT  → provably equivalent.
   - SAT    → functions differ somewhere; proceed to characterise where.
   - UNKNOWN → timeout / solver gave up.
3. When they differ:
   a. Compute the symbolic distance expression δ(x) = |out_old(x) − out_new(x)|
      (or the discrete 0/1 for Bool outputs).
   b. Collect up to MAX_EXAMPLES counterexamples — concrete inputs where they differ.
   c. Try to characterise the "non-zero region" by checking whether the symbolic
      diff condition simplifies to a readable Z3 formula.
   d. Check whether there exist inputs where they agree (zero-distance region).

The result is a DiffResult carrying:
  - equivalent: bool
  - symbolic_distance: str   — simplified Z3 expression for δ(x)
  - diff_condition: str       — simplified Z3 formula for "where they differ"
  - counterexamples: list     — concrete inputs demonstrating differences
  - agree_example: dict|None  — a concrete input where they agree (if any)
  - old_val / new_val at each counterexample (for the report)
"""

from __future__ import annotations
import z3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..ir.types import IRType, IntType, FloatType, BoolType
from ..ir.terms import FuncDef
from .z3_encoder import Z3Encoder, EncoderError


MAX_EXAMPLES = 5
DEFAULT_TIMEOUT_MS = 15_000


# --------------------------------------------------------------------------- #
# Result types                                                                  #
# --------------------------------------------------------------------------- #

@dataclass
class Example:
    inputs: Dict[str, object]
    old_output: object
    new_output: object
    distance: object


@dataclass
class DiffResult:
    func_name: str
    params: List[Tuple[str, IRType]]

    equivalent: bool
    """True iff Z3 proved the two versions identical on all inputs."""

    symbolic_distance: Optional[str]
    """Simplified Z3 expression for |out_old(x) − out_new(x)|, or None."""

    diff_condition: Optional[str]
    """Simplified Z3 formula describing the region where outputs differ, or None."""

    counterexamples: List[Example] = field(default_factory=list)
    """Concrete inputs where the functions produce different outputs."""

    agree_example: Optional[Example] = None
    """A concrete input where both versions agree (if one exists)."""

    error: Optional[str] = None
    """Human-readable error message if analysis could not complete."""


# --------------------------------------------------------------------------- #
# Main entry                                                                    #
# --------------------------------------------------------------------------- #

def compute_diff(
    func_old: FuncDef,
    func_new: FuncDef,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> DiffResult:
    """
    Compute the semantic distance between *func_old* and *func_new*.
    Both functions must have the same parameter names and types.
    """
    if len(func_old.params) != len(func_new.params):
        return DiffResult(
            func_name=func_old.name,
            params=func_old.params,
            equivalent=False,
            symbolic_distance=None,
            diff_condition=None,
            error="Functions have different numbers of parameters",
        )

    for (n1, t1), (n2, t2) in zip(func_old.params, func_new.params):
        if n1 != n2 or t1 != t2:
            return DiffResult(
                func_name=func_old.name,
                params=func_old.params,
                equivalent=False,
                symbolic_distance=None,
                diff_condition=None,
                error=(
                    f"Parameter mismatch: old has '{n1}: {t1}', "
                    f"new has '{n2}: {t2}'"
                ),
            )

    try:
        return _run_diff(func_old, func_new, timeout_ms)
    except EncoderError as e:
        return DiffResult(
            func_name=func_old.name,
            params=func_old.params,
            equivalent=False,
            symbolic_distance=None,
            diff_condition=None,
            error=f"Encoding error: {e}",
        )
    except Exception as e:  # noqa: BLE001
        return DiffResult(
            func_name=func_old.name,
            params=func_old.params,
            equivalent=False,
            symbolic_distance=None,
            diff_condition=None,
            error=f"Internal error: {e}",
        )


# --------------------------------------------------------------------------- #
# Core implementation                                                           #
# --------------------------------------------------------------------------- #

def _run_diff(func_old: FuncDef, func_new: FuncDef, timeout_ms: int) -> DiffResult:
    # ── Encode both functions with shared symbolic parameters ────────────────
    enc_old = Z3Encoder()
    sym_params = enc_old.setup_params(func_old)
    out_old = enc_old.encode(func_old.body)

    enc_new = Z3Encoder()
    enc_new.env = dict(enc_old.env)   # same symbolic variables
    out_new = enc_new.encode(func_new.body)

    return_type = func_old.return_type

    # ── Step 1: equivalence check ────────────────────────────────────────────
    s = z3.Solver()
    s.set("timeout", timeout_ms)
    s.add(out_old != out_new)
    check = s.check()

    if check == z3.unsat:
        return DiffResult(
            func_name=func_old.name,
            params=func_old.params,
            equivalent=True,
            symbolic_distance="0",
            diff_condition="False",
        )

    if check == z3.unknown:
        return DiffResult(
            func_name=func_old.name,
            params=func_old.params,
            equivalent=False,
            symbolic_distance=None,
            diff_condition=None,
            error="SMT solver timed out or returned 'unknown'",
        )

    # ── Step 2: compute symbolic distance expression ─────────────────────────
    dist_expr = _distance_expr(out_old, out_new, return_type)
    sym_dist_str = _simplify_str(dist_expr)

    # ── Step 3: characterise the diff condition ──────────────────────────────
    diff_cond = out_old != out_new
    diff_cond_str = _simplify_str(diff_cond)

    # ── Step 4: collect counterexamples ─────────────────────────────────────
    counterexamples: List[Example] = []
    seen_points: List[z3.ExprRef] = []

    for _ in range(MAX_EXAMPLES):
        s2 = z3.Solver()
        s2.set("timeout", timeout_ms)
        s2.add(out_old != out_new)
        for pt in seen_points:
            s2.add(z3.Not(pt))
        if s2.check() != z3.sat:
            break
        model = s2.model()
        ex = _make_example(model, sym_params, out_old, out_new, dist_expr, return_type)
        counterexamples.append(ex)
        # Exclude this exact input point in subsequent iterations
        pt_cond = z3.And(*[
            sym == model.eval(sym, model_completion=True)
            for sym in sym_params.values()
        ])
        seen_points.append(pt_cond)

    # ── Step 5: find a zero-distance example (where they agree) ─────────────
    s3 = z3.Solver()
    s3.set("timeout", min(timeout_ms, 5_000))
    s3.add(out_old == out_new)
    agree_example: Optional[Example] = None
    if s3.check() == z3.sat:
        model = s3.model()
        agree_example = _make_example(model, sym_params, out_old, out_new, dist_expr, return_type)

    return DiffResult(
        func_name=func_old.name,
        params=func_old.params,
        equivalent=False,
        symbolic_distance=sym_dist_str,
        diff_condition=diff_cond_str,
        counterexamples=counterexamples,
        agree_example=agree_example,
    )


# --------------------------------------------------------------------------- #
# Distance expression helpers                                                   #
# --------------------------------------------------------------------------- #

def _distance_expr(out_old: z3.ExprRef, out_new: z3.ExprRef, return_type: IRType) -> z3.ExprRef:
    """Build a Z3 expression for the distance between out_old and out_new."""
    if isinstance(return_type, BoolType):
        return z3.If(out_old == out_new, z3.IntVal(0), z3.IntVal(1))
    # Numeric: absolute difference
    diff = out_old - out_new
    return z3.If(diff >= 0, diff, -diff)


# --------------------------------------------------------------------------- #
# Model-extraction helpers                                                      #
# --------------------------------------------------------------------------- #

def _make_example(
    model: z3.ModelRef,
    sym_params: Dict[str, z3.ExprRef],
    out_old: z3.ExprRef,
    out_new: z3.ExprRef,
    dist_expr: z3.ExprRef,
    return_type: IRType,
) -> Example:
    inputs = {
        name: _z3_to_python(model.eval(sym, model_completion=True))
        for name, sym in sym_params.items()
    }
    old_v = _z3_to_python(model.eval(out_old, model_completion=True))
    new_v = _z3_to_python(model.eval(out_new, model_completion=True))
    dist_v = _z3_to_python(model.eval(dist_expr, model_completion=True))
    return Example(inputs=inputs, old_output=old_v, new_output=new_v, distance=dist_v)


def _z3_to_python(val: z3.ExprRef) -> object:
    try:
        if z3.is_int_value(val):
            return val.as_long()
        if z3.is_rational_value(val):
            frac = val.as_fraction()
            f = float(frac)
            return int(f) if f == int(f) else f
        if z3.is_true(val):
            return True
        if z3.is_false(val):
            return False
    except Exception:  # noqa: BLE001
        pass
    return str(val)


def _simplify_str(expr: z3.ExprRef) -> str:
    try:
        return str(z3.simplify(expr))
    except Exception:  # noqa: BLE001
        return str(expr)
