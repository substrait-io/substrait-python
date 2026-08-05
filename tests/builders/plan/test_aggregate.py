import pytest
import substrait.algebra_pb2 as stalg
import substrait.extensions.extensions_pb2 as ste
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt
import yaml

from substrait.builders.extended_expression import aggregate_function, column
from substrait.builders.plan import aggregate, default_version, read_named_table
from substrait.builders.type import boolean, i64
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema

content = """%YAML 1.2
---
urn: extension:test:urn
aggregate_functions:
  - name: "count"
    description: Count a set of values
    impls:
      - args:
          - name: x
            value: any
        nullability: DECLARED_OUTPUT
        decomposable: MANY
        intermediate: i64
        return: i64
"""


registry = ExtensionRegistry(load_default_extensions=False)
registry.register_extension_dict(yaml.safe_load(content))

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()], nullability=stt.Type.NULLABILITY_REQUIRED
)

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_aggregate():
    table = read_named_table("table", named_struct)

    group_expr = column("id")
    measure_expr = aggregate_function(
        "extension:test:urn",
        "count",
        expressions=[column("is_applicable")],
        alias=["count"],
    )

    actual = aggregate(
        table, grouping_expressions=[group_expr], measures=[measure_expr]
    )(registry)

    ns = infer_plan_schema(table(None))

    expected = stp.Plan(
        version=default_version,
        extension_urns=[
            ste.SimpleExtensionURN(extension_urn_anchor=1, urn="extension:test:urn")
        ],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_urn_reference=1,
                    function_anchor=1,
                    name="count:any",
                )
            )
        ],
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        aggregate=stalg.AggregateRel(
                            input=table(None).relations[-1].root.input,
                            grouping_expressions=[
                                group_expr(ns, registry).referred_expr[0].expression
                            ],
                            groupings=[
                                stalg.AggregateRel.Grouping(expression_references=[0])
                            ],
                            measures=[
                                stalg.AggregateRel.Measure(
                                    measure=measure_expr(ns, registry)
                                    .referred_expr[0]
                                    .measure
                                )
                            ],
                        )
                    ),
                    names=["id", "count"],
                )
            )
        ],
    )

    assert actual == expected


def test_aggregate_rejects_a_non_aggregate_measure():
    """A measure that is not an aggregate function used to be emitted as a measure
    that is *set but empty*: reading ``.measure`` off a reference holding an
    ``expression`` yields a default-constructed AggregateFunction, and assigning it
    sets the field.

    Beyond being malformed on its own, that is the one shape breaking the premise
    ``remap_function_references`` relies on -- that a present message implies a real
    reference -- so folding such a plan into another build renumbered its *unset*
    reference along with the genuine ones, silently pointing an empty measure at a
    real function.
    """
    table = read_named_table("table", named_struct)

    with pytest.raises(ValueError, match="must be aggregate functions"):
        aggregate(table, grouping_expressions=[column("id")], measures=[column("id")])(
            registry
        )
