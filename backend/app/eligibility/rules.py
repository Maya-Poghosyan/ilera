"""Validate a deliberately small declarative rule language; no eval or calls."""
import ast

_ALLOWED = (ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.And, ast.Or,
            ast.Not, ast.Eq, ast.NotEq, ast.In, ast.NotIn, ast.Lt, ast.LtE,
            ast.Gt, ast.GtE, ast.Attribute, ast.Name, ast.Load, ast.Constant,
            ast.List, ast.Tuple)


def validate_rule(rule: str, facts: list[str]) -> None:
    try:
        tree = ast.parse(rule, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid rule syntax") from exc
    if not isinstance(tree.body, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
        raise ValueError("Rule must be a boolean expression")
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ValueError(f"Unsupported rule operation: {type(node).__name__}")
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name):
                raise ValueError("Only canonical two-part fact paths are allowed")
            path = f"{node.value.id}.{node.attr}"
            if path not in facts:
                raise ValueError(f"Rule uses undeclared fact: {path}")
        if isinstance(node, ast.Name) and not isinstance(parents.get(node), ast.Attribute):
            raise ValueError("Bare names are not fact values")
        if isinstance(node, ast.BoolOp) and any(not isinstance(v, (ast.Compare, ast.BoolOp, ast.UnaryOp)) for v in node.values):
            raise ValueError("Boolean operators require comparisons")
        if isinstance(node, ast.UnaryOp) and not isinstance(node.operand, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
            raise ValueError("not requires a comparison")


def evaluate_rule(rule: str, values: dict[str, object]) -> bool:
    """Interpret only validated comparisons/boolean operations over supplied facts."""
    validate_rule(rule, list(values))
    comparisons = {
        ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
        ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
        ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
        ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
    }

    def visit(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [visit(item) for item in node.elts]
        if isinstance(node, ast.Attribute):
            return values[f"{node.value.id}.{node.attr}"]
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for operator, right_node in zip(node.ops, node.comparators):
                right = visit(right_node)
                if not comparisons[type(operator)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BoolOp):
            operands = [visit(item) for item in node.values]
            if any(type(item) is not bool for item in operands):
                raise ValueError("Boolean operators require boolean operands")
            return all(operands) if isinstance(node.op, ast.And) else any(operands)
        if isinstance(node, ast.UnaryOp):
            operand = visit(node.operand)
            if type(operand) is not bool:
                raise ValueError("not requires a boolean operand")
            return not operand
        raise ValueError("Unsupported rule operand")

    result = visit(ast.parse(rule, mode="eval").body)
    if type(result) is not bool:
        raise ValueError("Rule did not produce a boolean")
    return result
