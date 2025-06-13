import random
import string
from sqloxide import parse_sql
from substrait.builders.extended_expression import (
    UnboundExtendedExpression,
    column,
    scalar_function,
    literal,
    aggregate_function,
    window_function,
)
from substrait.builders.plan import (
    read_named_table,
    project,
    filter,
    sort,
    fetch,
    set,
    join,
    aggregate,
)
from substrait.gen.proto import type_pb2 as stt
from substrait.gen.proto import algebra_pb2 as stalg
from substrait.extension_registry import ExtensionRegistry
from typing import Callable
from deepdiff import DeepDiff

SchemaResolver = Callable[[str], stt.NamedStruct]

function_mapping = {
    "Plus": ("functions_arithmetic.yaml", "add"),
    "Minus": ("functions_arithmetic.yaml", "subtract"),
    "Gt": ("functions_comparison.yaml", "gt"),
    "GtEq": ("functions_comparison.yaml", "gte"),
    "Lt": ("functions_comparison.yaml", "lt"),
    "Eq": ("functions_comparison.yaml", "equal"),
}

aggregate_function_mapping = {"SUM": ("functions_arithmetic.yaml", "sum")}

window_function_mapping = {
    "row_number": ("functions_arithmetic.yaml", "row_number"),
}


def compare_dicts(dict1, dict2):
    diff = DeepDiff(dict1, dict2, exclude_regex_paths=["span"])
    return len(diff) == 0


def translate_expression(
    ast: dict,
    schema_resolver: SchemaResolver,
    registry: ExtensionRegistry,
    measures: list[UnboundExtendedExpression],
    groupings: list[dict],
    alias: str = None,
) -> UnboundExtendedExpression:
    assert len(ast) == 1
    op = list(ast.keys())[0]

    if groupings:
        # This means we are parsing a projection after a grouping
        # Loop through used groupings for an identical ast and return it rather than recalculate
        for i, f in enumerate(groupings):
            if compare_dicts(ast, f):
                return column(i, alias=alias)

    ast = ast[op]

    if op == "Identifier":
        return column(ast["value"], alias=alias)
    elif op == "UnnamedExpr" or op == "expr" or op == "Unnamed" or op == "Expr":
        return translate_expression(
            ast,
            schema_resolver=schema_resolver,
            registry=registry,
            measures=measures,
            groupings=groupings,
        )
    elif op == "ExprWithAlias":
        return translate_expression(
            ast["expr"],
            schema_resolver=schema_resolver,
            registry=registry,
            measures=measures,
            groupings=groupings,
            alias=ast["alias"]["value"],
        )
    elif op == "BinaryOp":
        expressions = [
            translate_expression(
                ast["left"],
                schema_resolver=schema_resolver,
                registry=registry,
                measures=measures,
                groupings=groupings,
            ),
            translate_expression(
                ast["right"],
                schema_resolver=schema_resolver,
                registry=registry,
                measures=measures,
                groupings=groupings,
            ),
        ]
        func = function_mapping[ast["op"]]
        return scalar_function(func[0], func[1], expressions=expressions, alias=alias)
    elif op == "Value":
        return literal(
            int(ast["value"]["Number"][0]), stt.Type(i64=stt.Type.I64()), alias=alias
        )  # TODO infer type
    elif op == "Function":
        expressions = [
            translate_expression(
                e,
                schema_resolver=schema_resolver,
                registry=registry,
                measures=measures,
                groupings=groupings,
            )
            for e in ast["args"]["List"]["args"]
        ]
        name = ast["name"][0]["Identifier"]["value"]

        if name in function_mapping:
            func = function_mapping[name]
            return scalar_function(func[0], func[1], *expressions, alias=alias)
        elif name in aggregate_function_mapping:
            # All measures need to be extracted out because substrait calculates measures in a separate rel
            # We generate a random name for the measure and return a column with that name for the projection to work
            # Start by checking if multiple measures are identical and reuse previously generated name
            for m in measures:
                if compare_dicts(ast, m[1]):
                    return column(m[2], alias=alias)

            func = aggregate_function_mapping[name]
            random_name = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=5)
            )  # TODO make this deterministic
            aggr = aggregate_function(func[0], func[1], expressions, alias=random_name)
            measures.append((aggr, ast, random_name))
            return column(random_name, alias=alias)
        elif name in window_function_mapping:
            func = window_function_mapping[name]

            partitions = [
                translate_expression(
                    e,
                    schema_resolver=schema_resolver,
                    registry=registry,
                    measures=measures,
                    groupings=groupings,
                )
                for e in ast["over"]["WindowSpec"]["partition_by"]
            ]

            return window_function(
                func[0], func[1], expressions, partitions=partitions, alias=alias
            )

        else:
            raise Exception(f"Unknown function {name}")
    # elif op == "Wildcard":
    #     return wildcard()
    else:
        raise Exception(f"Unknown op {op}")


def translate(ast: dict, schema_resolver: SchemaResolver, registry: ExtensionRegistry):
    assert len(ast) == 1
    op = list(ast.keys())[0]
    ast = ast[op]

    if op == "Query":
        relation = translate(
            ast["body"], schema_resolver=schema_resolver, registry=registry
        )

        if ast["order_by"]:
            expressions = [
                translate_expression(
                    e["expr"],
                    schema_resolver=schema_resolver,
                    registry=registry,
                    measures=None,
                    groupings=None,
                )
                for e in ast["order_by"]["kind"]["Expressions"]
            ]
            relation = sort(relation, expressions)(registry)

        if ast["limit_clause"]:
            limit_expression = translate_expression(
                ast["limit_clause"]["LimitOffset"]["limit"],
                schema_resolver=schema_resolver,
                registry=registry,
                measures=None,
                groupings=None,
            )

            if ast["limit_clause"]["LimitOffset"]["offset"]:
                offset_expression = translate_expression(
                    ast["limit_clause"]["LimitOffset"]["offset"]["value"],
                    schema_resolver=schema_resolver,
                    registry=registry,
                    measures=None,
                    groupings=None,
                )
            else:
                offset_expression = None

            relation = fetch(relation, offset_expression, limit_expression)(registry)

        return relation
    elif op == "Select":
        relation = translate(
            ast["from"][0]["relation"],
            schema_resolver=schema_resolver,
            registry=registry,
        )

        if ast["from"][0]["joins"]:
            for _join in ast["from"][0]["joins"]:
                join_type_mapping = {
                    "Inner": stalg.JoinRel.JOIN_TYPE_INNER,
                    "Left": stalg.JoinRel.JOIN_TYPE_LEFT,
                    "LeftOuter": stalg.JoinRel.JOIN_TYPE_LEFT,
                    "RightOuter": stalg.JoinRel.JOIN_TYPE_RIGHT,
                    "Right": stalg.JoinRel.JOIN_TYPE_RIGHT,
                }
                right = translate(
                    _join["relation"],
                    schema_resolver=schema_resolver,
                    registry=registry,
                )

                join_type = list(_join["join_operator"].keys())[0]

                expression = translate_expression(
                    _join["join_operator"][join_type]["On"],
                    schema_resolver=schema_resolver,
                    registry=registry,
                    measures=None,
                    groupings=None,
                )

                relation = join(
                    relation, right, expression, join_type_mapping[join_type]
                )(registry)

        if "selection" in ast and ast["selection"]:
            where_expression = translate_expression(
                ast["selection"],
                schema_resolver=schema_resolver,
                registry=registry,
                measures=None,
                groupings=None,
            )
            relation = filter(relation, where_expression)(registry)

        if ast["group_by"] and ast["group_by"]["Expressions"][0]:
            groupings = ast["group_by"]["Expressions"][0]
            grouping_expressions = [
                translate_expression(
                    e,
                    schema_resolver=schema_resolver,
                    registry=registry,
                    measures=None,
                    groupings=None,
                )
                for e in groupings
            ]
        else:
            groupings = []
            grouping_expressions = []

        measures = []

        projection = [
            translate_expression(
                p,
                schema_resolver=schema_resolver,
                registry=registry,
                measures=measures,
                groupings=groupings,
            )
            for p in ast["projection"]
        ]

        if ast["having"]:
            having_predicate = translate_expression(
                ast["having"],
                schema_resolver=schema_resolver,
                registry=registry,
                measures=measures,
                groupings=[],
            )
        else:
            having_predicate = None

        if measures or groupings:
            relation = aggregate(
                relation, grouping_expressions, [e[0] for e in measures]
            )(registry)

        if having_predicate:
            relation = filter(relation, having_predicate)(registry)

        return project(relation, expressions=projection)(registry)
    elif op == "Table":
        name = ast["name"][0]["Identifier"]["value"]
        return read_named_table(name, schema_resolver(name))
    elif op == "SetOperation":
        # TODO more than 2 inputs to a set operation
        left = translate(
            ast["left"], schema_resolver=schema_resolver, registry=registry
        )
        right = translate(
            ast["right"], schema_resolver=schema_resolver, registry=registry
        )
        if ast["op"] == "Union":
            set_op = (
                stalg.SetRel.SET_OP_UNION_ALL
                if ast["set_quantifier"] == "All"
                else stalg.SetRel.SET_OP_UNION_DISTINCT
            )
        else:
            raise Exception("")

        return set([left, right], set_op)(registry)
    else:
        raise Exception(f"Unknown op {op}")


def convert(query: str, dialect: str, schema_resolver: SchemaResolver):
    ast = parse_sql(sql=query, dialect=dialect)[0]
    registry = ExtensionRegistry(load_default_extensions=True)
    return translate(ast, schema_resolver=schema_resolver, registry=registry)
