from typing import Iterable, Union

import substrait.dataframe
from substrait.builders.plan import select
from substrait.dataframe.expression import Expression


class DataFrame:
    def __init__(self, plan):
        self.plan = plan
        self._native_frame = self

    def to_substrait(self, registry):
        return self.plan(registry)

    def __narwhals_lazyframe__(self) -> "DataFrame":
        """Return object implementing CompliantDataFrame protocol."""
        return self

    def __narwhals_namespace__(self):
        """
        Return the namespace object that contains functions like col, lit, etc.
        This is how Narwhals knows which backend's functions to use.
        """
        return substrait.dataframe

    def select(
        self, *exprs: Union[Expression, Iterable[Expression]], **named_exprs: Expression
    ) -> "DataFrame":
        expressions = [e.expr for e in exprs] + [
            expr.alias(alias).expr for alias, expr in named_exprs.items()
        ]
        return DataFrame(select(self.plan, expressions=expressions))

    # TODO handle version
    def _with_version(self, version):
        return self
