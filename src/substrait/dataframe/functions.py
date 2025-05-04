from . import scalar_function
from .expression import UnboundExpression

def add(*expressions: UnboundExpression):
    return scalar_function("functions_arithmetic.yaml", "add", *expressions)
