from .dataframe import DataFrame
from typing import Any

import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
from substrait.dataframe.expression import UnboundExpression, UnboundFieldReference, UnboundLiteral, UnboundScalarFunction

def literal(value: Any, type: str):
    return UnboundLiteral(value, type)

def col(column_name: str):
    return UnboundFieldReference(column_name=column_name)

def scalar_function(uri: str, function: str, *expressions: UnboundExpression):
    return UnboundScalarFunction(uri, function, *expressions)

def pyarrow_to_substrait_type(pa_type):
    import pyarrow

    if pa_type == pyarrow.int64():
        return stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_NULLABLE))
    elif pa_type == pyarrow.float64():
        return stt.Type(fp64=stt.Type.FP64(nullability=stt.Type.NULLABILITY_NULLABLE))
    elif pa_type == pyarrow.string():
        return stt.Type(
            string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)
        )


def named_table(name, conn):
    pa_schema = conn.adbc_get_table_schema(name)

    column_names = pa_schema.names
    struct = stt.Type.Struct(
        types=[
            pyarrow_to_substrait_type(pa_schema.field(c).type) for c in column_names
        ],
        nullability=stt.Type.Nullability.NULLABILITY_NULLABLE,
    )

    schema = stt.NamedStruct(
        names=column_names,
        struct=struct,
    )

    rel = stalg.Rel(
        read=stalg.ReadRel(
            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
            base_schema=schema,
            named_table=stalg.ReadRel.NamedTable(names=[name]),
        )
    )

    plan = stp.Plan(
        relations=[
            stp.PlanRel(root=stalg.RelRoot(input=rel, names=column_names))
        ]
    )

    return DataFrame(plan=plan)