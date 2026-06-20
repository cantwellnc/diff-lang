"""
Encode IR terms as Z3 expressions for symbolic execution.

Each variable in `env` holds a Z3 expression (not a fresh Z3 variable per
Let-binding).  Let-bindings are handled by substitution: we evaluate the
bound expression, store it under the name, evaluate the body, then restore
the previous binding.  This keeps everything in one flat Z3 expression and
avoids the need for universally-quantified formulas.
"""

from __future__ import annotations
import z3
from typing import Dict

from ..ir.types import IRType, IntType, FloatType, BoolType
from ..ir.terms import (
    IRTerm, Var, IntLit, FloatLit, BoolLit,
    BinOp, UnaryOp, IfExpr, Let, FuncDef,
)


class EncoderError(Exception):
    pass


class Z3Encoder:
    def __init__(self) -> None:
        self.env: Dict[str, z3.ExprRef] = {}

    # ------------------------------------------------------------------ #
    # Public helpers                                                        #
    # ------------------------------------------------------------------ #

    def fresh_symbolic(self, name: str, typ: IRType) -> z3.ExprRef:
        if isinstance(typ, IntType):
            return z3.Int(name)
        if isinstance(typ, FloatType):
            return z3.Real(name)
        if isinstance(typ, BoolType):
            return z3.Bool(name)
        raise EncoderError(f"Cannot create symbolic variable for type {typ}")

    def setup_params(self, func: FuncDef) -> Dict[str, z3.ExprRef]:
        """
        Populate self.env with fresh symbolic variables for each parameter
        and return the mapping {param_name: z3_var}.
        """
        self.env = {}
        sym_params: Dict[str, z3.ExprRef] = {}
        for name, typ in func.params:
            sym = self.fresh_symbolic(name, typ)
            self.env[name] = sym
            sym_params[name] = sym
        return sym_params

    def encode(self, term: IRTerm) -> z3.ExprRef:
        if isinstance(term, Var):
            if term.name not in self.env:
                raise EncoderError(f"Unbound variable '{term.name}'")
            return self.env[term.name]

        if isinstance(term, IntLit):
            return z3.IntVal(term.value)

        if isinstance(term, FloatLit):
            return z3.RealVal(term.value)

        if isinstance(term, BoolLit):
            return z3.BoolVal(term.value)

        if isinstance(term, BinOp):
            return self._encode_binop(term)

        if isinstance(term, UnaryOp):
            operand = self.encode(term.operand)
            if term.op == "neg":
                return -operand
            if term.op == "not":
                return z3.Not(operand)
            raise EncoderError(f"Unknown unary op '{term.op}'")

        if isinstance(term, IfExpr):
            cond = self.encode(term.condition)
            then_ = self.encode(term.then_branch)
            else_ = self.encode(term.else_branch)
            return z3.If(cond, then_, else_)

        if isinstance(term, Let):
            val = self.encode(term.value)
            previous = self.env.get(term.name)
            self.env[term.name] = val
            result = self.encode(term.body)
            if previous is not None:
                self.env[term.name] = previous
            else:
                del self.env[term.name]
            return result

        raise EncoderError(f"Cannot encode term of type {type(term).__name__}")

    # ------------------------------------------------------------------ #
    # Binary operators                                                      #
    # ------------------------------------------------------------------ #

    def _encode_binop(self, term: BinOp) -> z3.ExprRef:
        left = self.encode(term.left)
        right = self.encode(term.right)
        op = term.op

        if op == "add":     return left + right
        if op == "sub":     return left - right
        if op == "mul":     return left * right
        if op == "div":     return left / right
        if op == "floordiv": return left / right   # Z3 Int division truncates toward zero
        if op == "mod":     return left % right
        if op == "eq":      return left == right
        if op == "ne":      return left != right
        if op == "lt":      return left < right
        if op == "le":      return left <= right
        if op == "gt":      return left > right
        if op == "ge":      return left >= right
        if op == "and":     return z3.And(left, right)
        if op == "or":      return z3.Or(left, right)

        raise EncoderError(f"Unknown binary op '{op}'")
