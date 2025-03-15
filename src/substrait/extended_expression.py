import itertools
import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stp
import substrait.gen.proto.extended_expression_pb2 as stee
from substrait.utils import type_num_names


def column(name: str):
    def resolve(base_schema: stp.NamedStruct) -> stee.ExtendedExpression:
        column_index = list(base_schema.names).index(name)
        lengths = [type_num_names(t) for t in base_schema.struct.types]
        flat_indices = [0] + list(itertools.accumulate(lengths))[:-1]

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        selection=stalg.Expression.FieldReference(
                            root_reference=stalg.Expression.FieldReference.RootReference(),
                            direct_reference=stalg.Expression.ReferenceSegment(
                                struct_field=stalg.Expression.ReferenceSegment.StructField(
                                    field=flat_indices.index(column_index)
                                )
                            ),
                        )
                    )
                )
            ],
            base_schema=base_schema,
        )

    return resolve
