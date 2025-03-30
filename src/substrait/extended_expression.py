import itertools
import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stp
import substrait.gen.proto.extended_expression_pb2 as stee
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.function_registry import FunctionRegistry
from substrait.utils import type_num_names, merge_extension_uris, merge_extension_declarations
from substrait.type_inference import infer_extended_expression_schema
from typing import Callable, Any, Union

UnboundExpression = Callable[[stp.NamedStruct, FunctionRegistry], stee.ExtendedExpression]

def literal(value: Any, type: stp.Type, alias: str = None) -> UnboundExpression:
    """Builds a resolver for ExtendedExpression containing a literal expression"""
    def resolve(base_schema: stp.NamedStruct, registry: FunctionRegistry) -> stee.ExtendedExpression:
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
                    output_names=[alias if alias else f'literal_{kind}'],
                )
            ],
            base_schema=base_schema,
        )

    return resolve

def column(field: Union[str, int]):
    """Builds a resolver for ExtendedExpression containing a FieldReference expression
    
    Accepts either an index or a field name of a desired field.
    """
    def resolve(base_schema: stp.NamedStruct, registry: FunctionRegistry) -> stee.ExtendedExpression:
        if isinstance(field, str):
            column_index = list(base_schema.names).index(field)
            lengths = [type_num_names(t) for t in base_schema.struct.types]
            flat_indices = [0] + list(itertools.accumulate(lengths))[:-1]
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
                    output_names=list(base_schema.names)[names_start:names_end],
                )
            ],
            base_schema=base_schema,
        )

    return resolve

def scalar_function(uri: str, function: str, *expressions: UnboundExpression, alias: str = None):
    """Builds a resolver for ExtendedExpression containing a ScalarFunction expression"""
    def resolve(base_schema: stp.NamedStruct, registry: FunctionRegistry) -> stee.ExtendedExpression:
        bound_expressions: list[stee.ExtendedExpression] = [e(base_schema, registry) for e in expressions]

        expression_schemas = [infer_extended_expression_schema(b) for b in bound_expressions]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(uri, function, signature)
        
        if not func:
            raise Exception('')
        
        func_extension_uris = [
                ste.SimpleExtensionURI(
                    extension_uri_anchor=registry.lookup_uri(uri),
                    uri=uri
                )
            ]
        
        func_extensions = [
                ste.SimpleExtensionDeclaration(
                    extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                        extension_uri_reference=registry.lookup_uri(uri),
                        function_anchor=func[0].anchor,
                        name=function
                    )
                )
            ]

        extension_uris = merge_extension_uris(
            func_extension_uris,
            *[b.extension_uris for b in bound_expressions]
        )

        extensions = merge_extension_declarations(
            func_extensions,
            *[b.extensions for b in bound_expressions]
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
                                ) for e in bound_expressions
                            ],
                            output_type=func[1]
                        )
                    ),
                    output_names=[alias if alias else 'scalar_function'],
                )
            ],
            base_schema=base_schema,
            extension_uris=extension_uris,
            extensions=extensions
        )

    return resolve
