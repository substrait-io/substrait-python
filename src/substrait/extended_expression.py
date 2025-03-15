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
        field_index = flat_indices.index(column_index)

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
