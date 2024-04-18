import itertools

import sqlglot

from substrait import proto

SQL_UNARY_FUNCTIONS = {"not": "not"}
SQL_BINARY_FUNCTIONS = {
    # Arithmetic
    "add": "add",
    "div": "div",
    "mul": "mul",
    "sub": "sub",
    "mod": "modulus",
    "bitwiseand": "bitwise_and",
    "bitwiseor": "bitwise_or",
    "bitwisexor": "bitwise_xor",
    "bitwiseor": "bitwise_or",
    # Comparisons
    "eq": "equal",
    "nullsafeeq": "is_not_distinct_from",
    "neq": "not_equal",
    "gt": "gt",
    "gte": "gte",
    "lt": "lt",
    "lte": "lte",
    # logical
    "and": "and",
    "or": "or",
}


def parse_sql_extended_expression(catalog, schema, sql):
    select = sqlglot.parse_one(sql)
    if not isinstance(select, sqlglot.expressions.Select):
        raise ValueError("a SELECT statement was expected")

    sqlglot_parser = SQLGlotParser(catalog, schema)

    # Handle the projections in the SELECT statemenent.
    project_expressions = []
    projection_invoked_functions = set()
    for sqlexpr in select.expressions:
        invoked_functions, output_name, expr = sqlglot_parser.expression_from_sqlglot(
            sqlexpr
        )
        projection_invoked_functions.update(invoked_functions)
        project_expressions.append(
            proto.ExpressionReference(expression=expr, output_names=[output_name])
        )
    extension_uris, extensions = catalog.extensions_for_functions(
        projection_invoked_functions
    )
    projection_extended_expr = proto.ExtendedExpression(
        extension_uris=extension_uris,
        extensions=extensions,
        base_schema=schema,
        referred_expr=project_expressions,
    )

    # Handle WHERE clause in the SELECT statement.
    invoked_functions_filter, _, filter_expr = sqlglot_parser.expression_from_sqlglot(
        select.find(sqlglot.expressions.Where).this
    )
    extension_uris, extensions = catalog.extensions_for_functions(
        invoked_functions_filter
    )
    filter_extended_expr = proto.ExtendedExpression(
        extension_uris=extension_uris,
        extensions=extensions,
        base_schema=schema,
        referred_expr=[proto.ExpressionReference(expression=filter_expr)],
    )

    return projection_extended_expr, filter_extended_expr


class SQLGlotParser:
    def __init__(self, functions_catalog, schema):
        self._functions_catalog = functions_catalog
        self._schema = schema
        self._counter = itertools.count()

    def expression_from_sqlglot(self, sqlglot_node):
        invoked_functions = set()
        output_name, _, substrait_expr = self._parse_expression(
            sqlglot_node, invoked_functions
        )
        return invoked_functions, output_name, substrait_expr

    def _parse_expression(self, expr, invoked_functions):
        if isinstance(expr, sqlglot.expressions.Literal):
            if expr.is_string:
                return (
                    f"literal_{next(self._counter)}",
                    proto.Type(string=proto.Type.String()),
                    proto.Expression(
                        literal=proto.Expression.Literal(string=expr.text)
                    ),
                )
            elif expr.is_int:
                return (
                    f"literal_{next(self._counter)}",
                    proto.Type(i32=proto.Type.I32()),
                    proto.Expression(
                        literal=proto.Expression.Literal(i32=int(expr.name))
                    ),
                )
            elif sqlglot.helper.is_float(expr.name):
                return (
                    f"literal_{next(self._counter)}",
                    proto.Type(fp32=proto.Type.FP32()),
                    proto.Expression(
                        literal=proto.Expression.Literal(float=float(expr.name))
                    ),
                )
            else:
                raise ValueError(f"Unsupporter literal: {expr.text}")
        elif isinstance(expr, sqlglot.expressions.Column):
            column_name = expr.output_name
            schema_field = list(self._schema.names).index(column_name)
            schema_type = self._schema.struct.types[schema_field]
            return (
                column_name,
                schema_type,
                proto.Expression(
                    selection=proto.Expression.FieldReference(
                        direct_reference=proto.Expression.ReferenceSegment(
                            struct_field=proto.Expression.ReferenceSegment.StructField(
                                field=schema_field
                            )
                        )
                    )
                ),
            )
        elif isinstance(expr, sqlglot.expressions.Alias):
            _, aliased_type, aliased_expr = self._parse_expression(
                expr.this, invoked_functions
            )
            return expr.output_name, aliased_type, aliased_expr
        elif expr.key in SQL_UNARY_FUNCTIONS:
            argument_name, argument_type, argument = self._parse_expression(
                expr.this, invoked_functions
            )
            function_name = SQL_UNARY_FUNCTIONS[expr.key]
            signature, result_type, function_expression = (
                self._parse_function_invokation(function_name, argument_type, argument)
            )
            invoked_functions.add(signature)
            result_name = f"{function_name}_{argument_name}_{next(self._counter)}"
            return result_name, result_type, function_expression
        elif expr.key in SQL_BINARY_FUNCTIONS:
            left_name, left_type, left = self._parse_expression(
                expr.left, invoked_functions
            )
            right_name, right_type, right = self._parse_expression(
                expr.right, invoked_functions
            )
            function_name = SQL_BINARY_FUNCTIONS[expr.key]
            signature, result_type, function_expression = (
                self._parse_function_invokation(
                    function_name, left_type, left, right_type, right
                )
            )
            invoked_functions.add(signature)
            result_name = (
                f"{left_name}_{function_name}_{right_name}_{next(self._counter)}"
            )
            return result_name, result_type, function_expression
        else:
            raise ValueError(
                f"Unsupported expression in ExtendedExpression: '{expr.key}' -> {expr}"
            )

    def _parse_function_invokation(
        self, function_name, left_type, left, right_type=None, right=None
    ):
        binary = False
        argtypes = [left_type]
        if right_type or right:
            binary = True
            argtypes.append(right_type)
        signature = self._functions_catalog.signature(function_name, argtypes)

        try:
            function_anchor = self._functions_catalog.function_anchor(signature)
        except KeyError:
            # No function found with the exact types, try any1_any1 version
            # TODO: What about cases like i32_any1? What about any instead of any1?
            if binary:
                signature = f"{function_name}:any1_any1"
            else:
                signature = f"{function_name}:any1"
            function_anchor = self._functions_catalog.function_anchor(signature)

        function_return_type = self._functions_catalog.function_return_type(signature)
        if function_return_type is None:
            print("No return type for", signature)
            # TODO: Is this the right way to handle this?
            function_return_type = left_type
        return (
            signature,
            function_return_type,
            proto.Expression(
                scalar_function=proto.Expression.ScalarFunction(
                    function_reference=function_anchor,
                    arguments=(
                        [
                            proto.FunctionArgument(value=left),
                            proto.FunctionArgument(value=right),
                        ]
                        if binary
                        else [proto.FunctionArgument(value=left)]
                    ),
                )
            ),
        )
