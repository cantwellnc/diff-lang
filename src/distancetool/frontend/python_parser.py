"""
Translate a subset of Python functions into the core IR.

Supported:
  - Parameters with int / float / bool type annotations (defaults to int)
  - Integer and float literals, bool literals
  - Arithmetic: +  -  *  //  /  %
  - Comparisons: ==  !=  <  <=  >  >=
  - Boolean logic: and  or  not
  - Conditional expressions: a if cond else b
  - if / elif / else statements (translated via continuation-passing)
  - Simple assignments and augmented assignments (x += e, etc.)
  - return statements
  - Nested Let-bindings for sequential assignments

Not supported in v0:
  - Loops (for / while)
  - Function calls (other than the function itself)
  - List / dict / tuple literals
  - Exception handling
"""

from __future__ import annotations
import ast
import textwrap
from typing import Dict, List, Tuple

from ..ir.types import IRType, INT, FLOAT, BOOL, FloatType, annotation_to_ir, is_numeric
from ..ir.terms import (
    IRTerm, Var, IntLit, FloatLit, BoolLit,
    BinOp, UnaryOp, IfExpr, Let, FuncDef,
)


class ParseError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Main entry                                                                    #
# --------------------------------------------------------------------------- #

def parse_function(source: str, func_name: str) -> FuncDef:
    """
    Parse *source* (a Python source file or snippet) and return the IR
    representation of the function named *func_name*.
    """
    source = textwrap.dedent(source)
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ParseError(f"Python syntax error: {e}") from e

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return _translate_funcdef(node)

    raise ParseError(f"Function '{func_name}' not found in source")


# --------------------------------------------------------------------------- #
# Function definition                                                           #
# --------------------------------------------------------------------------- #

def _translate_funcdef(node: ast.FunctionDef) -> FuncDef:
    env: Dict[str, IRType] = {}
    params: List[Tuple[str, IRType]] = []

    for arg in node.args.args:
        typ = annotation_to_ir(arg.annotation)
        params.append((arg.arg, typ))
        env[arg.arg] = typ

    return_type = annotation_to_ir(node.returns)
    body = _translate_stmts(node.body, env)

    return FuncDef(name=node.name, params=params, body=body, return_type=return_type)


# --------------------------------------------------------------------------- #
# Statement list → single IR term (continuation-passing)                       #
# --------------------------------------------------------------------------- #

def _translate_stmts(stmts: list, env: Dict[str, IRType]) -> IRTerm:
    if not stmts:
        raise ParseError("Reached end of function without a return statement")

    stmt = stmts[0]
    rest = stmts[1:]

    # ── return ──────────────────────────────────────────────────────────────
    if isinstance(stmt, ast.Return):
        if stmt.value is None:
            raise ParseError("return without value is not supported")
        return _translate_expr(stmt.value, env)

    # ── simple assignment  x = expr ─────────────────────────────────────────
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            raise ParseError("Only simple single-target assignments are supported")
        name = stmt.targets[0].id
        value = _translate_expr(stmt.value, env)
        new_env = {**env, name: value.type}
        body = _translate_stmts(rest, new_env)
        return Let(name=name, value=value, body=body, type=body.type)

    # ── augmented assignment  x op= expr ────────────────────────────────────
    if isinstance(stmt, ast.AugAssign):
        if not isinstance(stmt.target, ast.Name):
            raise ParseError("Only simple augmented assignments are supported")
        name = stmt.target.id
        if name not in env:
            raise ParseError(f"Augmented assignment to undefined variable '{name}'")
        old_var = Var(name=name, type=env[name])
        delta = _translate_expr(stmt.value, env)
        op, result_type = _binop_from_ast(stmt.op, old_var.type, delta.type)
        new_val = BinOp(op=op, left=old_var, right=delta, type=result_type)
        new_env = {**env, name: result_type}
        body = _translate_stmts(rest, new_env)
        return Let(name=name, value=new_val, body=body, type=body.type)

    # ── if / elif / else ────────────────────────────────────────────────────
    if isinstance(stmt, ast.If):
        return _translate_if_stmt(stmt, rest, env)

    # Standalone expression statements — only docstrings (string constants) are
    # silently skipped; any other bare expression is unsupported in v0.
    if isinstance(stmt, ast.Expr):
        if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            return _translate_stmts(rest, env)
        raise ParseError(
            f"Bare expression statement at line {getattr(stmt, 'lineno', '?')} is not supported in v0"
        )

    raise ParseError(
        f"Unsupported statement type '{type(stmt).__name__}' at line {getattr(stmt, 'lineno', '?')}. "
        "v0 supports: assignments, augmented assignments, if/else, return."
    )


# --------------------------------------------------------------------------- #
# if statement                                                                  #
# --------------------------------------------------------------------------- #

def _translate_if_stmt(stmt: ast.If, rest: list, env: Dict[str, IRType]) -> IRTerm:
    cond = _translate_expr(stmt.test, env)

    # If a branch ends with an unconditional return we don't append `rest`.
    then_stmts = stmt.body + ([] if _has_unconditional_return(stmt.body) else rest)
    else_stmts = (
        (stmt.orelse + ([] if _has_unconditional_return(stmt.orelse) else rest))
        if stmt.orelse
        else rest
    )

    then_branch = _translate_stmts(then_stmts, env)
    else_branch = _translate_stmts(else_stmts, env)

    return IfExpr(
        condition=cond,
        then_branch=then_branch,
        else_branch=else_branch,
        type=then_branch.type,
    )


def _has_unconditional_return(stmts: list) -> bool:
    """True if every execution path through stmts hits a return."""
    if not stmts:
        return False
    last = stmts[-1]
    if isinstance(last, ast.Return):
        return True
    if isinstance(last, ast.If):
        return (
            _has_unconditional_return(last.body)
            and bool(last.orelse)
            and _has_unconditional_return(last.orelse)
        )
    return False


# --------------------------------------------------------------------------- #
# Expressions                                                                   #
# --------------------------------------------------------------------------- #

def _translate_expr(node: ast.expr, env: Dict[str, IRType]) -> IRTerm:
    # ── literals ────────────────────────────────────────────────────────────
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return BoolLit(value=v, type=BOOL)
        if isinstance(v, int):
            return IntLit(value=v, type=INT)
        if isinstance(v, float):
            return FloatLit(value=v, type=FLOAT)
        raise ParseError(f"Unsupported literal type: {type(v).__name__}")

    # ── variable reference ──────────────────────────────────────────────────
    if isinstance(node, ast.Name):
        if node.id == "True":
            return BoolLit(True, BOOL)
        if node.id == "False":
            return BoolLit(False, BOOL)
        typ = env.get(node.id)
        if typ is None:
            raise ParseError(f"Undefined variable '{node.id}'")
        return Var(name=node.id, type=typ)

    # ── binary arithmetic / comparison ──────────────────────────────────────
    if isinstance(node, ast.BinOp):
        left = _translate_expr(node.left, env)
        right = _translate_expr(node.right, env)
        op, result_type = _binop_from_ast(node.op, left.type, right.type)
        return BinOp(op=op, left=left, right=right, type=result_type)

    # ── unary ────────────────────────────────────────────────────────────────
    if isinstance(node, ast.UnaryOp):
        operand = _translate_expr(node.operand, env)
        if isinstance(node.op, ast.Not):
            return UnaryOp(op="not", operand=operand, type=BOOL)
        if isinstance(node.op, ast.USub):
            return UnaryOp(op="neg", operand=operand, type=operand.type)
        if isinstance(node.op, ast.UAdd):
            return operand
        raise ParseError(f"Unsupported unary operator: {type(node.op).__name__}")

    # ── comparison ──────────────────────────────────────────────────────────
    if isinstance(node, ast.Compare):
        return _translate_compare(node, env)

    # ── boolean  and / or ───────────────────────────────────────────────────
    if isinstance(node, ast.BoolOp):
        op = "and" if isinstance(node.op, ast.And) else "or"
        terms = [_translate_expr(v, env) for v in node.values]
        result = terms[0]
        for t in terms[1:]:
            result = BinOp(op=op, left=result, right=t, type=BOOL)
        return result

    # ── inline if (ternary) ──────────────────────────────────────────────────
    if isinstance(node, ast.IfExp):
        cond = _translate_expr(node.test, env)
        then_ = _translate_expr(node.body, env)
        else_ = _translate_expr(node.orelse, env)
        return IfExpr(condition=cond, then_branch=then_, else_branch=else_, type=then_.type)

    raise ParseError(
        f"Unsupported expression type '{type(node).__name__}' at line {getattr(node, 'lineno', '?')}. "
        "v0 supports: literals, variables, arithmetic, comparisons, boolean ops, ternary if."
    )


def _translate_compare(node: ast.Compare, env: Dict[str, IRType]) -> IRTerm:
    if len(node.ops) != 1:
        raise ParseError("Chained comparisons (a < b < c) are not supported in v0")
    left = _translate_expr(node.left, env)
    right = _translate_expr(node.comparators[0], env)
    op_map = {
        ast.Eq: "eq", ast.NotEq: "ne",
        ast.Lt: "lt", ast.LtE: "le",
        ast.Gt: "gt", ast.GtE: "ge",
    }
    for cls, name in op_map.items():
        if isinstance(node.ops[0], cls):
            return BinOp(op=name, left=left, right=right, type=BOOL)
    raise ParseError(f"Unsupported comparison operator: {type(node.ops[0]).__name__}")


# --------------------------------------------------------------------------- #
# Operator helpers                                                              #
# --------------------------------------------------------------------------- #

_AST_ARITH = {
    ast.Add: "add",
    ast.Sub: "sub",
    ast.Mult: "mul",
    ast.Div: "div",
    ast.FloorDiv: "floordiv",
    ast.Mod: "mod",
}


def _binop_from_ast(op: ast.operator, ltype: IRType, rtype: IRType) -> Tuple[str, IRType]:
    for cls, name in _AST_ARITH.items():
        if isinstance(op, cls):
            # Division always produces float; floor-div preserves int
            if isinstance(op, ast.Div):
                result_type = FLOAT
            elif isinstance(ltype, FloatType) or isinstance(rtype, FloatType):
                result_type = FLOAT
            else:
                result_type = ltype
            return name, result_type
    raise ParseError(f"Unsupported binary operator: {type(op).__name__}")
