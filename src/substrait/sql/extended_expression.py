import itertools

import sqlglot

from substrait import proto
from .utils import DispatchRegistry


SQL_FUNCTIONS = {
    # Arithmetic
    sqlglot.expressions.Add: "add",
    sqlglot.expressions.Div: "div",
    sqlglot.expressions.Mul: "mul",
    sqlglot.expressions.Sub: "sub",
    sqlglot.expressions.Mod: "modulus",
    sqlglot.expressions.BitwiseAnd: "bitwise_and",
    sqlglot.expressions.BitwiseOr: "bitwise_or",
    sqlglot.expressions.BitwiseXor: "bitwise_xor",
    sqlglot.expressions.BitwiseNot: "bitwise_not",
    # Comparisons
    sqlglot.expressions.EQ: "equal",
    sqlglot.expressions.NullSafeEQ: "is_not_distinct_from",
    sqlglot.expressions.NEQ: "not_equal",
    sqlglot.expressions.GT: "gt",
    sqlglot.expressions.GTE: "gte",
    sqlglot.expressions.LT: "lt",
    sqlglot.expressions.LTE: "lte",
    # logical
    sqlglot.expressions.And: "and",
    sqlglot.expressions.Or: "or",
    sqlglot.expressions.Not: "not",
}


def parse_sql_extended_expression(catalog, schema, sql):
    """Parse a SQL SELECT statement into an ExtendedExpression.

    Only supports SELECT statements with projections and WHERE clauses.
    """
    select = sqlglot.parse_one(sql)
    if not isinstance(select, sqlglot.expressions.Select):
        raise ValueError("a SELECT statement was expected")

    sqlglot_parser = SQLGlotParser(catalog, schema)

    # Handle the projections in the SELECT statemenent.
    project_expressions = []
    projection_invoked_functions = set()
    for sqlexpr in select.expressions:
        parsed_expr = sqlglot_parser.expression_from_sqlglot(sqlexpr)
        projection_invoked_functions.update(parsed_expr.invoked_functions)
        project_expressions.append(
            proto.ExpressionReference(
                expression=parsed_expr.expression,
                output_names=[parsed_expr.output_name],
            )
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
    filter_parsed_expr = sqlglot_parser.expression_from_sqlglot(
        select.find(sqlglot.expressions.Where).this
    )
    extension_uris, extensions = catalog.extensions_for_functions(
        filter_parsed_expr.invoked_functions
    )
    filter_extended_expr = proto.ExtendedExpression(
        extension_uris=extension_uris,
        extensions=extensions,
        base_schema=schema,
        referred_expr=[
            proto.ExpressionReference(expression=filter_parsed_expr.expression)
        ],
    )

    return projection_extended_expr, filter_extended_expr


class SQLGlotParser:
    DISPATCH_REGISTRY = DispatchRegistry()

    def __init__(self, functions_catalog, schema):
        self._functions_catalog = functions_catalog
        self._schema = schema
        self._counter = itertools.count()

        self._parse_expression = self.DISPATCH_REGISTRY.bind(self)

    def expression_from_sqlglot(self, sqlglot_node):
        """Parse a SQLGlot expression into a Substrait Expression."""
        return self._parse_expression(sqlglot_node)

    @DISPATCH_REGISTRY.register(sqlglot.expressions.Literal)
    def _parse_Literal(self, expr):
        if expr.is_string:
            return ParsedSubstraitExpression(
                f"literal${next(self._counter)}",
                proto.Type(string=proto.Type.String()),
                proto.Expression(literal=proto.Expression.Literal(string=expr.text)),
            )
        elif expr.is_int:
            return ParsedSubstraitExpression(
                f"literal${next(self._counter)}",
                proto.Type(i32=proto.Type.I32()),
                proto.Expression(literal=proto.Expression.Literal(i32=int(expr.name))),
            )
        elif sqlglot.helper.is_float(expr.name):
            return ParsedSubstraitExpression(
                f"literal${next(self._counter)}",
                proto.Type(fp32=proto.Type.FP32()),
                proto.Expression(
                    literal=proto.Expression.Literal(float=float(expr.name))
                ),
            )
        else:
            raise ValueError(f"Unsupporter literal: {expr.text}")

    @DISPATCH_REGISTRY.register(sqlglot.expressions.Column)
    def _parse_Column(self, expr):
        column_name = expr.output_name
        schema_field = list(self._schema.names).index(column_name)
        schema_type = self._schema.struct.types[schema_field]
        return ParsedSubstraitExpression(
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

    @DISPATCH_REGISTRY.register(sqlglot.expressions.Alias)
    def _parse_Alias(self, expr):
        parsed_expression = self._parse_expression(expr.this)
        return parsed_expression.duplicate(output_name=expr.output_name)

    @DISPATCH_REGISTRY.register(sqlglot.expressions.Binary)
    def _parser_Binary(self, expr):
        left_parsed_expr = self._parse_expression(expr.left)
        right_parsed_expr = self._parse_expression(expr.right)
        function_name = SQL_FUNCTIONS[type(expr)]
        signature, result_type, function_expression = self._parse_function_invokation(
            function_name, left_parsed_expr, right_parsed_expr
        )
        result_name = f"{function_name}_{left_parsed_expr.output_name}_{right_parsed_expr.output_name}_{next(self._counter)}"
        return ParsedSubstraitExpression(
            result_name,
            result_type,
            function_expression,
            left_parsed_expr.invoked_functions
            | right_parsed_expr.invoked_functions
            | {signature},
        )

    @DISPATCH_REGISTRY.register(sqlglot.expressions.Unary)
    def _parse_Unary(self, expr):
        argument_parsed_expr = self._parse_expression(expr.this)
        function_name = SQL_FUNCTIONS[type(expr)]
        signature, result_type, function_expression = self._parse_function_invokation(
            function_name, argument_parsed_expr
        )
        result_name = (
            f"{function_name}_{argument_parsed_expr.output_name}_{next(self._counter)}"
        )
        return ParsedSubstraitExpression(
            result_name,
            result_type,
            function_expression,
            argument_parsed_expr.invoked_functions | {signature},
        )

    def _parse_function_invokation(
        self, function_name, argument_parsed_expr, *additional_arguments
    ):
        """Generates a Substrait function invokation expression.

        The function invocation will be generated from the function name
        and the arguments as ParsedSubstraitExpression.

        Returns the function signature, the return type and the
        invokation expression itself.
        """
        arguments = [argument_parsed_expr] + list(additional_arguments)
        signature = self._functions_catalog.make_signature(
            function_name, proto_argtypes=[arg.type for arg in arguments]
        )

        registered_function = self._functions_catalog.lookup_function(signature)
        if registered_function is None:
            raise KeyError(f"Function not found: {signature}")

        return (
            registered_function.signature,
            registered_function.return_type,
            proto.Expression(
                scalar_function=proto.Expression.ScalarFunction(
                    function_reference=registered_function.function_anchor,
                    arguments=[
                        proto.FunctionArgument(value=arg.expression)
                        for arg in arguments
                    ],
                )
            ),
        )


class ParsedSubstraitExpression:
    """A Substrait expression that was parsed from a SQLGlot node.

    This stores the expression itself, with an associated output name
    in case it is required to emit projections.

    It also stores the type of the expression (i64, string, boolean, etc...)
    and the functions that the expression in going to invoke.
    """

    def __init__(self, output_name, type, expression, invoked_functions=None):
        self.expression = expression
        self.output_name = output_name
        self.type = type

        if invoked_functions is None:
            invoked_functions = set()
        self.invoked_functions = invoked_functions

    def duplicate(
        self, output_name=None, type=None, expression=None, invoked_functions=None
    ):
        return ParsedSubstraitExpression(
            output_name or self.output_name,
            type or self.type,
            expression or self.expression,
            invoked_functions or self.invoked_functions,
        )

    def __repr__(self):
        return f"<ParsedSubstraitExpression {self.output_name} {self.type}>"
