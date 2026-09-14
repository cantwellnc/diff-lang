"""
Tests for the two-stage simplification pipeline:
  Stage 1 — tactic_simplify  (Z3 ctx-solver-simplify, timegated)
  Stage 2 — pretty            (AST-walking pretty-printer)
"""

import z3
import pytest
from distancetool.engine.simplifier import pretty, tactic_simplify, simplify_and_pretty


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def x(): return z3.Int("x")
def y(): return z3.Int("y")
def p(): return z3.Int("price")
def a(): return z3.Int("age")


# --------------------------------------------------------------------------- #
# pretty() — literal flipping                                                   #
# --------------------------------------------------------------------------- #

def test_flip_le():
    # 100 <= x  →  x >= 100
    assert pretty(z3.IntVal(100) <= x()) == "x >= 100"

def test_flip_lt():
    # 0 < x  →  x > 0
    assert pretty(z3.IntVal(0) < x()) == "x > 0"

def test_flip_ge():
    # 100 >= x  →  x <= 100
    assert pretty(z3.IntVal(100) >= x()) == "x <= 100"

def test_no_flip_when_var_left():
    # x <= 100  stays  x <= 100
    assert pretty(x() <= z3.IntVal(100)) == "x <= 100"

def test_no_flip_both_vars():
    # x <= y  stays  x <= y  (no literal, no flip)
    assert pretty(x() <= y()) == "x <= y"


# --------------------------------------------------------------------------- #
# pretty() — Not rewrites                                                       #
# --------------------------------------------------------------------------- #

def test_not_eq_becomes_ne():
    assert pretty(z3.Not(x() == y())) == "x != y"

def test_not_le_becomes_gt():
    assert pretty(z3.Not(x() <= z3.IntVal(5))) == "x > 5"

def test_not_lt_becomes_ge():
    assert pretty(z3.Not(x() < z3.IntVal(5))) == "x >= 5"

def test_not_ge_becomes_lt():
    assert pretty(z3.Not(x() >= z3.IntVal(0))) == "x < 0"

def test_not_gt_becomes_le():
    assert pretty(z3.Not(x() > z3.IntVal(10))) == "x <= 10"


# --------------------------------------------------------------------------- #
# pretty() — boolean connectives                                                #
# --------------------------------------------------------------------------- #

def test_and():
    expr = z3.And(x() > z3.IntVal(0), y() < z3.IntVal(10))
    assert pretty(expr) == "x > 0 and y < 10"

def test_or():
    expr = z3.Or(x() < z3.IntVal(0), x() > z3.IntVal(150))
    assert pretty(expr) == "x < 0 or x > 150"

def test_and_with_flipped_literal():
    # And(0 <= age, 150 >= age)  →  age >= 0 and age <= 150
    expr = z3.And(z3.IntVal(0) <= a(), z3.IntVal(150) >= a())
    assert pretty(expr) == "age >= 0 and age <= 150"


# --------------------------------------------------------------------------- #
# pretty() — arithmetic                                                         #
# --------------------------------------------------------------------------- #

def test_neg_coeff_in_sum():
    # x + (-1)*y  →  x - y
    expr = x() + z3.IntVal(-1) * y()
    assert pretty(expr) == "x - y"

def test_neg_unary():
    expr = -x()
    assert pretty(expr) == "-x"

def test_coefficient_k():
    # 3 * x
    expr = z3.IntVal(3) * x()
    assert pretty(expr) == "3*x"

def test_coefficient_1_collapses():
    # 1 * x  →  x
    expr = z3.IntVal(1) * x()
    assert pretty(expr) == "x"

def test_literals():
    assert pretty(z3.IntVal(42)) == "42"
    assert pretty(z3.IntVal(-7)) == "-7"
    assert pretty(z3.BoolVal(True)) == "True"
    assert pretty(z3.BoolVal(False)) == "False"


# --------------------------------------------------------------------------- #
# pretty() — absolute-value pattern                                             #
# --------------------------------------------------------------------------- #

def test_abs_pattern_with_neg_product():
    # If(x >= 0, x, -1*x)  →  |x|
    d = x()
    expr = z3.If(d >= z3.IntVal(0), d, z3.IntVal(-1) * d)
    assert pretty(expr) == "|x|"

def test_abs_pattern_with_unary_minus():
    # If(x >= 0, x, -x)  →  |x|
    d = x()
    expr = z3.If(d >= z3.IntVal(0), d, -d)
    assert pretty(expr) == "|x|"

def test_abs_pattern_compound_inner():
    # If(x - y >= 0, x - y, -(x - y))  →  |x - y|
    d = x() - y()
    expr = z3.If(d >= z3.IntVal(0), d, -d)
    result = pretty(expr)
    assert result.startswith("|") and result.endswith("|")

def test_non_abs_if():
    # If(x > 0, x, 0)  is NOT an abs pattern
    expr = z3.If(x() > z3.IntVal(0), x(), z3.IntVal(0))
    result = pretty(expr)
    assert not result.startswith("|")


# --------------------------------------------------------------------------- #
# tactic_simplify() — Boolean simplification                                   #
# --------------------------------------------------------------------------- #

def test_tactic_simplifies_obvious_tautology():
    # x >= 0 or x < 0  →  True
    expr = z3.Or(x() >= z3.IntVal(0), x() < z3.IntVal(0))
    result = tactic_simplify(expr, timeout_ms=3_000)
    assert z3.is_true(result)

def test_tactic_simplifies_obvious_contradiction():
    # x > 0 and x < 0  is unsatisfiable; the tactic should derive False
    # (or some equivalent that is itself unsatisfiable).
    expr = z3.And(x() > z3.IntVal(0), x() < z3.IntVal(0))
    result = tactic_simplify(expr, timeout_ms=3_000)
    # ctx-solver-simplify may not collapse all the way to the literal False,
    # but the result must be semantically equivalent to False (unsat).
    s = z3.Solver()
    s.add(result)
    assert s.check() == z3.unsat

def test_tactic_timeout_falls_back():
    # A trivially-satisfiable expression shouldn't explode even at 1ms timeout
    expr = x() > z3.IntVal(0)
    result = tactic_simplify(expr, timeout_ms=1)
    # Should not raise; result is some valid Z3 expression
    assert isinstance(result, z3.ExprRef)

def test_tactic_arithmetic_passthrough():
    # Non-bool: just z3.simplify(), should not raise
    expr = x() + y() - x()
    result = tactic_simplify(expr, timeout_ms=1_000)
    assert isinstance(result, z3.ExprRef)


# --------------------------------------------------------------------------- #
# tactic_simplify() — off-by-one discount case                                 #
# --------------------------------------------------------------------------- #

def test_tactic_discount_diff_condition():
    """
    The discount example (> 100 vs >= 100) has a diff condition that is
    equivalent to  price == 100.  ctx-solver-simplify should collapse it.
    """
    price = p()
    out_old = z3.If(price <= z3.IntVal(100), price, price - z3.IntVal(10))
    out_new = z3.If(price >= z3.IntVal(100), price - z3.IntVal(10), price)
    diff_cond = out_old != out_new

    result = tactic_simplify(diff_cond, timeout_ms=3_000)
    result_str = pretty(result)
    # Should collapse to  price == 100  (or the negation form)
    assert "100" in result_str
    # And it should be much shorter than the raw Z3 string
    assert len(result_str) < len(str(z3.simplify(diff_cond)))


# --------------------------------------------------------------------------- #
# simplify_and_pretty() — end-to-end                                           #
# --------------------------------------------------------------------------- #

def test_end_to_end_simple_diff():
    # x + 1  vs  x + 2  → diff_cond is always True (they always differ)
    diff_cond = (x() + z3.IntVal(1)) != (x() + z3.IntVal(2))
    result = simplify_and_pretty(diff_cond)
    assert result == "True"

def test_end_to_end_abs():
    # |x - y|
    d = x() - y()
    dist = z3.If(d >= z3.IntVal(0), d, z3.IntVal(-1) * d)
    result = simplify_and_pretty(dist)
    assert result == "|x - y|"
