"""
Two-stage expression readability pipeline:

  Stage 1 — tactic pass
    For Boolean expressions: run Z3's ctx-solver-simplify (which can collapse
    nested If-then-else trees into compact predicates by reasoning about the
    arithmetic inside them).  Gated by a wall-clock timeout implemented via
    ThreadPoolExecutor; if the tactic doesn't finish in time the stage is
    skipped and we fall back to plain z3.simplify().

    For arithmetic expressions: z3.simplify() with arith_lhs=True and
    pull_cheap_ite=True (tactics don't operate directly on non-Bool terms).

  Stage 2 — pretty-printer
    Walk the (possibly simplified) Z3 AST and emit human-friendly text:
      - Literal-on-left comparisons are flipped:  100 <= x  →  x >= 100
      - Not(a == b)     →  a != b
      - Not(a <= b)     →  a > b   (and similar for all comparisons)
      - -1 * x inside a sum  →  shown as  - x  (so  a + -1*b  →  a - b)
      - If(d >= 0, d, -d)  →  |d|
      - k * 1  collapses to  k;  1 * x  collapses to  x
      - Short If expressions stay on one line; long ones get indented
"""

from __future__ import annotations

import concurrent.futures
from typing import Optional

import z3


TACTIC_DEFAULT_TIMEOUT_MS = 2_000


# --------------------------------------------------------------------------- #
# Public API                                                                    #
# --------------------------------------------------------------------------- #

def simplify_and_pretty(
    expr: z3.ExprRef,
    tactic_timeout_ms: int = TACTIC_DEFAULT_TIMEOUT_MS,
) -> str:
    """Tactic pass → pretty-print.  Always returns a non-empty string."""
    simplified = tactic_simplify(expr, tactic_timeout_ms)
    return pretty(simplified)


def tactic_simplify(
    expr: z3.ExprRef,
    timeout_ms: int = TACTIC_DEFAULT_TIMEOUT_MS,
) -> z3.ExprRef:
    """
    Apply Z3 tactics to *expr* with a hard wall-clock timeout.

    Boolean: simplify → ctx-solver-simplify.
    Arithmetic: z3.simplify() with arith_lhs + pull_cheap_ite options.

    Falls back to z3.simplify() on timeout or any Z3Exception.
    """
    if not z3.is_bool(expr):
        return z3.simplify(expr, arith_lhs=True, pull_cheap_ite=True)

    def _run() -> z3.ExprRef:
        goal = z3.Goal()
        goal.add(expr)
        t = z3.Then(
            z3.Tactic("simplify"),
            z3.With(z3.Tactic("ctx-solver-simplify"), timeout=timeout_ms),
        )
        result = t(goal)
        if not result or len(result[0]) == 0:
            return z3.BoolVal(True)
        sub = result[0]
        if len(sub) == 1:
            return sub[0]
        return z3.And(*[sub[i] for i in range(len(sub))])

    # ThreadPoolExecutor gives us a clean wall-clock timeout.  Since Z3's
    # default context is not thread-safe for concurrent access we run the
    # tactic call in the worker while the main thread blocks on .result().
    # max_workers=1 guarantees at most one Z3 call is in-flight at a time.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run)
        try:
            # Small grace period so the worker can finish its current Z3 op
            return future.result(timeout=timeout_ms / 1000 + 0.5)
        except (concurrent.futures.TimeoutError, Exception):
            return z3.simplify(expr)


def pretty(expr: z3.ExprRef) -> str:
    """
    Pretty-print a Z3 expression as human-readable text.
    See module docstring for the full list of transformations.
    """
    return _pp(expr, prec=0)


# --------------------------------------------------------------------------- #
# Operator precedence constants                                                 #
# --------------------------------------------------------------------------- #

_PREC_OR  = 1
_PREC_AND = 2
_PREC_CMP = 3
_PREC_ADD = 4
_PREC_MUL = 5
_PREC_NEG = 7


# --------------------------------------------------------------------------- #
# Recursive pretty-printer                                                      #
# --------------------------------------------------------------------------- #

def _pp(expr: z3.ExprRef, prec: int = 0) -> str:
    # ── ground values ────────────────────────────────────────────────────────
    if z3.is_true(expr):  return "True"
    if z3.is_false(expr): return "False"
    if z3.is_int_value(expr): return str(expr.as_long())
    if z3.is_rational_value(expr):
        f = float(expr.as_fraction())
        return str(int(f) if f == int(f) else round(f, 6))

    # ── symbolic variable (leaf) ──────────────────────────────────────────────
    if z3.is_const(expr):
        return str(expr)

    if not z3.is_app(expr):
        return str(expr)   # fallback for quantifiers etc.

    name = expr.decl().name()
    n    = expr.num_args()
    args = [expr.arg(i) for i in range(n)]

    # ── absolute-value pattern ────────────────────────────────────────────────
    inner = _detect_abs(expr)
    if inner is not None:
        return f"|{_pp(inner)}|"

    # ── if-then-else ─────────────────────────────────────────────────────────
    if name == "if":
        c = _pp(args[0])
        t = _pp(args[1])
        e = _pp(args[2])
        one_liner = f"If({c}, {t}, {e})"
        if len(one_liner) <= 72:
            return one_liner
        return f"If({c},\n   {t},\n   {e})"

    # ── not ──────────────────────────────────────────────────────────────────
    if name == "not" and n == 1:
        inner = args[0]
        iname = inner.decl().name() if z3.is_app(inner) else ""
        iargs = [inner.arg(j) for j in range(inner.num_args())] if z3.is_app(inner) else []

        if iname == "=" and len(iargs) == 2:
            l = _pp(iargs[0], prec=_PREC_CMP)
            r = _pp(iargs[1], prec=_PREC_CMP)
            return f"{l} != {r}"

        _flip = {"<=": ">", "<": ">=", ">=": "<", ">": "<="}
        if iname in _flip and len(iargs) == 2:
            return _pp_cmp(_flip[iname], iargs[0], iargs[1])

        return f"not {_pp(inner, prec=_PREC_NEG)}"

    # ── and / or ─────────────────────────────────────────────────────────────
    if name == "and":
        parts = [_pp(a, prec=_PREC_AND + 1) for a in args]
        s = " and ".join(parts)
        return f"({s})" if prec > _PREC_AND else s

    if name == "or":
        parts = [_pp(a, prec=_PREC_OR + 1) for a in args]
        s = " or ".join(parts)
        return f"({s})" if prec > _PREC_OR else s

    # ── equality / distinct ──────────────────────────────────────────────────
    if name == "=" and n == 2:
        l = _pp(args[0], prec=_PREC_CMP)
        r = _pp(args[1], prec=_PREC_CMP)
        return f"{l} == {r}"
    if name == "distinct" and n == 2:
        l = _pp(args[0], prec=_PREC_CMP)
        r = _pp(args[1], prec=_PREC_CMP)
        return f"{l} != {r}"

    # ── comparisons ──────────────────────────────────────────────────────────
    if name in ("<=", "<", ">=", ">") and n == 2:
        return _pp_cmp(name, args[0], args[1])

    # ── addition ─────────────────────────────────────────────────────────────
    if name == "+":
        return _pp_sum(args, prec)

    # ── multiplication ───────────────────────────────────────────────────────
    if name == "*":
        return _pp_product(args, prec)

    # ── unary minus ──────────────────────────────────────────────────────────
    if name == "-" and n == 1:
        return f"-{_pp(args[0], prec=_PREC_NEG)}"

    # ── binary minus ─────────────────────────────────────────────────────────
    if name == "-" and n == 2:
        l = _pp(args[0], prec=_PREC_ADD)
        r = _pp(args[1], prec=_PREC_ADD + 1)
        s = f"{l} - {r}"
        return f"({s})" if prec > _PREC_ADD else s

    # ── division ─────────────────────────────────────────────────────────────
    if name == "/" and n == 2:
        l = _pp(args[0], prec=_PREC_MUL)
        r = _pp(args[1], prec=_PREC_MUL + 1)
        return f"{l} / {r}"

    # ── fallback ─────────────────────────────────────────────────────────────
    return f"{name}({', '.join(_pp(a) for a in args)})"


# --------------------------------------------------------------------------- #
# Comparison helper                                                             #
# --------------------------------------------------------------------------- #

def _pp_cmp(op: str, left: z3.ExprRef, right: z3.ExprRef) -> str:
    """Emit a comparison; flip  literal op var  →  var flipped_op literal."""
    _flip = {"<=": ">=", "<": ">", ">=": "<=", ">": "<"}
    if _is_literal(left) and not _is_literal(right):
        left, right, op = right, left, _flip[op]
    return f"{_pp(left)} {op} {_pp(right)}"


def _is_literal(expr: z3.ExprRef) -> bool:
    return (
        z3.is_int_value(expr)
        or z3.is_rational_value(expr)
        or z3.is_true(expr)
        or z3.is_false(expr)
    )


# --------------------------------------------------------------------------- #
# Arithmetic helpers                                                            #
# --------------------------------------------------------------------------- #

def _pp_sum(args: list, prec: int) -> str:
    """Render a Z3 + node, turning -1*x addends into  - x."""
    positives: list[str] = []
    subtracted: list[str] = []

    for a in args:
        is_neg, inner = _extract_neg(a)
        if is_neg:
            subtracted.append(_pp(inner, prec=_PREC_ADD + 1))
        else:
            positives.append(_pp(a, prec=_PREC_ADD))

    if positives and subtracted:
        s = " + ".join(positives) + " - " + " - ".join(subtracted)
    elif positives:
        s = " + ".join(positives)
    else:
        s = "-" + " - ".join(subtracted)

    return f"({s})" if prec > _PREC_ADD else s


def _pp_product(args: list, prec: int) -> str:
    """Render a Z3 * node; collapse -1*x → -x and 1*x → x."""
    if len(args) == 2:
        is_neg, inner = _extract_neg_product(args)
        if is_neg and inner is not None:
            return f"-{_pp(inner, prec=_PREC_NEG)}"
        # k * x  where k is a literal
        if z3.is_int_value(args[0]):
            k = args[0].as_long()
            if k == 1:
                return _pp(args[1], prec=prec)
            return f"{k}*{_pp(args[1], prec=_PREC_MUL + 1)}"

    parts = [_pp(a, prec=_PREC_MUL + 1) for a in args]
    s = "*".join(parts)
    return f"({s})" if prec > _PREC_MUL else s


def _extract_neg(expr: z3.ExprRef) -> tuple[bool, z3.ExprRef]:
    """Return (True, inner) if expr is -1 * inner, else (False, expr)."""
    if z3.is_app(expr) and expr.decl().name() == "*" and expr.num_args() == 2:
        a0, a1 = expr.arg(0), expr.arg(1)
        if z3.is_int_value(a0) and a0.as_long() == -1:
            return True, a1
        if z3.is_int_value(a1) and a1.as_long() == -1:
            return True, a0
    return False, expr


def _extract_neg_product(args: list) -> tuple[bool, Optional[z3.ExprRef]]:
    """For a 2-element product arg list, detect -1 * x."""
    if len(args) != 2:
        return False, None
    if z3.is_int_value(args[0]) and args[0].as_long() == -1:
        return True, args[1]
    if z3.is_int_value(args[1]) and args[1].as_long() == -1:
        return True, args[0]
    return False, None


# --------------------------------------------------------------------------- #
# Absolute-value pattern detector                                               #
# --------------------------------------------------------------------------- #

def _detect_abs(expr: z3.ExprRef) -> Optional[z3.ExprRef]:
    """
    Detect  If(d >= 0, d, -d)  and return d, else None.

    Two Z3 normalisation issues to handle:
      1. Z3 rewrites  d >= 0  to  0 <= d  (decl name "<=" with literal on
         left), so both forms are accepted.
      2. After z3.simplify(), -(x-y) becomes y-x (binary minus), not -1*(x-y).
         So instead of structural matching on the else branch we check that
         then_ + else_ == 0 via z3.simplify(), which covers all equivalent
         representations.
    """
    if not (z3.is_app(expr) and expr.decl().name() == "if" and expr.num_args() == 3):
        return None

    cond, then_, else_ = expr.arg(0), expr.arg(1), expr.arg(2)

    # condition: d >= 0  stored as ">="  OR  0 <= d  stored as "<="
    if not (z3.is_app(cond) and cond.num_args() == 2):
        return None
    cname = cond.decl().name()
    c0, c1 = cond.arg(0), cond.arg(1)

    if cname == ">=" and z3.is_int_value(c1) and c1.as_long() == 0:
        d = c0
    elif cname == "<=" and z3.is_int_value(c0) and c0.as_long() == 0:
        d = c1
    else:
        return None

    # then branch must be d (structurally)
    if str(then_) != str(d):
        return None

    # else branch must be -d in any equivalent form; check  d + else_ == 0.
    try:
        if z3.is_true(z3.simplify(then_ + else_ == 0)):
            return d
    except z3.Z3Exception:
        pass

    return None
