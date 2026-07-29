import contextlib
import contextvars

import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.utils import iter_plan_rels, plan_subtrees, rel_anchor_of


class _SubtreeScope:
    """The shared-subtree list a ``ReferenceRel`` resolves against, with per-ordinal
    schema memoization and cycle detection.

    A ``ReferenceRel``'s schema is that of ``subtrees[subtree_ordinal]``, and a
    subtree may itself reference an earlier one, so resolution recurses. Memoizing
    each ordinal's schema avoids re-inferring a subtree referenced from many places
    (otherwise exponential for chained cached self-joins), and the in-progress set
    turns a cyclic/self reference in a malformed plan into a clear error rather than
    a ``RecursionError``. Behaves as a read-only sequence (``len`` / indexing) so
    callers that pass a plain list of subtrees still work unchanged.
    """

    __slots__ = ("_rels", "_schemas", "_resolving")

    def __init__(self, rels):
        self._rels = list(rels)
        self._schemas: dict = {}
        self._resolving: set = set()

    def __len__(self):
        return len(self._rels)

    def __getitem__(self, ordinal):
        return self._rels[ordinal]

    def schema_of(self, ordinal, registry):
        if ordinal in self._schemas:
            return self._schemas[ordinal]
        if ordinal in self._resolving:
            raise Exception(
                f"ReferenceRel subtree_ordinal {ordinal} forms a cycle; a shared "
                "subtree cannot reference itself directly or transitively"
            )
        self._resolving.add(ordinal)
        try:
            schema = infer_rel_schema(
                self._rels[ordinal], registry=registry, subtrees=self
            )
        finally:
            self._resolving.discard(ordinal)
        self._schemas[ordinal] = schema
        return schema


class _AnchorScope:
    """Map of ``RelCommon.rel_anchor`` -> the relation carrying it, with lazy
    per-anchor schema memoization, for resolving id-based outer references
    (``OuterReference.rel_reference``).

    A ``rel_reference`` names the anchor of the relation the reference is rooted on
    and resolves against that relation's schema: a ``LateralJoinRel`` anchor denotes
    the *current left row* (its left input's schema), any other anchor its output
    schema. Resolution is lazy (only referenced anchors are inferred) and memoized;
    an in-progress set turns a malformed cyclic reference into a clear error rather
    than a ``RecursionError``. Anchored relations are inferred with the plan's
    ``_SubtreeScope`` in scope so an anchor on a shared subtree still resolves.

    ``register`` pre-binds an anchor to an already-known schema, for a correlated
    sub-tree whose anchoring relation is not yet assembled (a lateral join's right
    input, at build or inference time). ``parent`` chains to an enclosing scope so
    nested correlations still resolve outer anchors.
    """

    __slots__ = ("_rels", "_subtrees", "_schemas", "_resolving", "_parent")

    def __init__(self, rels: dict, subtrees, *, parent=None):
        self._rels = rels
        self._subtrees = subtrees
        self._schemas: dict = {}
        self._resolving: set = set()
        self._parent = parent

    def register(self, anchor, struct: stt.Type.Struct) -> None:
        """Pre-bind ``anchor`` to an already-known schema."""
        self._schemas[anchor] = struct

    def schema_of(self, anchor, registry) -> stt.Type.Struct:
        if anchor in self._schemas:
            return self._schemas[anchor]
        if anchor not in self._rels:
            if self._parent is not None:
                return self._parent.schema_of(anchor, registry)
            raise Exception(f"outer reference to unknown rel_anchor {anchor}")
        if anchor in self._resolving:
            raise Exception(
                f"outer reference rel_anchor {anchor} forms a resolution cycle"
            )
        self._resolving.add(anchor)
        try:
            rel = self._rels[anchor]
            # A lateral-join anchor denotes the current left row, not the join's
            # own output; every other anchor resolves against its output schema.
            target = (
                rel.lateral_join.left
                if rel.WhichOneof("rel_type") == "lateral_join"
                else rel
            )
            struct = infer_rel_schema(
                target, registry=registry, subtrees=self._subtrees
            )
        finally:
            self._resolving.discard(anchor)
        self._schemas[anchor] = struct
        return struct


# Stack of enclosing-query schemas (NamedStruct) for correlated subqueries, so a
# field reference with an OuterReference.steps_out root resolves against the right
# level (offset-based, for tree-shaped plans). Pushed by the subquery builders
# while resolving their inner plan. Id-based (rel_reference) outer references
# resolve against ``anchor_scope`` instead.
outer_schemas: contextvars.ContextVar = contextvars.ContextVar(
    "outer_schemas", default=()
)

# The anchor scope (an ``_AnchorScope``) for the plan / correlated sub-tree
# currently being inferred, or None outside inference. Set for the duration of a
# whole-plan inference (``infer_plan_schema``) so a ``rel_reference`` anywhere in
# the tree resolves, and temporarily narrowed by ``_outer_anchor_binding`` while a
# lateral join's right input is inferred.
anchor_scope: contextvars.ContextVar = contextvars.ContextVar(
    "anchor_scope", default=None
)


@contextlib.contextmanager
def _outer_anchor_binding(anchor, struct):
    """Bind ``anchor`` -> ``struct`` for id-based outer references resolved within
    the block, chaining to any enclosing anchor scope.

    Used while a ``LateralJoinRel``'s right (dependent) input is built or inferred:
    references to the join's ``rel_anchor`` resolve to the current left row even
    though the join relation is not yet in an anchor index. Nested lateral joins
    compose via the parent chain.
    """
    scope = _AnchorScope({}, (), parent=anchor_scope.get())
    scope.register(anchor, struct)
    token = anchor_scope.set(scope)
    try:
        yield
    finally:
        anchor_scope.reset(token)


def _derive_extension_schema(detail, inputs, registry):
    """Derive a registered extension relation's output NamedStruct, or None.

    The detail class is looked up on ``registry`` (an ``ExtensionRegistry``, or
    ``None`` when inference wasn't given one), so derivation is scoped to that
    registry instance rather than shared process-wide. ``inputs`` is ``None``
    (leaf), a single ``Type.Struct`` (single), or a list of ``Type.Struct``
    (multi).
    """
    detail_cls = (
        registry.lookup_extension_relation(detail.type_url)
        if registry is not None
        else None
    )
    if detail_cls is None:
        return None
    reconstructed = detail_cls.from_any(detail)
    if inputs is None:
        return reconstructed.derive_schema()
    return reconstructed.derive_schema(inputs)


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
    elif literal_type == "date":
        return stt.Type(date=stt.Type.Date(nullability=nullability))
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
    elif literal_type == "precision_time":
        return stt.Type(
            precision_time=stt.Type.PrecisionTime(
                precision=literal.precision_time.precision, nullability=nullability
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


def infer_nested_type(
    nested: stalg.Expression.Nested, parent_schema, *, registry=None, subtrees=()
) -> stt.Type:
    nested_type = nested.WhichOneof("nested_type")

    nullability = (
        stt.Type.Nullability.NULLABILITY_NULLABLE
        if nested.nullable
        else stt.Type.Nullability.NULLABILITY_REQUIRED
    )

    if nested_type == "struct":
        return stt.Type(
            struct=stt.Type.Struct(
                types=[
                    infer_expression_type(
                        f, parent_schema, registry=registry, subtrees=subtrees
                    )
                    for f in nested.struct.fields
                ],
                nullability=nullability,
            )
        )
    elif nested_type == "list":
        return stt.Type(
            list=stt.Type.List(
                type=infer_expression_type(
                    nested.list.values[0],
                    parent_schema,
                    registry=registry,
                    subtrees=subtrees,
                ),
                nullability=nullability,
            )
        )
    elif nested_type == "map":
        return stt.Type(
            map=stt.Type.Map(
                key=infer_expression_type(
                    nested.map.key_values[0].key,
                    parent_schema,
                    registry=registry,
                    subtrees=subtrees,
                ),
                value=infer_expression_type(
                    nested.map.key_values[0].value,
                    parent_schema,
                    registry=registry,
                    subtrees=subtrees,
                ),
                nullability=nullability,
            )
        )
    else:
        raise Exception(f"Unknown nested_type {nested_type}")


def infer_expression_type(
    expression: stalg.Expression,
    parent_schema: stt.Type.Struct,
    *,
    registry=None,
    subtrees=(),
) -> stt.Type:
    rex_type = expression.WhichOneof("rex_type")
    if rex_type == "selection":
        root_type = expression.selection.WhichOneof("root_type")
        # An OuterReference resolves against an enclosing query's schema; a lambda
        # parameter reference against the lambda's parameter struct; otherwise
        # against the input row.
        if root_type == "outer_reference":
            outer_ref = expression.selection.outer_reference
            # An outer reference resolves either by id (rel_reference -> the schema
            # of the relation carrying that rel_anchor, via the anchor scope -- a
            # LateralJoinRel anchor gives the current left row) or by offset
            # (steps_out -> that many levels up the correlated-subquery stack).
            # These are a protobuf oneof.
            if outer_ref.WhichOneof("outer_reference_type") == "rel_reference":
                anchors = anchor_scope.get()
                if anchors is None:
                    raise Exception(
                        "rel_reference outer reference requires whole-plan context; "
                        "infer via infer_plan_schema"
                    )
                schema = anchors.schema_of(outer_ref.rel_reference, registry)
            else:
                stack = outer_schemas.get()
                # steps_out is 1-based per the Substrait spec (1 = the immediately
                # enclosing query), so it indexes back from the top of the stack.
                steps = outer_ref.steps_out
                if steps < 1:
                    raise Exception(
                        f"outer reference has steps_out={steps}; Substrait requires "
                        "steps_out >= 1 (1 = the immediately enclosing query)"
                    )
                if steps > len(stack):
                    raise Exception(
                        "outer reference outside an enclosing (correlated) query"
                    )
                schema = stack[len(stack) - steps].struct
        else:
            assert root_type in ("root_reference", "lambda_parameter_reference")
            schema = parent_schema

        reference_type = expression.selection.WhichOneof("reference_type")

        if reference_type == "direct_reference":
            segment = expression.selection.direct_reference

            segment_reference_type = segment.WhichOneof("reference_type")

            if segment_reference_type == "struct_field":
                return schema.types[segment.struct_field.field]
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
        return infer_expression_type(
            expression.if_then.ifs[0].then,
            parent_schema,
            registry=registry,
            subtrees=subtrees,
        )
    elif rex_type == "switch_expression":
        return infer_expression_type(
            expression.switch_expression.ifs[0].then,
            parent_schema,
            registry=registry,
            subtrees=subtrees,
        )
    elif rex_type == "cast":
        return expression.cast.type
    elif rex_type == "singular_or_list" or rex_type == "multi_or_list":
        return stt.Type(
            bool=stt.Type.Boolean(nullability=stt.Type.Nullability.NULLABILITY_NULLABLE)
        )
    elif rex_type == "nested":
        return infer_nested_type(
            expression.nested, parent_schema, registry=registry, subtrees=subtrees
        )
    elif rex_type == "lambda":
        # A lambda's type is func<param_types -> body_type>; the body's parameter
        # references resolve against the lambda's own parameter struct.
        lam = getattr(expression, "lambda")
        body_type = infer_expression_type(
            lam.body, lam.parameters, registry=registry, subtrees=subtrees
        )
        return stt.Type(
            func=stt.Type.Func(
                parameter_types=list(lam.parameters.types),
                return_type=body_type,
                nullability=stt.Type.NULLABILITY_REQUIRED,
            )
        )
    elif rex_type == "subquery":
        subquery_type = expression.subquery.WhichOneof("subquery_type")

        # The subquery's inner plan may contain OuterReferences (correlated
        # columns) that resolve against this enclosing query's schema. Push it so
        # inferring the inner rel resolves them -- this makes inference
        # self-contained rather than relying on the build-time push in
        # extended_expression._inner_rel (which is gone by the time a downstream
        # verb re-infers the enclosing plan's schema).
        stack = outer_schemas.get()
        token = outer_schemas.set((*stack, stt.NamedStruct(struct=parent_schema)))
        try:
            if subquery_type == "scalar":
                scalar_rel = infer_rel_schema(
                    expression.subquery.scalar.input,
                    registry=registry,
                    subtrees=subtrees,
                )
                return scalar_rel.types[0]
            elif (
                subquery_type == "in_predicate"
                or subquery_type == "set_comparison"
                or subquery_type == "set_predicate"
            ):
                return stt.Type(
                    bool=stt.Type.Boolean(
                        nullability=stt.Type.Nullability.NULLABILITY_NULLABLE
                    )
                )
            else:
                raise Exception(f"Unknown subquery_type {subquery_type}")
        finally:
            outer_schemas.reset(token)
    elif rex_type == "dynamic_parameter":
        return expression.dynamic_parameter.type
    elif rex_type == "execution_context_variable":
        ecv = expression.execution_context_variable
        variable = ecv.WhichOneof("execution_context_variable_type")
        # Each variant carries the variable's own type.
        if variable == "current_timestamp":
            return stt.Type(precision_timestamp_tz=ecv.current_timestamp)
        elif variable == "current_date":
            return stt.Type(date=ecv.current_date)
        elif variable == "current_timezone":
            return stt.Type(string=ecv.current_timezone)
        else:
            raise Exception(f"Unknown execution context variable {variable}")
    else:
        raise Exception(f"Unknown rex_type {rex_type}")


def infer_extended_expression_schema(
    ee: stee.ExtendedExpression, *, registry=None
) -> stt.Type.Struct:
    exprs = [e for e in ee.referred_expr]

    types = [
        infer_expression_type(e.expression, ee.base_schema.struct, registry=registry)
        for e in exprs
    ]

    return stt.Type.Struct(
        types=types,
        nullability=stt.Type.NULLABILITY_REQUIRED,
    )


# Name of the extra boolean column a mark join appends to its output.
JOIN_MARK_COLUMN_NAME = "mark"


def _join_column_shape(type_name: str) -> str:
    """Which columns a join emits, by join-type NAME (shared across all join
    relations, whose enum integer values differ): ``left`` / ``right`` only for
    semi/anti, ``both+mark`` for mark joins, ``both`` otherwise. Single source of
    truth for both the inferred type list and the RelRoot names."""
    if type_name in ("JOIN_TYPE_LEFT_SEMI", "JOIN_TYPE_LEFT_ANTI"):
        return "left"
    if type_name in ("JOIN_TYPE_RIGHT_SEMI", "JOIN_TYPE_RIGHT_ANTI"):
        return "right"
    if type_name in ("JOIN_TYPE_LEFT_MARK", "JOIN_TYPE_RIGHT_MARK"):
        return "both+mark"
    return "both"  # inner / outer / left / right / single


def join_output_names(type_name: str, left_names, right_names) -> list:
    """RelRoot output names for a join, matching the columns
    :func:`_join_output_struct` emits so names and inferred types never disagree
    in count."""
    shape = _join_column_shape(type_name)
    if shape == "left":
        return list(left_names)
    if shape == "right":
        return list(right_names)
    if shape == "both+mark":
        return list(left_names) + list(right_names) + [JOIN_MARK_COLUMN_NAME]
    return list(left_names) + list(right_names)


def _join_struct_from_schemas(
    type_name: str, left: stt.Type.Struct, right: stt.Type.Struct
) -> stt.Type.Struct:
    """Combine already-inferred left/right schemas into a join's output struct
    by join-type NAME (shared across all join relations, whose enum integer
    values differ)."""
    required = stt.Type.Nullability.NULLABILITY_REQUIRED
    shape = _join_column_shape(type_name)
    if shape == "left":
        types = list(left.types)
    elif shape == "right":
        types = list(right.types)
    elif shape == "both+mark":
        types = (
            list(left.types)
            + list(right.types)
            + [
                stt.Type(
                    bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)
                )
            ]
        )
    else:
        types = list(left.types) + list(right.types)
    return stt.Type.Struct(types=types, nullability=required)


def _join_output_struct(
    type_name: str, left_rel, right_rel, *, registry=None, subtrees=()
) -> stt.Type.Struct:
    """Join output column types by join-type NAME (shared across all join
    relations, whose enum integer values differ)."""
    left = infer_rel_schema(left_rel, registry=registry, subtrees=subtrees)
    right = infer_rel_schema(right_rel, registry=registry, subtrees=subtrees)
    return _join_struct_from_schemas(type_name, left, right)


def _lateral_join_output_struct(
    type_name: str, lateral_join: stalg.LateralJoinRel, *, registry=None, subtrees=()
) -> stt.Type.Struct:
    """Lateral-join output column types.

    A lateral join forms output like a regular join (same per-join-type column
    shapes), except its right (dependent) input is evaluated once per left row and
    may reference the current left row via ``OuterReference.rel_reference`` pointing
    to this relation's ``RelCommon.rel_anchor``. The left schema is bound to that
    anchor (via the anchor scope) while the right schema is inferred, so those
    id-based references resolve.
    """
    left = infer_rel_schema(lateral_join.left, registry=registry, subtrees=subtrees)
    common = lateral_join.common
    if common.HasField("rel_anchor"):
        with _outer_anchor_binding(common.rel_anchor, left):
            right = infer_rel_schema(
                lateral_join.right, registry=registry, subtrees=subtrees
            )
    else:
        right = infer_rel_schema(
            lateral_join.right, registry=registry, subtrees=subtrees
        )
    return _join_struct_from_schemas(type_name, left, right)


def _field_nullability(t: stt.Type):
    """The nullability of a (concrete) field type, or UNSPECIFIED if it has none."""
    kind = t.WhichOneof("kind")
    return getattr(t, kind).nullability if kind else stt.Type.NULLABILITY_UNSPECIFIED


def _with_field_nullability(t: stt.Type, nullability) -> stt.Type:
    """A copy of ``t`` with its nullability replaced (unchanged if it has no kind)."""
    out = stt.Type()
    out.CopyFrom(t)
    kind = out.WhichOneof("kind")
    if kind:
        getattr(out, kind).nullability = nullability
    return out


def _combine_set_nullability(op_name: str, nullabilities: list):
    """Combine one field's nullability across a set operation's inputs.

    Set inputs share field *types* but may differ in nullability; the output
    nullability is combined across all inputs per the operation (matching the
    Substrait spec's set-operation output-type derivation). ``nullabilities`` is
    the field's nullability in each input, primary first.
    """
    nullable = stt.Type.NULLABILITY_NULLABLE
    required = stt.Type.NULLABILITY_REQUIRED
    primary, secondaries = nullabilities[0], nullabilities[1:]
    if op_name in ("SET_OP_UNION_DISTINCT", "SET_OP_UNION_ALL"):
        # Nullable if nullable in any input.
        return nullable if nullable in nullabilities else required
    if op_name == "SET_OP_INTERSECTION_PRIMARY":
        # Nullable only if nullable in the primary and in some secondary input.
        return nullable if primary == nullable and nullable in secondaries else required
    if op_name in ("SET_OP_INTERSECTION_MULTISET", "SET_OP_INTERSECTION_MULTISET_ALL"):
        # Required if required in any input.
        return required if required in nullabilities else nullable
    # MINUS_* (and unspecified): the same as the primary input.
    return primary


def _set_output_struct(op_name: str, inputs: list) -> stt.Type.Struct:
    """The output struct of a set operation over already-inferred ``inputs``.

    Field types are taken from the primary input (the spec requires identical
    field types across inputs); each field's nullability is combined across all
    inputs according to ``op_name`` via :func:`_combine_set_nullability`.
    """
    primary = inputs[0]
    types = [
        _with_field_nullability(
            field,
            _combine_set_nullability(
                op_name,
                [_field_nullability(s.types[i]) for s in inputs if i < len(s.types)],
            ),
        )
        for i, field in enumerate(primary.types)
    ]
    return stt.Type.Struct(types=types, nullability=primary.nullability)


def infer_rel_schema(rel: stalg.Rel, *, registry=None, subtrees=()) -> stt.Type.Struct:
    """Infer a relation's output struct.

    ``subtrees`` is the plan's list of shared subtree ``Rel``s (the leading ``rel``
    entries of a ``Plan``, extracted by :func:`infer_plan_schema`); a
    ``ReferenceRel`` resolves its schema against ``subtrees[subtree_ordinal]``. It
    defaults to ``()`` so plans without shared subtrees behave exactly as before.
    """
    rel_type = rel.WhichOneof("rel_type")

    if rel_type == "read":
        (common, struct) = (rel.read.common, rel.read.base_schema.struct)
    elif rel_type == "filter":
        (common, struct) = (
            rel.filter.common,
            infer_rel_schema(rel.filter.input, registry=registry, subtrees=subtrees),
        )
    elif rel_type == "fetch":
        (common, struct) = (
            rel.fetch.common,
            infer_rel_schema(rel.fetch.input, registry=registry, subtrees=subtrees),
        )
    elif rel_type == "aggregate":
        parent_schema = infer_rel_schema(
            rel.aggregate.input, registry=registry, subtrees=subtrees
        )
        grouping_types = [
            infer_expression_type(
                g, parent_schema, registry=registry, subtrees=subtrees
            )
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
        (common, struct) = (
            rel.sort.common,
            infer_rel_schema(rel.sort.input, registry=registry, subtrees=subtrees),
        )
    elif rel_type == "project":
        parent_schema = infer_rel_schema(
            rel.project.input, registry=registry, subtrees=subtrees
        )
        expression_types = [
            infer_expression_type(
                e, parent_schema, registry=registry, subtrees=subtrees
            )
            for e in rel.project.expressions
        ]
        raw_schema = stt.Type.Struct(
            types=list(parent_schema.types) + expression_types,
            nullability=parent_schema.nullability,
        )

        (common, struct) = (rel.project.common, raw_schema)
    elif rel_type == "set":
        input_structs = [
            infer_rel_schema(i, registry=registry, subtrees=subtrees)
            for i in rel.set.inputs
        ]
        (common, struct) = (
            rel.set.common,
            _set_output_struct(stalg.SetRel.SetOp.Name(rel.set.op), input_structs),
        )
    elif rel_type == "cross":
        left_schema = infer_rel_schema(
            rel.cross.left, registry=registry, subtrees=subtrees
        )
        right_schema = infer_rel_schema(
            rel.cross.right, registry=registry, subtrees=subtrees
        )

        raw_schema = stt.Type.Struct(
            types=list(left_schema.types) + list(right_schema.types),
            nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
        )

        (common, struct) = (rel.cross.common, raw_schema)
    elif rel_type == "join":
        raw_schema = _join_output_struct(
            stalg.JoinRel.JoinType.Name(rel.join.type),
            rel.join.left,
            rel.join.right,
            registry=registry,
            subtrees=subtrees,
        )
        (common, struct) = (rel.join.common, raw_schema)
    elif rel_type == "lateral_join":
        raw_schema = _lateral_join_output_struct(
            stalg.JoinRel.JoinType.Name(rel.lateral_join.type),
            rel.lateral_join,
            registry=registry,
            subtrees=subtrees,
        )
        (common, struct) = (rel.lateral_join.common, raw_schema)
    elif rel_type == "window":
        parent_schema = infer_rel_schema(
            rel.window.input, registry=registry, subtrees=subtrees
        )
        window_output_types = [wf.output_type for wf in rel.window.window_functions]
        raw_schema = stt.Type.Struct(
            types=list(parent_schema.types) + window_output_types,
            nullability=parent_schema.nullability,
        )
        (common, struct) = (rel.window.common, raw_schema)
    elif rel_type == "expand":
        parent_schema = infer_rel_schema(
            rel.expand.input, registry=registry, subtrees=subtrees
        )
        field_types = []
        for field in rel.expand.fields:
            if field.HasField("consistent_field"):
                field_types.append(
                    infer_expression_type(
                        field.consistent_field,
                        parent_schema,
                        registry=registry,
                        subtrees=subtrees,
                    )
                )
            else:
                duplicates = field.switching_field.duplicates
                if not duplicates:
                    raise ValueError(
                        "expand switching field has no duplicate expressions; its "
                        "output type cannot be inferred"
                    )
                # All duplicates of a switching field share one type; the first
                # determines the output column type.
                field_types.append(
                    infer_expression_type(
                        duplicates[0],
                        parent_schema,
                        registry=registry,
                        subtrees=subtrees,
                    )
                )
        # Expand appends an i32 column with the index of the duplicate the row
        # is derived from.
        field_types.append(
            stt.Type(i32=stt.Type.I32(nullability=stt.Type.NULLABILITY_REQUIRED))
        )
        raw_schema = stt.Type.Struct(
            types=field_types, nullability=parent_schema.nullability
        )
        (common, struct) = (rel.expand.common, raw_schema)
    elif rel_type == "nested_loop_join":
        name = stalg.NestedLoopJoinRel.JoinType.Name(rel.nested_loop_join.type)
        raw_schema = _join_output_struct(
            name,
            rel.nested_loop_join.left,
            rel.nested_loop_join.right,
            registry=registry,
            subtrees=subtrees,
        )
        (common, struct) = (rel.nested_loop_join.common, raw_schema)
    elif rel_type == "hash_join":
        name = stalg.HashJoinRel.JoinType.Name(rel.hash_join.type)
        raw_schema = _join_output_struct(
            name,
            rel.hash_join.left,
            rel.hash_join.right,
            registry=registry,
            subtrees=subtrees,
        )
        (common, struct) = (rel.hash_join.common, raw_schema)
    elif rel_type == "merge_join":
        name = stalg.MergeJoinRel.JoinType.Name(rel.merge_join.type)
        raw_schema = _join_output_struct(
            name,
            rel.merge_join.left,
            rel.merge_join.right,
            registry=registry,
            subtrees=subtrees,
        )
        (common, struct) = (rel.merge_join.common, raw_schema)
    elif rel_type == "exchange":
        # Exchange redistributes rows without changing the schema.
        (common, struct) = (
            rel.exchange.common,
            infer_rel_schema(rel.exchange.input, registry=registry, subtrees=subtrees),
        )
    elif rel_type == "top_n":
        # TopN is a fused sort+fetch; the schema is unchanged from the input.
        (common, struct) = (
            rel.top_n.common,
            infer_rel_schema(rel.top_n.input, registry=registry, subtrees=subtrees),
        )
    elif rel_type == "reference":
        # A ReferenceRel has no RelCommon/emit; its schema is that of the shared
        # subtree its subtree_ordinal indexes into. A _SubtreeScope memoizes that
        # resolution and guards against reference cycles; a plain sequence (direct
        # callers/tests) is resolved inline against the full subtree list so a
        # subtree may itself reference an earlier one.
        ordinal = rel.reference.subtree_ordinal
        if not 0 <= ordinal < len(subtrees):
            raise Exception(
                f"ReferenceRel subtree_ordinal {ordinal} is out of range "
                f"({len(subtrees)} shared subtree(s) in scope)"
            )
        if isinstance(subtrees, _SubtreeScope):
            return subtrees.schema_of(ordinal, registry)
        return infer_rel_schema(subtrees[ordinal], registry=registry, subtrees=subtrees)
    elif rel_type == "extension_leaf":
        derived = _derive_extension_schema(rel.extension_leaf.detail, None, registry)
        if derived is None:
            raise Exception(
                "no schema deriver registered for extension leaf relation "
                f"{rel.extension_leaf.detail.type_url!r}"
            )
        (common, struct) = (rel.extension_leaf.common, derived.struct)
    elif rel_type == "extension_single":
        input_struct = infer_rel_schema(
            rel.extension_single.input, registry=registry, subtrees=subtrees
        )
        derived = _derive_extension_schema(
            rel.extension_single.detail, input_struct, registry
        )
        # Fall back to a pass-through schema when no deriver is registered.
        (common, struct) = (
            rel.extension_single.common,
            derived.struct if derived is not None else input_struct,
        )
    elif rel_type == "extension_multi":
        input_structs = [
            infer_rel_schema(i, registry=registry, subtrees=subtrees)
            for i in rel.extension_multi.inputs
        ]
        derived = _derive_extension_schema(
            rel.extension_multi.detail, input_structs, registry
        )
        if derived is None:
            raise Exception(
                "no schema deriver registered for extension multi relation "
                f"{rel.extension_multi.detail.type_url!r}"
            )
        (common, struct) = (rel.extension_multi.common, derived.struct)
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


def infer_plan_schema(plan: stp.Plan, *, registry=None) -> stt.NamedStruct:
    # A Plan carries its shared subtrees in-band as the leading ``rel`` entries of
    # ``relations`` (the query root is the trailing ``root`` entry), so a
    # ReferenceRel anywhere in the tree resolves against them by ordinal. Wrap them
    # in a _SubtreeScope so repeated references are memoized and cycles are caught.
    subtrees = _SubtreeScope(plan_subtrees(plan))
    # Index every RelCommon.rel_anchor in the plan (across subtrees, the root, and
    # subquery-embedded relations) so an id-based OuterReference (rel_reference)
    # anywhere resolves against the anchored relation's output schema.
    anchors = {
        a: rel for rel in iter_plan_rels(plan) if (a := rel_anchor_of(rel)) is not None
    }
    # Chain to any enclosing anchor scope (e.g. a lateral join binding its left
    # schema while its right input -- a separate plan being inferred here -- is
    # built) so references to an outer anchor still resolve.
    token = anchor_scope.set(_AnchorScope(anchors, subtrees, parent=anchor_scope.get()))
    try:
        root = plan.relations[-1].root
        schema = infer_rel_schema(root.input, registry=registry, subtrees=subtrees)
    finally:
        anchor_scope.reset(token)

    return stt.NamedStruct(names=root.names, struct=schema)
