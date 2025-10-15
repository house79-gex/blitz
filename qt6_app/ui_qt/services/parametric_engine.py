from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import ast
import math

# Valutatore sicuro per formule (solo aritmetica/funzioni whitelisted)
_ALLOWED_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Load, ast.Name, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
    ast.Compare, ast.Eq, ast.NotEq, ast.Gt, ast.GtE, ast.Lt, ast.LtE,
    ast.BoolOp, ast.And, ast.Or,
    ast.IfExp,
    ast.Constant,
}
_ALLOWED_FUNCS = {
    "abs": abs, "min": min, "max": max, "round": round,
    "floor": math.floor, "ceil": math.ceil,
    "sqrt": math.sqrt, "pow": pow,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "rad": math.radians, "deg": math.degrees,
}

class _SafeEval(ast.NodeVisitor):
    def __init__(self, env: Dict[str, Any]):
        self.env = env
    def visit(self, node):
        if type(node) not in _ALLOWED_NODES:
            raise ValueError(f"Espressione non permessa: {type(node).__name__}")
        return super().visit(node)
    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)
    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, (int, float, bool)): return node.value
        raise ValueError("Costante non permessa")
    def visit_Name(self, node: ast.Name):
        if node.id in self.env: return self.env[node.id]
        raise ValueError(f"Variabile sconosciuta: {node.id}")
    def visit_UnaryOp(self, node: ast.UnaryOp):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd): return +operand
        if isinstance(node.op, ast.USub): return -operand
        raise ValueError("Operatore unario non permesso")
    def visit_BinOp(self, node: ast.BinOp):
        l = self.visit(node.left); r = self.visit(node.right)
        if isinstance(node.op, ast.Add): return l + r
        if isinstance(node.op, ast.Sub): return l - r
        if isinstance(node.op, ast.Mult): return l * r
        if isinstance(node.op, ast.Div): return l / r
        if isinstance(node.op, ast.FloorDiv): return l // r
        if isinstance(node.op, ast.Mod): return l % r
        if isinstance(node.op, ast.Pow): return l ** r
        raise ValueError("Operatore binario non permesso")
    def visit_Compare(self, node: ast.Compare):
        left = self.visit(node.left); ok = True
        for op, comp in zip(node.ops, node.comparators):
            right = self.visit(comp)
            if isinstance(op, ast.Eq): ok = ok and (left == right)
            elif isinstance(op, ast.NotEq): ok = ok and (left != right)
            elif isinstance(op, ast.Gt): ok = ok and (left > right)
            elif isinstance(op, ast.GtE): ok = ok and (left >= right)
            elif isinstance(op, ast.Lt): ok = ok and (left < right)
            elif isinstance(op, ast.LtE): ok = ok and (left <= right)
            else: raise ValueError("Operatore di confronto non permesso")
            left = right
        return ok
    def visit_BoolOp(self, node: ast.BoolOp):
        vals = [self.visit(v) for v in node.values]
        if isinstance(node.op, ast.And):
            res = True
            for v in vals: res = res and bool(v)
            return res
        if isinstance(node.op, ast.Or):
            res = False
            for v in vals: res = res or bool(v)
            return res
        raise ValueError("Operatore booleano non permesso")
    def visit_IfExp(self, node: ast.IfExp):
        return self.visit(node.body if self.visit(node.test) else node.orelse)
    def visit_Call(self, node: ast.Call):
        if not isinstance(node.func, ast.Name): raise ValueError("Chiamata funzione non permessa")
        fname = node.func.id
        if fname not in _ALLOWED_FUNCS: raise ValueError(f"Funzione non permessa: {fname}")
        args = [self.visit(a) for a in node.args]
        return _ALLOWED_FUNCS[fname](*args)

def safe_eval(expr: str, env: Dict[str, Any]) -> float:
    tree = ast.parse(expr, mode="eval")
    return _SafeEval(env).visit(tree)

from typing import NamedTuple

@dataclass
class Parameter:
    name: str
    type: str = "float"      # "float" | "int" | "bool" | "select"
    default: Any = 0.0
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[List[Any]] = None
    description: str = ""

@dataclass
class ElementDef:
    id: str
    role: str
    profile_var: str
    qty_expr: str
    length_expr: str
    angle_a_expr: str
    angle_b_expr: str
    note_expr: str = ""

@dataclass
class TypologyDef:
    name: str
    version: str
    description: str
    parameters: List[Parameter] = field(default_factory=list)
    derived: Dict[str, str] = field(default_factory=dict)
    elements: List[ElementDef] = field(default_factory=list)

@dataclass
class Part:
    id: str
    role: str
    profile: str
    qty: int
    length: float
    angle_a: float
    angle_b: float
    note: str = ""

class ParametricEngine:
    def __init__(self, typology: TypologyDef):
        self.typ = typology

    def evaluate(self, inputs: Dict[str, Any]) -> Tuple[List[Part], Dict[str, Any]]:
        env: Dict[str, Any] = {}
        # default + inputs
        for p in self.typ.parameters:
            env[p.name] = inputs.get(p.name, p.default)
        # derivate
        for k, expr in self.typ.derived.items():
            env[k] = float(safe_eval(expr, env))
        # elementi
        parts: List[Part] = []
        for e in self.typ.elements:
            prof = str(env.get(e.profile_var, "") or "—")
            qty = int(round(float(safe_eval(e.qty_expr, env))))
            length = float(safe_eval(e.length_expr, env))
            ang_a = float(safe_eval(e.angle_a_expr, env))
            ang_b = float(safe_eval(e.angle_b_expr, env))
            note = str(safe_eval(e.note_expr, env)) if e.note_expr else ""
            parts.append(Part(
                id=e.id, role=e.role, profile=prof, qty=qty,
                length=length, angle_a=ang_a, angle_b=ang_b, note=note
            ))
        return parts, env
