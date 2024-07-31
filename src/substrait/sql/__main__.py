import pathlib
import argparse

from substrait import proto
from .functions_catalog import FunctionsCatalog
from .extended_expression import parse_sql_extended_expression


def main():
    """Commandline tool to test the SQL to ExtendedExpression parser.

    Run as python -m substrait.sql first_name=String,surname=String,age=I32 "SELECT surname, age + 1 as next_birthday, age + 2 WHERE age = 32"
    """
    parser = argparse.ArgumentParser(
        description="Convert a SQL SELECT statement to an ExtendedExpression"
    )
    parser.add_argument("schema", type=str, help="Schema of the input data")
    parser.add_argument("sql", type=str, help="SQL SELECT statement")
    args = parser.parse_args()

    catalog = FunctionsCatalog()
    catalog.load_standard_extensions(
        pathlib.Path(__file__).parent.parent.parent.parent
        / "third_party"
        / "substrait"
        / "extensions",
    )
    schema = parse_schema(args.schema)
    projection_expr, filter_expr = parse_sql_extended_expression(
        catalog, schema, args.sql
    )

    print("---- SQL INPUT ----")
    print(args.sql)
    print("---- PROJECTION ----")
    print(projection_expr)
    print("---- FILTER ----")
    print(filter_expr)


def parse_schema(schema_string):
    """Parse Schema from a comma separated string of fieldname=fieldtype pairs.

    For example: "first_name=String,surname=String,age=I32"
    """
    types = []
    names = []

    fields = schema_string.split(",")
    for field in fields:
        fieldname, fieldtype = field.split("=")
        proto_type = getattr(proto.Type, fieldtype)
        names.append(fieldname)
        types.append(
            proto.Type(
                **{
                    fieldtype.lower(): proto_type(
                        nullability=proto.Type.Nullability.NULLABILITY_REQUIRED
                    )
                }
            )
        )
    return proto.NamedStruct(names=names, struct=proto.Type.Struct(types=types))


if __name__ == "__main__":
    main()
