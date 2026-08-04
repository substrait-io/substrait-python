import substrait.algebra_pb2 as stalg
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import (
    EnumerationArgument,
    column,
    nested_struct,
    scalar_function,
)
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_extended_expression_schema


named_struct = stt.NamedStruct(
    names=["left", "right", "occurred_at"],
    struct=stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(
                precision_timestamp=stt.Type.PrecisionTimestamp(
                    precision=6,
                    nullability=stt.Type.NULLABILITY_REQUIRED,
                )
            ),
        ],
        nullability=stt.Type.NULLABILITY_REQUIRED,
    ),
)


def test_scalar_function_accepts_enumeration_arguments():
    registry = ExtensionRegistry()
    expression = scalar_function(
        "extension:io.substrait:functions_datetime",
        "extract",
        [EnumerationArgument("UNIX_TIME"), column("occurred_at")],
    )(named_struct, registry)

    function = expression.referred_expr[0].expression.scalar_function
    assert function.arguments[0] == stalg.FunctionArgument(enum="UNIX_TIME")
    assert function.arguments[1].HasField("value")
    assert function.output_type.WhichOneof("kind") == "i64"


def test_nested_struct_is_a_typed_scalar_expression():
    registry = ExtensionRegistry(load_default_extensions=False)
    expression = nested_struct([column("left"), column("right")])(
        named_struct, registry
    )

    inferred = infer_extended_expression_schema(expression, registry=registry)
    assert inferred.types[0].WhichOneof("kind") == "struct"
    assert [item.WhichOneof("kind") for item in inferred.types[0].struct.types] == [
        "i64",
        "string",
    ]
