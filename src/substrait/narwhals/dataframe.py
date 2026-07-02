"""The Narwhals integration layer for Substrait.

This module is the **Narwhals-compliant wrapper**: it lets ``narwhals`` drive
Substrait plan construction via ``nw.from_native(...)`` by exposing the backend
hooks (``__narwhals_lazyframe__`` / ``__narwhals_namespace__``) and translating
Narwhals calls into Substrait plan builders.

It is distinct from :mod:`substrait.frame`, which is the Substrait-*native*
fluent DataFrame you can call directly without Narwhals. This layer sits on top
of that native machinery; the two compose rather than compete.

Status: experimental / minimal -- it currently implements only a subset of the
Narwhals compliant protocol, to be built out on top of :mod:`substrait.frame`.
"""

from typing import Iterable, Union

import substrait.narwhals
from substrait.builders.plan import select
from substrait.narwhals.expression import Expression


class DataFrame:
    """Narwhals-compliant wrapper around a Substrait plan.

    Presents as a Narwhals ``LazyFrame`` backend. For direct, non-Narwhals plan
    building use :class:`substrait.frame.DataFrame` instead.
    """

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
        return substrait.narwhals

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
