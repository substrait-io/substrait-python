import itertools
import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stp
import substrait.gen.proto.extended_expression_pb2 as stee
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.extension_registry import ExtensionRegistry
from substrait.utils import type_num_names, merge_extension_uris, merge_extension_declarations
from substrait.type_inference import infer_extended_expression_schema
from typing import Callable, Any, Union, Iterable

UnboundExtendedExpression = Callable[[stp.NamedStruct, ExtensionRegistry], stee.ExtendedExpression]

def _alias_or_inferred(
        alias: Union[Iterable[str], str],
        op: str,
        args: Iterable[str],
        ):
    if alias:
        return [alias] if isinstance(alias, str) else alias
    else:
        return [f'{op}({",".join(args)})']

def literal(value: Any, type: stp.Type, alias: Union[Iterable[str], str] = None) -> UnboundExtendedExpression:
    """Builds a resolver for ExtendedExpression containing a literal expression"""
    def resolve(base_schema: stp.NamedStruct, registry: ExtensionRegistry) -> stee.ExtendedExpression:
        kind = type.WhichOneof('kind')

        if kind == "bool":
            literal = stalg.Expression.Literal(boolean=value, nullable=type.bool.nullability == stp.Type.NULLABILITY_NULLABLE)
        elif kind == "i8":
            literal = stalg.Expression.Literal(i8=value, nullable=type.i8.nullability == stp.Type.NULLABILITY_NULLABLE)
        elif kind == "i16":
            literal = stalg.Expression.Literal(i16=value, nullable=type.i16.nullability == stp.Type.NULLABILITY_NULLABLE)
        elif kind == "i32":
            literal = stalg.Expression.Literal(i32=value, nullable=type.i32.nullability == stp.Type.NULLABILITY_NULLABLE)
        elif kind == "i64":
            literal = stalg.Expression.Literal(i64=value, nullable=type.i64.nullability == stp.Type.NULLABILITY_NULLABLE)
        elif kind == "fp32":
            literal = stalg.Expression.Literal(fp32=value, nullable=type.fp32.nullability == stp.Type.NULLABILITY_NULLABLE)
        elif kind == "fp64":
            literal = stalg.Expression.Literal(fp64=value, nullable=type.fp64.nullability == stp.Type.NULLABILITY_NULLABLE)
        elif kind == "string":
            literal = stalg.Expression.Literal(string=value, nullable=type.string.nullability == stp.Type.NULLABILITY_NULLABLE)
        else:
            raise Exception(f"Unknown literal type - {type}")

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        literal=literal
                    ),
                    output_names=_alias_or_inferred(alias, 'Literal', [str(value)])
                )
            ],
            base_schema=base_schema,
        )

    return resolve

def column(field: Union[str, int], alias: Union[Iterable[str], str] = None):
    """Builds a resolver for ExtendedExpression containing a FieldReference expression

    Accepts either an index or a field name of a desired field.
    """
    alias = [alias] if alias and isinstance(alias, str) else alias

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        lengths = [type_num_names(t) for t in base_schema.struct.types]
        flat_indices = [0] + list(itertools.accumulate(lengths))[:-1]

        if isinstance(field, str):
            column_index = list(base_schema.names).index(field)
            field_index = flat_indices.index(column_index)
        else:
            field_index = field

        names_start = flat_indices[field_index]
        names_end = (
            flat_indices[field_index + 1]
            if len(flat_indices) > field_index + 1
            else None
        )

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        selection=stalg.Expression.FieldReference(
                            root_reference=stalg.Expression.FieldReference.RootReference(),
                            direct_reference=stalg.Expression.ReferenceSegment(
                                struct_field=stalg.Expression.ReferenceSegment.StructField(
                                    field=field_index
                                )
                            ),
                        )
                    ),
                    output_names=list(base_schema.names)[names_start:names_end]
                    if not alias
                    else alias,
                )
            ],
            base_schema=base_schema,
        )

    return resolve

def scalar_function(
    uri: str, function: str, *expressions: UnboundExtendedExpression, alias: Union[Iterable[str], str] = None
):
    """Builds a resolver for ExtendedExpression containing a ScalarFunction expression"""
    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            e(base_schema, registry) for e in expressions
        ]

        expression_schemas = [
            infer_extended_expression_schema(b) for b in bound_expressions
        ]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(uri, function, signature)

        if not func:
            raise Exception(f"Unknown function {function} for {signature}")

        func_extension_uris = [
            ste.SimpleExtensionURI(
                extension_uri_anchor=registry.lookup_uri(uri), uri=uri
            )
        ]

        func_extensions = [
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=registry.lookup_uri(uri),
                    function_anchor=func[0].anchor,
                    name=function,
                )
            )
        ]

        extension_uris = merge_extension_uris(
            func_extension_uris, *[b.extension_uris for b in bound_expressions]
        )

        extensions = merge_extension_declarations(
            func_extensions, *[b.extensions for b in bound_expressions]
        )

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        scalar_function=stalg.Expression.ScalarFunction(
                            function_reference=func[0].anchor,
                            arguments=[
                                stalg.FunctionArgument(
                                    value=e.referred_expr[0].expression
                                )
                                for e in bound_expressions
                            ],
                            output_type=func[1],
                        )
                    ),
                    output_names=_alias_or_inferred(alias, function, [e.referred_expr[0].output_names[0] for e in bound_expressions]),
                )
            ],
            base_schema=base_schema,
            extension_uris=extension_uris,
            extensions=extensions,
        )

    return resolve

def aggregate_function(
    uri: str, function: str, *expressions: UnboundExtendedExpression, alias: Union[Iterable[str], str] = None
):
    """Builds a resolver for ExtendedExpression containing a AggregateFunction measure"""
    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            e(base_schema, registry) for e in expressions
        ]

        expression_schemas = [
            infer_extended_expression_schema(b) for b in bound_expressions
        ]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(uri, function, signature)

        if not func:
            raise Exception(f"Unknown function {function} for {signature}")

        func_extension_uris = [
            ste.SimpleExtensionURI(
                extension_uri_anchor=registry.lookup_uri(uri), uri=uri
            )
        ]

        func_extensions = [
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=registry.lookup_uri(uri),
                    function_anchor=func[0].anchor,
                    name=function,
                )
            )
        ]

        extension_uris = merge_extension_uris(
            func_extension_uris, *[b.extension_uris for b in bound_expressions]
        )

        extensions = merge_extension_declarations(
            func_extensions, *[b.extensions for b in bound_expressions]
        )

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    measure=stalg.AggregateFunction(
                        function_reference=func[0].anchor,
                        arguments=[
                            stalg.FunctionArgument(value=e.referred_expr[0].expression)
                            for e in bound_expressions
                        ],
                        output_type=func[1],
                    ),
                    output_names=_alias_or_inferred(alias, 'IfThen', [e.referred_expr[0].output_names[0] for e in bound_expressions]),
                )
            ],
            base_schema=base_schema,
            extension_uris=extension_uris,
            extensions=extensions,
        )

    return resolve


# TODO bounds, sorts
def window_function(
    uri: str,
    function: str,
    *expressions: UnboundExtendedExpression,
    partitions: Iterable[UnboundExtendedExpression] = [],
    alias: Union[Iterable[str], str] = None
):
    """Builds a resolver for ExtendedExpression containing a WindowFunction expression"""
    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            e(base_schema, registry) for e in expressions
        ]

        bound_partitions = [e(base_schema, registry) for e in partitions]

        expression_schemas = [
            infer_extended_expression_schema(b) for b in bound_expressions
        ]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(uri, function, signature)

        if not func:
            raise Exception(f"Unknown function {function} for {signature}")

        func_extension_uris = [
            ste.SimpleExtensionURI(
                extension_uri_anchor=registry.lookup_uri(uri), uri=uri
            )
        ]

        func_extensions = [
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=registry.lookup_uri(uri),
                    function_anchor=func[0].anchor,
                    name=function,
                )
            )
        ]

        extension_uris = merge_extension_uris(
            func_extension_uris,
            *[b.extension_uris for b in bound_expressions],
            *[b.extension_uris for b in bound_partitions],
        )

        extensions = merge_extension_declarations(
            func_extensions,
            *[b.extensions for b in bound_expressions],
            *[b.extensions for b in bound_partitions],
        )

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        window_function=stalg.Expression.WindowFunction(
                            function_reference=func[0].anchor,
                            arguments=[
                                stalg.FunctionArgument(
                                    value=e.referred_expr[0].expression
                                )
                                for e in bound_expressions
                            ],
                            output_type=func[1],
                            partitions=[
                                e.referred_expr[0].expression for e in bound_partitions
                            ],
                        )
                    ),
                    output_names=_alias_or_inferred(alias, function, [e.referred_expr[0].output_names[0] for e in bound_expressions]),
                )
            ],
            base_schema=base_schema,
            extension_uris=extension_uris,
            extensions=extensions,
        )

    return resolve


def if_then(ifs: Iterable[tuple[UnboundExtendedExpression, UnboundExtendedExpression]], _else: UnboundExtendedExpression, alias: Union[Iterable[str], str] = None):
    """Builds a resolver for ExtendedExpression containing an IfThen expression"""
    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_ifs = [
            (if_clause[0](base_schema, registry), if_clause[1](base_schema, registry))
            for if_clause in ifs
        ]

        bound_else = _else(base_schema, registry)

        extension_uris = merge_extension_uris(
            *[b[0].extension_uris for b in bound_ifs],
            *[b[1].extension_uris for b in bound_ifs],
            bound_else.extension_uris
        )

        extensions = merge_extension_declarations(
            *[b[0].extensions for b in bound_ifs],
            *[b[1].extensions for b in bound_ifs],
            bound_else.extensions
        )

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        if_then=stalg.Expression.IfThen(**{
                            'ifs': [
                                stalg.Expression.IfThen.IfClause(**{
                                    'if': if_clause[0].referred_expr[0].expression,
                                    'then': if_clause[1].referred_expr[0].expression,
                                })    
                                for if_clause in bound_ifs
                            ],
                            'else': bound_else.referred_expr[0].expression
                        })
                    ),
                    output_names=_alias_or_inferred(alias, 'IfThen', [a for e in bound_ifs for a in [e[0].referred_expr[0].output_names[0], e[1].referred_expr[0].output_names[0]]]
                                                    + [bound_else.referred_expr[0].output_names[0]]
                                                    ),
                )
            ],
            base_schema=base_schema,
            extension_uris=extension_uris,
            extensions=extensions,
        )

    return resolve
