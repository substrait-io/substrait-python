"""Enumeration-argument functions (``extract``, ``round_temporal``, ...).

Some standard functions take *enumeration arguments* -- the Substrait spec
(``functions_datetime.yaml``) declares them under ``args:`` with an ``options:``
domain rather than a ``value:`` type. ``extract`` is the canonical example::

    - name: "extract"
      impls:
        - args:
            - name: component        # enumeration argument
              options: [ YEAR, ISO_YEAR, US_YEAR, UNIX_TIME ]
            - name: x                # value argument
              value: date
          return: i64

Per the spec these serialize into ``ScalarFunction.arguments`` as
``FunctionArgument.enum`` (a positional operand, interleaved with the value
arguments in signature order) -- NOT into ``ScalarFunction.options``, which
carries only *behavioral* options (``overflow``, ``rounding``, ...). Consumers
such as DuckDB read enum selections exclusively from ``arguments``.

The user-facing API mirrors the spec's positional model (and substrait-go's
``types.Enum`` / substrait-java's ``EnumArg``): an enumeration selection is a
positional ``sub.enum("...")`` marker written in declared argument order, while
behavioral options stay on the ``**options`` keyword channel.

These tests guard two properties of the DataFrame / builder pipeline:

1. **Resolution.** ``sub.f.extract(sub.enum("YEAR"), col)`` must build -- the
   enum token interleaves into the match signature so the overload (which counts
   the enum position toward its arity) resolves.
2. **Serialization.** The enum selection must land in ``arguments`` as a
   ``FunctionArgument.enum``, not in ``options``. Routing it into ``options``
   produces a plan that omits the enum from ``arguments`` -- which DuckDB's
   consumer then reads as an empty enum vector and crashes on.
"""

import pytest
import substrait.algebra_pb2 as stalg

import substrait.dataframe as sub
from substrait.builders.type import precision_timestamp


def _messages_of(message, message_type) -> list:
    """Every message of ``message_type`` reachable anywhere in a proto tree."""
    target = message_type.DESCRIPTOR.full_name
    found: list = []

    def walk(msg):
        for field, value in msg.ListFields():
            if field.message_type is None:
                continue
            items = value if field.is_repeated else [value]
            for item in items:
                if field.message_type.full_name == target:
                    found.append(item)
                walk(item)

    walk(message)
    return found


def _function_name(plan, function) -> str:
    """The function's base extension name (the ``foo`` of the ``foo:sig`` anchor)."""
    ref = function.function_reference
    for decl in plan.extensions:
        fn = decl.extension_function
        if fn.function_anchor == ref:
            return fn.name.split(":", 1)[0]
    return ""


def _functions_named(plan, message_type, name: str) -> list:
    """The ``message_type`` calls in ``plan`` whose base name is exactly ``name``.

    Exact on the base name (declarations are ``name:signature``): a prefix match
    like ``startswith("extract")`` would also catch ``extract_boolean`` and break
    the single-match unpacking below.
    """
    return [
        m for m in _messages_of(plan, message_type) if _function_name(plan, m) == name
    ]


def _arg_kinds(function) -> list:
    return [a.WhichOneof("arg_type") for a in function.arguments]


def _options(function) -> list:
    return [(o.name, list(o.preference)) for o in function.options]


def test_extract_with_a_single_enum_argument_resolves():
    """The two-argument ``extract(component, date)`` overload must build."""
    df = sub.read_named_table("t", {"d": sub.date})

    # Must not raise "Unknown function extract"; unpacking asserts exactly one.
    plan = df.with_columns(y=sub.f.extract(sub.enum("YEAR"), sub.col("d"))).to_plan()

    (extract,) = _functions_named(plan, stalg.Expression.ScalarFunction, "extract")
    assert _arg_kinds(extract) == ["enum", "value"]


def test_extract_serializes_the_enum_as_an_argument_not_an_option():
    """sub.enum("YEAR") must be a FunctionArgument.enum, in signature position.

    Spec order for this overload is [component (enum), x (value)], so the
    positional value operand follows the enum selection.
    """
    df = sub.read_named_table("t", {"d": sub.date})

    plan = df.with_columns(y=sub.f.extract(sub.enum("YEAR"), sub.col("d"))).to_plan()

    (extract,) = _functions_named(plan, stalg.Expression.ScalarFunction, "extract")
    assert _arg_kinds(extract) == ["enum", "value"], (
        f"enum not carried in arguments in signature order: {_arg_kinds(extract)}"
    )
    assert extract.arguments[0].enum == "YEAR"
    assert list(extract.options) == [], (
        f"enum selection leaked into options (crashes DuckDB): {extract.options}"
    )


def test_extract_day_of_month_carries_both_enum_arguments():
    """The exact combination behind the reported DuckDB crash.

    ``extract(sub.enum("DAY"), sub.enum("ONE"), <timestamp>)`` has two enum
    arguments; both must appear in ``arguments`` (order [component, indexing, x])
    and neither in ``options``.
    """
    df = sub.read_named_table("t", {"ts": precision_timestamp(6)})

    plan = df.with_columns(
        dom=sub.f.extract(sub.enum("DAY"), sub.enum("ONE"), sub.col("ts"))
    ).to_plan()

    (extract,) = _functions_named(plan, stalg.Expression.ScalarFunction, "extract")
    assert _arg_kinds(extract) == ["enum", "enum", "value"], _arg_kinds(extract)
    assert [extract.arguments[0].enum, extract.arguments[1].enum] == ["DAY", "ONE"]
    assert list(extract.options) == [], (
        f"enum selections leaked into options (crashes DuckDB): {extract.options}"
    )


def test_two_enum_selections_yield_distinct_inferred_output_names():
    """Enum selections must feed the inferred alias, else projections collide.

    ``extract(sub.enum("YEAR"), d)`` and ``extract(sub.enum("ISO_YEAR"), d)``
    differ only in the enum selection; if the inferred name ignored it both
    columns would be named ``extract(d)`` and clash in one projection.
    """
    df = sub.read_named_table("t", {"d": sub.date})

    plan = df.select(
        sub.f.extract(sub.enum("YEAR"), sub.col("d")),
        sub.f.extract(sub.enum("ISO_YEAR"), sub.col("d")),
    ).to_plan()

    names = list(plan.relations[0].root.names)
    assert len(set(names)) == len(names), f"inferred output names collided: {names}"


def test_std_dev_resolves_to_enum_overload_not_deprecated_value_only():
    """sub.enum("POPULATION") must select the enum overload.

    ``std_dev`` declares both a deprecated value-only overload (``std_dev:fp64``,
    one argument) and an enum-argument one (``std_dev:req_fp64``, two arguments).
    Supplying the enum selection positionally makes the call two operands wide, so
    it matches the enum overload by arity and the selection lands in ``arguments``
    as an enum rather than becoming a behavioral option.
    """
    df = sub.read_named_table("t", {"x": sub.fp64})

    plan = (
        df.group_by()
        .agg(sub.f.std_dev(sub.enum("POPULATION"), sub.col("x")).alias("s"))
        .to_plan()
    )

    (std_dev,) = _functions_named(plan, stalg.AggregateFunction, "std_dev")
    assert _arg_kinds(std_dev) == ["enum", "value"], _arg_kinds(std_dev)
    assert std_dev.arguments[0].enum == "POPULATION"
    assert list(std_dev.options) == [], (
        f"enum selection leaked into options: {std_dev.options}"
    )


def test_median_splits_enum_argument_from_behavioral_option():
    """A call carrying both kinds at once -- the premise of this change.

    ``median`` takes an enum argument ``precision`` *and* a behavioral option
    ``rounding``. The positional ``sub.enum("EXACT")`` must land in ``arguments``
    as an enum, the keyword ``rounding`` in ``options`` as a FunctionOption; they
    must not swap channels.
    """
    df = sub.read_named_table("t", {"x": sub.fp64})

    plan = (
        df.group_by()
        .agg(
            sub.f.median(sub.enum("EXACT"), sub.col("x"), rounding="TRUNCATE").alias(
                "m"
            )
        )
        .to_plan()
    )

    (median,) = _functions_named(plan, stalg.AggregateFunction, "median")
    assert _arg_kinds(median) == ["enum", "value"], _arg_kinds(median)
    assert median.arguments[0].enum == "EXACT"
    assert _options(median) == [("rounding", ["TRUNCATE"])], _options(median)


def test_bare_string_is_not_an_enum_selection():
    """Only ``sub.enum(...)`` marks an enum; a bare string is a literal operand.

    ``extract(sub.col("d"), "YEAR")`` coerces ``"YEAR"`` to a string literal, so
    no overload matches ([date, string] value signature) and resolution raises
    -- documenting why the positional marker is required.
    """
    df = sub.read_named_table("t", {"d": sub.date})

    with pytest.raises(Exception, match="[Uu]nknown function|No matching overload"):
        df.with_columns(y=sub.f.extract(sub.col("d"), "YEAR")).to_plan()


def test_window_call_site_still_emits_value_arguments():
    """The window builder shares argument assembly; a value operand must survive.

    No standard window function takes an enumeration argument, so this guards the
    value-only path through the changed ``_function_arguments`` return for the
    window call site rather than enum handling.
    """
    df = sub.read_named_table("t", {"a": sub.i64})

    plan = df.select(sub.f.ntile(sub.lit(4)).over(order_by="a")).to_plan()

    (ntile,) = _functions_named(plan, stalg.Expression.WindowFunction, "ntile")
    assert _arg_kinds(ntile) == ["value"], _arg_kinds(ntile)
