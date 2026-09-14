"""
End-to-end tests for the Z3 encoder and differencer.

Each test exercises a recognisable pattern:
  - provably equivalent programs → DiffResult.equivalent == True
  - programs that differ everywhere → counterexamples found
  - programs that differ conditionally → agree_example found
"""

import pytest
from distancetool.frontend.python_parser import parse_function
from distancetool.engine.differencer import compute_diff
from distancetool.engine.z3_encoder import Z3Encoder


# --------------------------------------------------------------------------- #
# Z3 encoder unit tests                                                        #
# --------------------------------------------------------------------------- #

def _encode(src: str, func_name: str):
    func = parse_function(src, func_name)
    enc = Z3Encoder()
    sym_params = enc.setup_params(func)
    out = enc.encode(func.body)
    return sym_params, out


def test_encoder_constant():
    _, out = _encode("def f(x: int) -> int:\n    return 42", "f")
    import z3
    assert z3.is_int_value(z3.simplify(out))
    assert z3.simplify(out).as_long() == 42


def test_encoder_add():
    src = "def f(x: int, y: int) -> int:\n    return x + y"
    sym_params, out = _encode(src, "f")
    import z3
    x, y = sym_params["x"], sym_params["y"]
    s = z3.Solver()
    s.add(x == 3, y == 4)
    assert s.check() == z3.sat
    model = s.model()
    val = model.eval(out).as_long()
    assert val == 7


def test_encoder_conditional():
    src = "def f(x: int) -> int:\n    return x * 2 if x > 0 else x"
    sym_params, out = _encode(src, "f")
    import z3
    x = sym_params["x"]
    s = z3.Solver()
    s.add(x == 5)
    model = s.model() if s.check() == z3.sat else None
    assert model is not None
    val = model.eval(out).as_long()
    assert val == 10


# --------------------------------------------------------------------------- #
# Differencer: equivalent programs                                              #
# --------------------------------------------------------------------------- #

def test_equivalent_identity():
    src = "def f(x: int) -> int:\n    return x"
    f_old = parse_function(src, "f")
    f_new = parse_function(src, "f")
    result = compute_diff(f_old, f_new)
    assert result.equivalent
    assert result.error is None


def test_equivalent_refactored():
    """Commutativity: x + y  ≡  y + x."""
    old = "def f(x: int, y: int) -> int:\n    return x + y"
    new = "def f(x: int, y: int) -> int:\n    return y + x"
    f_old = parse_function(old, "f")
    f_new = parse_function(new, "f")
    result = compute_diff(f_old, f_new)
    assert result.equivalent


def test_equivalent_let_vs_inline():
    """Assignment then return  ≡  direct return."""
    old = "def f(x: int) -> int:\n    y = x + 1\n    return y"
    new = "def f(x: int) -> int:\n    return x + 1"
    result = compute_diff(parse_function(old, "f"), parse_function(new, "f"))
    assert result.equivalent


# --------------------------------------------------------------------------- #
# Differencer: programs that always differ                                      #
# --------------------------------------------------------------------------- #

def test_constant_diff():
    """return x + 1  vs  return x + 2  — always differ by 1."""
    old = "def f(x: int) -> int:\n    return x + 1"
    new = "def f(x: int) -> int:\n    return x + 2"
    result = compute_diff(parse_function(old, "f"), parse_function(new, "f"))
    assert not result.equivalent
    assert result.counterexamples
    # Every counterexample should have distance 1
    for ex in result.counterexamples:
        assert ex.distance == 1
    # No agree example should exist
    assert result.agree_example is None


def test_multiply_diff():
    """return x * 2  vs  return x * 3 — differ when x ≠ 0."""
    old = "def f(x: int) -> int:\n    return x * 2"
    new = "def f(x: int) -> int:\n    return x * 3"
    result = compute_diff(parse_function(old, "f"), parse_function(new, "f"))
    assert not result.equivalent
    assert result.counterexamples
    # x == 0 is a point where they agree
    assert result.agree_example is not None
    assert result.agree_example.inputs["x"] == 0


# --------------------------------------------------------------------------- #
# Differencer: conditionally different                                          #
# --------------------------------------------------------------------------- #

def test_conditional_diff():
    """
    Old: if x > 0: return x * 2 else return x
    New: if x > 0: return x * 3 else return x
    → differ only when x > 0.
    """
    old = """\
def f(x: int) -> int:
    if x > 0:
        return x * 2
    return x
"""
    new = """\
def f(x: int) -> int:
    if x > 0:
        return x * 3
    return x
"""
    result = compute_diff(parse_function(old, "f"), parse_function(new, "f"))
    assert not result.equivalent
    assert result.counterexamples
    # All counterexamples must have x > 0
    for ex in result.counterexamples:
        assert ex.inputs["x"] > 0
    # There must be agree examples (x <= 0)
    assert result.agree_example is not None
    assert result.agree_example.inputs["x"] <= 0


def test_off_by_one_threshold():
    """
    Old: return x + 1 if x > 10 else 0
    New: return x + 1 if x >= 10 else 0
    → differ only at x == 10 (old returns 0, new returns 11).

    Note: return x - 10 if x > 10 else 0  vs  x >= 10 are *equivalent*
    because at x==10 both return 0 (10-10 == the else branch).
    """
    old = "def f(x: int) -> int:\n    return x + 1 if x > 10 else 0"
    new = "def f(x: int) -> int:\n    return x + 1 if x >= 10 else 0"
    result = compute_diff(parse_function(old, "f"), parse_function(new, "f"))
    assert not result.equivalent
    assert result.counterexamples
    # The only differing point is x == 10
    for ex in result.counterexamples:
        assert ex.inputs["x"] == 10
    assert result.agree_example is not None


# --------------------------------------------------------------------------- #
# Differencer: boolean outputs                                                  #
# --------------------------------------------------------------------------- #

def test_bool_equivalent():
    old = "def f(x: int) -> bool:\n    return x > 0"
    new = "def f(x: int) -> bool:\n    return not x <= 0"
    result = compute_diff(parse_function(old, "f"), parse_function(new, "f"))
    assert result.equivalent


def test_bool_differ():
    old = "def f(x: int) -> bool:\n    return x > 0"
    new = "def f(x: int) -> bool:\n    return x >= 0"
    result = compute_diff(parse_function(old, "f"), parse_function(new, "f"))
    assert not result.equivalent
    # Differ only at x == 0
    for ex in result.counterexamples:
        assert ex.inputs["x"] == 0


# --------------------------------------------------------------------------- #
# Real-world-ish example: fee calculation                                       #
# --------------------------------------------------------------------------- #

def test_fee_calculation():
    """
    Old policy: flat 5 % fee.
    New policy: 5 % fee, but waived when amount <= 100.
    """
    old = """\
def compute_fee(amount: int) -> int:
    return amount // 20
"""
    new = """\
def compute_fee(amount: int) -> int:
    if amount <= 100:
        return 0
    return amount // 20
"""
    result = compute_diff(parse_function(old, "compute_fee"), parse_function(new, "compute_fee"))
    assert not result.equivalent
    # All differences occur when amount <= 100 (new always returns 0 there;
    # old returns amount//20 which is non-zero for |amount| >= 20).
    for ex in result.counterexamples:
        assert ex.inputs["amount"] <= 100
        # old fee must differ from 0 — either positive or negative (floor div)
        assert ex.old_output != 0
