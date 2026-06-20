from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple
from .types import IRType, INT, FLOAT, BOOL


class IRTerm:
    type: IRType


@dataclass
class Var(IRTerm):
    name: str
    type: IRType


@dataclass
class IntLit(IRTerm):
    value: int
    type: IRType = field(default_factory=lambda: INT)


@dataclass
class FloatLit(IRTerm):
    value: float
    type: IRType = field(default_factory=lambda: FLOAT)


@dataclass
class BoolLit(IRTerm):
    value: bool
    type: IRType = field(default_factory=lambda: BOOL)


@dataclass
class BinOp(IRTerm):
    """
    op ∈ {add, sub, mul, div, floordiv, mod,
           eq, ne, lt, le, gt, ge, and, or}
    """
    op: str
    left: IRTerm
    right: IRTerm
    type: IRType


@dataclass
class UnaryOp(IRTerm):
    """op ∈ {neg, not}"""
    op: str
    operand: IRTerm
    type: IRType


@dataclass
class IfExpr(IRTerm):
    condition: IRTerm
    then_branch: IRTerm
    else_branch: IRTerm
    type: IRType


@dataclass
class Let(IRTerm):
    """let name = value in body"""
    name: str
    value: IRTerm
    body: IRTerm
    type: IRType


@dataclass
class FuncDef:
    name: str
    params: List[Tuple[str, IRType]]
    body: IRTerm
    return_type: IRType
