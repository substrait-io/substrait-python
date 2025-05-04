from typing import Any
from substrait.gen.proto import algebra_pb2 as stalg
from substrait.function_registry import FunctionRegistry
import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
from substrait.type_inference import infer_expression_type


class BoundExpression:
    def __init__(self, expression: stalg.Expression, parent_schema: stt.Type.Struct, alias: str, extensions: dict):
        self.expression = expression
        self.extensions = extensions
        self.parent_schema = parent_schema
        self.alias = alias

    def extensions(self):
        return self.extensions

    def dtype(self) -> stt.Type:
        return infer_expression_type(self.expression, self.parent_schema)

class UnboundExpression:
    def bind(self, df):
        pass
    
    def alias(self, alias: str):
        self.alias = alias
        return self
    

class UnboundLiteral(UnboundExpression):
    def __init__(self, value: Any, type: str):
        self.value = value
        self.type = type

    def bind(self, df) -> stalg.Expression:
        type = self.type
        value = self.value
        
        if type == "boolean":
            literal = stalg.Expression.Literal(boolean=value, nullable=True)
        elif type in ("i8", "int8"):
            literal = stalg.Expression.Literal(i8=value, nullable=True)
        elif type in ("i16", "int16"):
            literal = stalg.Expression.Literal(i16=value, nullable=True)
        elif type in ("i32", "int32"):
            literal = stalg.Expression.Literal(i32=value, nullable=True)
        elif type in ("i64", "int64"):
            literal = stalg.Expression.Literal(i64=value, nullable=True)
        elif type == "fp32":
            literal = stalg.Expression.Literal(fp32=value, nullable=True)
        elif type == "fp64":
            literal = stalg.Expression.Literal(fp64=value, nullable=True)
        elif type == "string":
            literal = stalg.Expression.Literal(string=value, nullable=True)
        else:
            raise Exception(f"Unknown literal type - {type}")

        return BoundExpression(
            expression=stalg.Expression(literal=literal),
            alias=self.alias,
            parent_schema=df.schema(),
            extensions={}
        )


class UnboundFieldReference(UnboundExpression):
    def __init__(self, column_name: str):
        self.column_name = column_name

    def bind(self, df) -> stalg.Expression:
        col_names = list(df.plan.relations[-1].root.names)

        return BoundExpression(
            expression=stalg.Expression(
                selection=stalg.Expression.FieldReference(
                    root_reference=stalg.Expression.FieldReference.RootReference(),
                    direct_reference=stalg.Expression.ReferenceSegment(
                        struct_field=stalg.Expression.ReferenceSegment.StructField(
                            field=col_names.index(self.column_name),
                        ),
                    ),
                ),
            ),
            alias=self.alias,
            parent_schema=df.schema(),
            extensions={}
        )

class UnboundScalarFunction(UnboundExpression):
    def __init__(self, uri: str, function: str, *expressions: UnboundExpression):
        self.uri = uri
        self.function = function
        self.expressions = expressions

    def bind(self, df):
        registry = FunctionRegistry()

        bound_expressions = [e.bind(df) for e in self.expressions]
        signature = [e.dtype() for e in bound_expressions]

        (func_entry, rtn) = registry.lookup_function(
            uri=self.uri,
            function_name=self.function,
            signature=signature,
        )

        return BoundExpression(
            expression=stalg.Expression(scalar_function=stalg.Expression.ScalarFunction(
                function_reference=func_entry.anchor,
                output_type=rtn,
                arguments=[
                    stalg.FunctionArgument(value=e.expression) for e in bound_expressions
                ],
            )),
            alias=self.alias,
            parent_schema=df.schema(),
            extensions={func_entry.uri: {str(func_entry): func_entry.anchor}}
        )