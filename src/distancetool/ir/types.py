from __future__ import annotations
import ast
from dataclasses import dataclass


class IRType:
    pass


@dataclass(frozen=True)
class IntType(IRType):
    def __str__(self): return "Int"
    def __repr__(self): return "Int"


@dataclass(frozen=True)
class FloatType(IRType):
    def __str__(self): return "Float"
    def __repr__(self): return "Float"


@dataclass(frozen=True)
class BoolType(IRType):
    def __str__(self): return "Bool"
    def __repr__(self): return "Bool"


@dataclass(frozen=True)
class ProductType(IRType):
    left: IRType
    right: IRType
    def __str__(self): return f"({self.left} × {self.right})"


@dataclass(frozen=True)
class FunctionType(IRType):
    domain: IRType
    codomain: IRType
    def __str__(self): return f"({self.domain} → {self.codomain})"


@dataclass(frozen=True)
class ListType(IRType):
    elem: IRType
    def __str__(self): return f"List({self.elem})"


INT = IntType()
FLOAT = FloatType()
BOOL = BoolType()


def annotation_to_ir(annotation: ast.expr | None) -> IRType:
    if annotation is None:
        return INT
    if isinstance(annotation, ast.Name):
        return {"int": INT, "float": FLOAT, "bool": BOOL}.get(annotation.id, INT)
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return {"int": INT, "float": FLOAT, "bool": BOOL}.get(annotation.value, INT)
    return INT


def is_numeric(t: IRType) -> bool:
    return isinstance(t, (IntType, FloatType))
