import substrait.extended_expression_pb2 as stee
import substrait.type_pb2 as stp

from substrait.builders.extended_expression import (
    ExtendedExpressionOrUnbound,
    UnboundExtendedExpression,
    resolve_expression,
    scalar_function,
)
from substrait.extension_registry import ExtensionRegistry


def _alias(
    expr: ExtendedExpressionOrUnbound,
    alias: str = None,
):
    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expression = resolve_expression(expr, base_schema, registry)
        bound_expression.referred_expr[0].output_names[0] = alias
        return bound_expression

    return resolve


class Expression:
    def __init__(self, expr: UnboundExtendedExpression):
        self.expr = expr

    def alias(self, alias: str):
        self.expr = _alias(self.expr, alias)
        return self

    def abs(self):
        self.expr = scalar_function(
            "functions_arithmetic.yaml", "abs", expressions=[self.expr]
        )
        return self
