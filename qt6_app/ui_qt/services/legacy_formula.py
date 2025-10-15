from __future__ import annotations
import ast
import math
import re
from typing import Any, Dict, Iterable, List, Set

_VAR_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
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

def sanitize_name(name: str) -> str:
    """
    Converte un nome profilo in token variabile sicuro: lettere/numeri/underscore maiuscoli.
    Esempio: 'Telaio 70x40/ALU' -> 'TELAIO_70X40_ALU'
    """
    if not name:
        return ""
    out = []
    for ch in name.upper():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", ".", "/", "\\"):
            out.append("_")
        else:
            out.append("_")
    # rimuovi underscore multipli
    s = re.sub(r"_+", "_", "".join(out)).strip("_")
    return s or "PROFILO"

def scan_variables(expr: str) -> List[str]:
    """
    Estrae i nomi variabili in modo semplice (H, L, C_R1, token profilo, variabili locali).
    Non valida l'espressione; serve per guida/analisi.
    """
    if not expr:
        return []
    # Prendi parole stile Python + mantieni C_R\d pattern (già catturato dalla regex base)
    found = list(dict.fromkeys(_VAR_RE.findall(expr)))
    return found

class _SafeEval(ast.NodeVisitor):
    def __init__(self, env: Dict[str, Any]):
        self.env = env

    def visit(self, node):
        if type(node) not in _ALLOWED_NODES:
            raise ValueError(f"Nodo non permesso: {type(node).__name__}")
        return super().visit(node)

    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ValueError("Costante non permessa")

    def visit_Name(self, node: ast.Name):
        if node.id in self.env:
            return self.env[node.id]
        raise ValueError(f"Variabile sconosciuta: {node.id}")

    def visit_UnaryOp(self, node: ast.UnaryOp):
        val = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd): return +val
        if isinstance(node.op, ast.USub): return -val
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
            else: raise ValueError("Operatore confronto non permesso")
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
        if not isinstance(node.func, ast.Name):
            raise ValueError("Funzione non permessa")
        fname = node.func.id
        if fname not in _ALLOWED_FUNCS:
            raise ValueError(f"Funzione non permessa: {fname}")
        args = [self.visit(a) for a in node.args]
        return _ALLOWED_FUNCS[fname](*args)

def eval_formula(expr: str, env: Dict[str, Any]) -> float:
    """
    Valuta in modo sicuro una formula. Restituisce float.
    """
    if not expr:
        return 0.0
    tree = ast.parse(expr, mode="eval")
    return float(_SafeEval(env).visit(tree))
