"""Tests for the core IR type and term constructors."""

import pytest
from distancetool.ir.types import INT, FLOAT, BOOL, IntType, FloatType, BoolType, annotation_to_ir
from distancetool.ir.terms import IntLit, FloatLit, BoolLit, BinOp, UnaryOp, IfExpr, Let, Var


def test_type_singletons():
    assert IntType() == INT
    assert FloatType() == FLOAT
    assert BoolType() == BOOL


def test_annotation_to_ir():
    import ast
    assert annotation_to_ir(None) is INT
    assert annotation_to_ir(ast.parse("int", mode="eval").body) is INT
    assert annotation_to_ir(ast.parse("float", mode="eval").body) is FLOAT
    assert annotation_to_ir(ast.parse("bool", mode="eval").body) is BOOL


def test_int_lit():
    t = IntLit(42)
    assert t.value == 42
    assert t.type is INT


def test_binop_type():
    left = IntLit(1)
    right = IntLit(2)
    node = BinOp(op="add", left=left, right=right, type=INT)
    assert node.type is INT


def test_if_expr():
    cond = BoolLit(True)
    then_ = IntLit(1)
    else_ = IntLit(0)
    expr = IfExpr(condition=cond, then_branch=then_, else_branch=else_, type=INT)
    assert expr.type is INT


def test_let_nesting():
    # let x = 1 in let y = 2 in x + y
    inner = Let(
        name="y",
        value=IntLit(2),
        body=BinOp("add", Var("x", INT), Var("y", INT), INT),
        type=INT,
    )
    outer = Let(name="x", value=IntLit(1), body=inner, type=INT)
    assert outer.type is INT
