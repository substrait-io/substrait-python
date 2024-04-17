import pathlib

from substrait import proto
from .functions_catalog import FunctionsCatalog
from .extended_expression import parse_sql_extended_expression

catalog = FunctionsCatalog()
catalog.load_standard_extensions(
    pathlib.Path(__file__).parent.parent.parent.parent / "third_party" / "substrait" / "extensions",
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

sql = "SELECT surname, age + 1 as next_birthday WHERE age = 32"
projection_expr, filter_expr = parse_sql_extended_expression(catalog, schema, sql)
print("---- SQL INPUT ----")
print(sql)
print("---- PROJECTION ----")
print(projection_expr)
print("---- FILTER ----")
print(filter_expr)
# parse_extended_expression("INSERT INTO table VALUES(1, 2, 3)")