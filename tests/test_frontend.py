"""Tests for the Python → IR frontend."""

import pytest
from distancetool.frontend.python_parser import parse_function, ParseError
from distancetool.ir.types import INT, FLOAT, BOOL
from distancetool.ir.terms import IntLit, BinOp, IfExpr, Let, Var


# --------------------------------------------------------------------------- #
# Basic parsing                                                                 #
# --------------------------------------------------------------------------- #

def test_simple_return():
    src = "def f(x: int) -> int:\n    return x"
    func = parse_function(src, "f")
    assert func.name == "f"
    assert func.params == [("x", INT)]
    assert func.return_type is INT
    assert isinstance(func.body, Var)
    assert func.body.name == "x"


def test_arithmetic():
    src = "def f(x: int, y: int) -> int:\n    return x + y * 2"
    func = parse_function(src, "f")
    body = func.body
    assert isinstance(body, BinOp)
    assert body.op == "add"


def test_float_params():
    src = "def f(x: float) -> float:\n    return x * 2.5"
    func = parse_function(src, "f")
    assert func.params == [("x", FLOAT)]
    body = func.body
    assert isinstance(body, BinOp)
    assert body.op == "mul"
    assert body.type is FLOAT


def test_bool_return():
    src = "def f(x: int) -> bool:\n    return x > 0"
    func = parse_function(src, "f")
    assert func.return_type is BOOL
    assert isinstance(func.body, BinOp)
    assert func.body.op == "gt"


def test_if_expression():
    src = "def f(x: int) -> int:\n    return x * 2 if x > 0 else x"
    func = parse_function(src, "f")
    assert isinstance(func.body, IfExpr)


def test_if_statement():
    src = """\
def f(x: int) -> int:
    if x > 0:
        return x * 2
    return x
"""
    func = parse_function(src, "f")
    assert isinstance(func.body, IfExpr)


def test_assignment_becomes_let():
    src = """\
def f(x: int) -> int:
    y = x + 1
    return y
"""
    func = parse_function(src, "f")
    assert isinstance(func.body, Let)
    assert func.body.name == "y"


def test_augmented_assignment():
    src = """\
def f(x: int) -> int:
    y = x
    y += 1
    return y
"""
    func = parse_function(src, "f")
    assert isinstance(func.body, Let)


def test_function_not_found():
    with pytest.raises(ParseError, match="not found"):
        parse_function("def g(x: int) -> int:\n    return x", "f")


def test_missing_return():
    with pytest.raises(ParseError):
        parse_function("def f(x: int) -> int:\n    y = x + 1", "f")


def test_nested_if():
    src = """\
def f(x: int) -> int:
    if x > 10:
        return x - 10
    elif x > 0:
        return x
    else:
        return 0
"""
    func = parse_function(src, "f")
    assert isinstance(func.body, IfExpr)
