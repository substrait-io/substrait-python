from substrait.builders.extended_expression import (
    UnboundExtendedExpression,
    scalar_function,
)
from substrait.builders.extended_expression import (
    alias as _alias,
)


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
