# Install pyarrow before running this example
# /// script
# dependencies = [
#   "pyarrow==20.0.0",
#   "substrait[extensions] @ file:///${PROJECT_ROOT}/"
# ]
# ///
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.substrait as pa_substrait
import substrait
from substrait.builders.plan import project, read_named_table

arrow_schema = pa.schema([pa.field("x", pa.int32()), pa.field("y", pa.int32())])

substrait_schema = (
    pa_substrait.serialize_schema(arrow_schema).to_pysubstrait().base_schema
)

substrait_expr = pa_substrait.serialize_expressions(
    exprs=[pc.field("x") + pc.field("y")], names=["total"], schema=arrow_schema
)

pysubstrait_expr = substrait.proto.ExtendedExpression.FromString(bytes(substrait_expr))

table = read_named_table("example", substrait_schema)
table = project(table, expressions=[pysubstrait_expr])(None)
print(table)
