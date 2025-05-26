import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.extended_expression_pb2 as stee
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp


def infer_literal_type(literal: stalg.Expression.Literal) -> stt.Type:
    literal_type = literal.WhichOneof("literal_type")

    nullability = (
        stt.Type.Nullability.NULLABILITY_NULLABLE
        if literal.nullable
        else stt.Type.Nullability.NULLABILITY_REQUIRED
    )

    if literal_type == "boolean":
        return stt.Type(bool=stt.Type.Boolean(nullability=nullability))
    elif literal_type == "i8":
        return stt.Type(i8=stt.Type.I8(nullability=nullability))
    elif literal_type == "i16":
        return stt.Type(i16=stt.Type.I16(nullability=nullability))
    elif literal_type == "i32":
        return stt.Type(i32=stt.Type.I32(nullability=nullability))
    elif literal_type == "i64":
        return stt.Type(i64=stt.Type.I64(nullability=nullability))
    elif literal_type == "fp32":
        return stt.Type(fp32=stt.Type.FP32(nullability=nullability))
    elif literal_type == "fp64":
        return stt.Type(fp64=stt.Type.FP64(nullability=nullability))
    elif literal_type == "string":
        return stt.Type(string=stt.Type.String(nullability=nullability))
    elif literal_type == "binary":
        return stt.Type(binary=stt.Type.Binary(nullability=nullability))
    elif literal_type == "timestamp":
        return stt.Type(timestamp=stt.Type.Timestamp(nullability=nullability))
    elif literal_type == "date":
        return stt.Type(date=stt.Type.Date(nullability=nullability))
    elif literal_type == "time":
        return stt.Type(time=stt.Type.Time(nullability=nullability))
    elif literal_type == "interval_year_to_month":
        return stt.Type(interval_year=stt.Type.IntervalYear(nullability=nullability))
    elif literal_type == "interval_day_to_second":
        return stt.Type(
            interval_day=stt.Type.IntervalDay(
                precision=literal.interval_day_to_second.precision,
                nullability=nullability,
            )
        )
    elif literal_type == "interval_compound":
        return stt.Type(
            interval_compound=stt.Type.IntervalCompound(
                nullability=nullability,
                precision=literal.interval_compound.interval_day_to_second.precision,
            )
        )
    elif literal_type == "fixed_char":
        return stt.Type(
            fixed_char=stt.Type.FixedChar(
                length=len(literal.fixed_char), nullability=nullability
            )
        )
    elif literal_type == "var_char":
        return stt.Type(
            varchar=stt.Type.VarChar(
                length=literal.var_char.length, nullability=nullability
            )
        )
    elif literal_type == "fixed_binary":
        return stt.Type(
            fixed_binary=stt.Type.FixedBinary(
                length=len(literal.fixed_binary), nullability=nullability
            )
        )
    elif literal_type == "decimal":
        return stt.Type(
            decimal=stt.Type.Decimal(
                scale=literal.decimal.scale,
                precision=literal.decimal.precision,
                nullability=nullability,
            )
        )
    elif literal_type == "precision_timestamp":
        return stt.Type(
            precision_timestamp=stt.Type.PrecisionTimestamp(
                precision=literal.precision_timestamp.precision, nullability=nullability
            )
        )
    elif literal_type == "precision_timestamp_tz":
        return stt.Type(
            precision_timestamp_tz=stt.Type.PrecisionTimestampTZ(
                precision=literal.precision_timestamp_tz.precision,
                nullability=nullability,
            )
        )
    elif literal_type == "struct":
        return stt.Type(
            struct=stt.Type.Struct(
                types=[infer_literal_type(f) for f in literal.struct.fields],
                nullability=nullability,
            )
        )
    elif literal_type == "map":
        return stt.Type(
            map=stt.Type.Map(
                key=infer_literal_type(literal.map.key_values[0].key),
                value=infer_literal_type(literal.map.key_values[0].value),
                nullability=nullability,
            )
        )
    elif literal_type == "timestamp_tz":
        return stt.Type(timestamp_tz=stt.Type.TimestampTZ(nullability=nullability))
    elif literal_type == "uuid":
        return stt.Type(uuid=stt.Type.UUID(nullability=nullability))
    elif literal_type == "null":
        return literal.null
    elif literal_type == "list":
        return stt.Type(
            list=stt.Type.List(
                type=infer_literal_type(literal.list.values[0]), nullability=nullability
            )
        )
    elif literal_type == "empty_list":
        return stt.Type(list=literal.empty_list)
    elif literal_type == "empty_map":
        return stt.Type(map=literal.empty_map)
    else:
        raise Exception(f"Unknown literal_type {literal_type}")


def infer_nested_type(nested: stalg.Expression.Nested) -> stt.Type:
    nested_type = nested.WhichOneof("nested_type")

    nullability = (
        stt.Type.Nullability.NULLABILITY_NULLABLE
        if nested.nullable
        else stt.Type.Nullability.NULLABILITY_REQUIRED
    )

    if nested_type == "struct":
        return stt.Type(
            struct=stt.Type.Struct(
                types=[infer_expression_type(f) for f in nested.struct.fields],
                nullability=nullability,
            )
        )
    elif nested_type == "list":
        return stt.Type(
            list=stt.Type.List(
                type=infer_expression_type(nested.list.values[0]),
                nullability=nullability,
            )
        )
    elif nested_type == "map":
        return stt.Type(
            map=stt.Type.Map(
                key=infer_expression_type(nested.map.key_values[0].key),
                value=infer_expression_type(nested.map.key_values[0].value),
                nullability=nullability,
            )
        )
    else:
        raise Exception(f"Unknown nested_type {nested_type}")


def infer_expression_type(
    expression: stalg.Expression, parent_schema: stt.Type.Struct
) -> stt.Type:
    rex_type = expression.WhichOneof("rex_type")
    if rex_type == "selection":
        root_type = expression.selection.WhichOneof("root_type")
        assert root_type == "root_reference"

        reference_type = expression.selection.WhichOneof("reference_type")

        if reference_type == "direct_reference":
            segment = expression.selection.direct_reference

            segment_reference_type = segment.WhichOneof("reference_type")

            if segment_reference_type == "struct_field":
                return parent_schema.types[segment.struct_field.field]
            else:
                raise Exception(f"Unknown reference_type {reference_type}")
        else:
            raise Exception(f"Unknown reference_type {reference_type}")

    elif rex_type == "literal":
        return infer_literal_type(expression.literal)
    elif rex_type == "scalar_function":
        return expression.scalar_function.output_type
    elif rex_type == "window_function":
        return expression.window_function.output_type
    elif rex_type == "if_then":
        return infer_expression_type(expression.if_then.ifs[0].then)
    elif rex_type == "switch_expression":
        return infer_expression_type(expression.switch_expression.ifs[0].then)
    elif rex_type == "cast":
        return expression.cast.type
    elif rex_type == "singular_or_list" or rex_type == "multi_or_list":
        return stt.Type(
            bool=stt.Type.Boolean(nullability=stt.Type.Nullability.NULLABILITY_NULLABLE)
        )
    elif rex_type == "nested":
        return infer_nested_type(expression.nested)
    elif rex_type == "subquery":
        subquery_type = expression.subquery.WhichOneof("subquery_type")

        if subquery_type == "scalar":
            scalar_rel = infer_rel_schema(expression.subquery.scalar.input)
            return scalar_rel.types[0]
        elif (
            subquery_type == "in_predicate"
            or subquery_type == "set_comparison"
            or subquery_type == "set_predicate"
        ):
            stt.Type.Boolean(
                nullability=stt.Type.Nullability.NULLABILITY_NULLABLE
            )  # can this be a null?
        else:
            raise Exception(f"Unknown subquery_type {subquery_type}")
    else:
        raise Exception(f"Unknown rex_type {rex_type}")


def infer_extended_expression_schema(ee: stee.ExtendedExpression) -> stt.Type.Struct:
    exprs = [e for e in ee.referred_expr]

    types = [infer_expression_type(e.expression, ee.base_schema.struct) for e in exprs]

    return stt.Type.Struct(
        types=types,
        nullability=stt.Type.NULLABILITY_REQUIRED,
    )


def infer_rel_schema(rel: stalg.Rel) -> stt.Type.Struct:
    rel_type = rel.WhichOneof("rel_type")

    if rel_type == "read":
        (common, struct) = (rel.read.common, rel.read.base_schema.struct)
    elif rel_type == "filter":
        (common, struct) = (rel.filter.common, infer_rel_schema(rel.filter.input))
    elif rel_type == "fetch":
        (common, struct) = (rel.fetch.common, infer_rel_schema(rel.fetch.input))
    elif rel_type == "aggregate":
        parent_schema = infer_rel_schema(rel.aggregate.input)
        grouping_types = [
            infer_expression_type(g, parent_schema)
            for g in rel.aggregate.grouping_expressions
        ]
        measure_types = [m.measure.output_type for m in rel.aggregate.measures]

        grouping_identifier_types = (
            []
            if len(rel.aggregate.groupings) <= 1
            else [stt.Type(i32=stt.Type.I32(nullability=stt.Type.NULLABILITY_REQUIRED))]
        )

        raw_schema = stt.Type.Struct(
            types=grouping_types + measure_types + grouping_identifier_types,
            nullability=parent_schema.nullability,
        )

        (common, struct) = (rel.aggregate.common, raw_schema)
    elif rel_type == "sort":
        (common, struct) = (rel.sort.common, infer_rel_schema(rel.sort.input))
    elif rel_type == "project":
        parent_schema = infer_rel_schema(rel.project.input)
        expression_types = [
            infer_expression_type(e, parent_schema) for e in rel.project.expressions
        ]
        raw_schema = stt.Type.Struct(
            types=list(parent_schema.types) + expression_types,
            nullability=parent_schema.nullability,
        )

        (common, struct) = (rel.project.common, raw_schema)
    elif rel_type == "set":
        (common, struct) = (rel.fetch.common, infer_rel_schema(rel.set.inputs[0]))
    elif rel_type == "cross":
        left_schema = infer_rel_schema(rel.cross.left)
        right_schema = infer_rel_schema(rel.cross.right)

        raw_schema = stt.Type.Struct(
            types=list(left_schema.types) + list(right_schema.types),
            nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
        )

        (common, struct) = (rel.cross.common, raw_schema)
    elif rel_type == "join":
        if rel.join.type in [
            stalg.JoinRel.JOIN_TYPE_INNER,
            stalg.JoinRel.JOIN_TYPE_OUTER,
            stalg.JoinRel.JOIN_TYPE_LEFT,
            stalg.JoinRel.JOIN_TYPE_RIGHT,
            stalg.JoinRel.JOIN_TYPE_LEFT_SINGLE,
            stalg.JoinRel.JOIN_TYPE_RIGHT_SINGLE,
        ]:
            raw_schema = stt.Type.Struct(
                types=list(infer_rel_schema(rel.join.left).types)
                + list(infer_rel_schema(rel.join.right).types),
                nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
            )
        elif rel.join.type in [
            stalg.JoinRel.JOIN_TYPE_LEFT_ANTI,
            stalg.JoinRel.JOIN_TYPE_LEFT_SEMI,
        ]:
            raw_schema = stt.Type.Struct(
                types=infer_rel_schema(rel.join.left).types,
                nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
            )
        elif rel.join.type in [
            stalg.JoinRel.JOIN_TYPE_RIGHT_ANTI,
            stalg.JoinRel.JOIN_TYPE_RIGHT_SEMI,
        ]:
            raw_schema = stt.Type.Struct(
                types=infer_rel_schema(rel.join.right).types,
                nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
            )
        elif rel.join.type in [
            stalg.JoinRel.JOIN_TYPE_LEFT_MARK,
            stalg.JoinRel.JOIN_TYPE_RIGHT_MARK,
        ]:
            raw_schema = stt.Type.Struct(
                types=list(infer_rel_schema(rel.join.left).types)
                + list(infer_rel_schema(rel.join.right).types)
                + [
                    stt.Type(
                        bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)
                    )
                ],
                nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
            )
        else:
            raise Exception(f"Unhandled join_type {rel.join.type}")

        (common, struct) = (rel.join.common, raw_schema)
    else:
        raise Exception(f"Unhandled rel_type {rel_type}")

    emit_kind = common.WhichOneof("emit_kind") or "direct"

    if emit_kind == "direct":
        return struct
    else:
        return stt.Type.Struct(
            types=[struct.types[i] for i in common.emit.output_mapping],
            nullability=struct.nullability,
        )


def infer_plan_schema(plan: stp.Plan) -> stt.NamedStruct:
    schema = infer_rel_schema(plan.relations[-1].root.input)

    return stt.NamedStruct(names=plan.relations[-1].root.names, struct=schema)
