import pathlib

import sqlglot
import yaml

from substrait import proto


SQL_BINARY_FUNCTIONS = {
    # Arithmetic
    "add": "add",
    "div": "div",
    "mul": "mul",
    "sub": "sub",
    # Comparisons
    "eq": "equal",
}


def parse_sql_extended_expression(catalog, schema, sql):
    select = sqlglot.parse_one(sql)
    if not isinstance(select, sqlglot.expressions.Select):
        raise ValueError("a SELECT statement was expected")

    invoked_functions_projection, projections = _substrait_projection_from_sqlglot(
        catalog, schema, select.expressions
    )
    extension_uris, extensions = catalog.extensions_for_functions(
        invoked_functions_projection
    )
    projection_extended_expr = proto.ExtendedExpression(
        extension_uris=extension_uris,
        extensions=extensions,
        base_schema=schema,
        referred_expr=projections,
    )

    invoked_functions_filter, filter_expr = _substrait_expression_from_sqlglot(
        catalog, schema, select.find(sqlglot.expressions.Where).this
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


def _substrait_projection_from_sqlglot(catalog, schema, expressions):
    if not expressions:
        return set(), []

    # My understanding of ExtendedExpressions is that they are meant to directly
    # point to the Expression that ProjectRel would contain, so we don't actually
    # need a ProjectRel at all.
    """
    projection_sub = proto.ProjectRel(
        input=proto.Rel(
            read=proto.ReadRel(
                named_table=proto.ReadRel.NamedTable(names=["__table__"]),
                base_schema=schema,
            )
        ),
        expressions=[],
    )
    """

    substrait_expressions = []
    invoked_functions = set()
    for sqlexpr in expressions:
        output_names = []
        if isinstance(sqlexpr, sqlglot.expressions.Alias):
            output_names = [sqlexpr.output_name]
            sqlexpr = sqlexpr.this
        _, substrait_expr = _parse_expression(
            catalog, schema, sqlexpr, invoked_functions
        )
        substrait_expr_reference = proto.ExpressionReference(
            expression=substrait_expr, output_names=output_names
        )
        substrait_expressions.append(substrait_expr_reference)

    return invoked_functions, substrait_expressions


def _substrait_expression_from_sqlglot(catalog, schema, sqlglot_node):
    if not sqlglot_node:
        return set(), None

    invoked_functions = set()
    _, substrait_expr = _parse_expression(
        catalog, schema, sqlglot_node, invoked_functions
    )
    return invoked_functions, substrait_expr


def _parse_expression(catalog, schema, expr, invoked_functions):
    # TODO: Propagate up column names (output_names) so that the projections _always_ have an output_name
    if isinstance(expr, sqlglot.expressions.Literal):
        if expr.is_string:
            return proto.Type(string=proto.Type.String()), proto.Expression(
                literal=proto.Expression.Literal(string=expr.text)
            )
        elif expr.is_int:
            return proto.Type(i32=proto.Type.I32()), proto.Expression(
                literal=proto.Expression.Literal(i32=int(expr.name))
            )
        elif sqlglot.helper.is_float(expr.name):
            return proto.Type(fp32=proto.Type.FP32()), proto.Expression(
                literal=proto.Expression.Literal(float=float(expr.name))
            )
        else:
            raise ValueError(f"Unsupporter literal: {expr.text}")
    elif isinstance(expr, sqlglot.expressions.Column):
        column_name = expr.output_name
        schema_field = list(schema.names).index(column_name)
        schema_type = schema.struct.types[schema_field]
        return schema_type, proto.Expression(
            selection=proto.Expression.FieldReference(
                direct_reference=proto.Expression.ReferenceSegment(
                    struct_field=proto.Expression.ReferenceSegment.StructField(
                        field=schema_field
                    )
                )
            )
        )
    elif expr.key in SQL_BINARY_FUNCTIONS:
        left_type, left = _parse_expression(
            catalog, schema, expr.left, invoked_functions
        )
        right_type, right = _parse_expression(
            catalog, schema, expr.right, invoked_functions
        )
        function_name = SQL_BINARY_FUNCTIONS[expr.key]
        signature, result_type, function_expression = _parse_function_invokation(
            function_name, left_type, left, right_type, right
        )
        invoked_functions.add(signature)
        return result_type, function_expression
    else:
        raise ValueError(
            f"Unsupported expression in ExtendedExpression: '{expr.key}' -> {expr}"
        )


def _parse_function_invokation(function_name, left_type, left, right_type, right):
    signature = f"{function_name}:{left_type.WhichOneof('kind')}_{right_type.WhichOneof('kind')}"
    try:
        function_anchor = catalog.function_anchor(signature)
    except KeyError:
        # not function found with the exact types, try any1_any1 version
        signature = f"{function_name}:any1_any1"
        function_anchor = catalog.function_anchor(signature)
    return (
        signature,
        left_type,
        proto.Expression(
            scalar_function=proto.Expression.ScalarFunction(
                function_reference=function_anchor,
                arguments=[
                    proto.FunctionArgument(value=left),
                    proto.FunctionArgument(value=right),
                ],
            )
        ),
    )


class FunctionsCatalog:
    STANDARD_EXTENSIONS = (
        "/functions_aggregate_approx.yaml",
        "/functions_aggregate_generic.yaml",
        "/functions_arithmetic.yaml",
        "/functions_arithmetic_decimal.yaml",
        "/functions_boolean.yaml",
        "/functions_comparison.yaml",
        "/functions_datetime.yaml",
        "/functions_geometry.yaml",
        "/functions_logarithmic.yaml",
        "/functions_rounding.yaml",
        "/functions_set.yaml",
        "/functions_string.yaml",
    )

    def __init__(self):
        self._declarations = {}
        self._registered_extensions = {}
        self._functions = {}

    def load_standard_extensions(self, dirpath):
        for ext in self.STANDARD_EXTENSIONS:
            self.load(dirpath, ext)

    def load(self, dirpath, filename):
        with open(pathlib.Path(dirpath) / filename.strip("/")) as f:
            sections = yaml.safe_load(f)

        loaded_functions = set()
        for functions in sections.values():
            for function in functions:
                function_name = function["name"]
                for impl in function.get("impls", []):
                    argtypes = [t.get("value", "unknown") for t in impl.get("args", [])]
                    if not argtypes:
                        signature = function_name
                    else:
                        signature = f"{function_name}:{'_'.join(argtypes)}"
                    self._declarations[signature] = filename
                    loaded_functions.add(signature)

        self._register_extensions(filename, loaded_functions)

    def _register_extensions(self, extension_uri, loaded_functions):
        if extension_uri not in self._registered_extensions:
            ext_anchor_id = len(self._registered_extensions) + 1
            self._registered_extensions[extension_uri] = proto.SimpleExtensionURI(
                extension_uri_anchor=ext_anchor_id, uri=extension_uri
            )

        for function in loaded_functions:
            if function in self._functions:
                extensions_by_anchor = self.extension_uris_by_anchor
                function = self._functions[function]
                function_extension = extensions_by_anchor[
                    function.extension_uri_reference
                ].uri
                continue
                raise ValueError(
                    f"Duplicate function definition: {function} from {extension_uri}, already loaded from {function_extension}"
                )
            extension_anchor = self._registered_extensions[
                extension_uri
            ].extension_uri_anchor
            function_anchor = len(self._functions) + 1
            self._functions[function] = (
                proto.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=extension_anchor,
                    name=function,
                    function_anchor=function_anchor,
                )
            )

    @property
    def extension_uris_by_anchor(self):
        return {
            ext.extension_uri_anchor: ext
            for ext in self._registered_extensions.values()
        }

    @property
    def extension_uris(self):
        return list(self._registered_extensions.values())

    @property
    def extensions(self):
        return list(self._functions.values())

    def function_anchor(self, function):
        return self._functions[function].function_anchor

    def extensions_for_functions(self, functions):
        uris_anchors = set()
        extensions = []
        for f in functions:
            ext = self._functions[f]
            uris_anchors.add(ext.extension_uri_reference)
            extensions.append(proto.SimpleExtensionDeclaration(extension_function=ext))

        uris_by_anchor = self.extension_uris_by_anchor
        extension_uris = [uris_by_anchor[uri_anchor] for uri_anchor in uris_anchors]
        return extension_uris, extensions


catalog = FunctionsCatalog()
catalog.load_standard_extensions(
    pathlib.Path(__file__).parent.parent / "third_party" / "substrait" / "extensions",
)
schema = proto.NamedStruct(
    names=["first_name", "surname", "age"],
    struct=proto.Type.Struct(
        types=[
            proto.Type(
                string=proto.Type.String(
                    nullability=proto.Type.Nullability.NULLABILITY_REQUIRED
                )
            ),
            proto.Type(
                string=proto.Type.String(
                    nullability=proto.Type.Nullability.NULLABILITY_REQUIRED
                )
            ),
            proto.Type(
                i32=proto.Type.I32(
                    nullability=proto.Type.Nullability.NULLABILITY_REQUIRED
                )
            ),
        ]
    ),
)

if __name__ == '__main__':
    sql = "SELECT surname, age + 1 as next_birthday WHERE age = 32"
    projection_expr, filter_expr = parse_sql_extended_expression(catalog, schema, sql)
    print("---- SQL INPUT ----")
    print(sql)
    print("---- PROJECTION ----")
    print(projection_expr)
    print("---- FILTER ----")
    print(filter_expr)
    # parse_extended_expression("INSERT INTO table VALUES(1, 2, 3)")
