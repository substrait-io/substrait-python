import substrait.dataframe
from substrait.builders.extended_expression import column

from substrait.dataframe.dataframe import DataFrame
from substrait.dataframe.expression import Expression

__all__ = [DataFrame, Expression]


def col(name: str) -> Expression:
    """Column selection."""
    return Expression(column(name))


# TODO handle str_as_lit argument
def parse_into_expr(expr, str_as_lit: bool):
    return expr._to_compliant_expr(substrait.dataframe)
