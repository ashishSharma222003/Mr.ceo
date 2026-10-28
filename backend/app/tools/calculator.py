import ast
import operator

from .registry import builtin_tool

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("Unsupported expression")


@builtin_tool("calculator", "Evaluate an arithmetic expression with + - * / % ** and parentheses, e.g. '(2+3)*4'.")
def calculator(expression: str) -> str:
    # Return errors as text so the agent can fix its call instead of the whole task failing.
    try:
        return str(_eval(ast.parse(expression.replace("^", "**"), mode="eval").body))
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as e:
        return f"Error: {e or 'invalid expression'}. Use only numbers, + - * / % ** and parentheses."
