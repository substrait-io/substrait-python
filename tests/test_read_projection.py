import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.type import boolean, i32, i64, string
from substrait.type_inference import infer_plan_schema, infer_rel_schema

MASK = stalg.Expression.MaskExpression
REQ = stt.Type.NULLABILITY_REQUIRED
NULL = stt.Type.NULLABILITY_NULLABLE


def _struct(*fields, nullable=REQ, variation=0):
    return stt.Type.Struct(
        types=fields, nullability=nullable, type_variation_reference=variation
    )


def _select(*fields):
    return MASK.StructSelect(
        struct_items=[
            field
            if isinstance(field, MASK.StructItem)
            else MASK.StructItem(field=field)
            for field in fields
        ]
    )


def _read(schema, select=None, *, names=(), emit=None):
    read = stalg.ReadRel(
        base_schema=stt.NamedStruct(names=names, struct=schema),
        named_table=stalg.ReadRel.NamedTable(names=["t"]),
    )
    if select is not None:
        read.projection.CopyFrom(MASK(select=select, maintain_singular_struct=True))
    if emit is not None:
        read.common.emit.output_mapping.extend(emit)
        read.common.emit.SetInParent()
    return stalg.Rel(read=read)


@pytest.mark.parametrize("fields", [[], [2], [2, 0], [2, 0, 2]])
def test_read_projection_selects_fields_in_mask_order(fields):
    schema = _struct(
        i64(nullable=False), string(), boolean(nullable=False), variation=7
    )
    rel = _read(schema, _select(*fields), names=["id", "text", "flag"])
    before = rel.SerializeToString()

    assert infer_rel_schema(rel) == _struct(
        *(schema.types[i] for i in fields), variation=7
    )
    assert rel.SerializeToString() == before


def test_read_without_projection_keeps_the_schema():
    schema = _struct(i64(nullable=False), string(), variation=7)
    assert infer_rel_schema(_read(schema)) == schema


def test_read_projection_without_select_keeps_the_schema():
    schema = _struct(i64(nullable=False), string(), variation=7)
    rel = _read(schema)
    rel.read.projection.maintain_singular_struct = True
    assert infer_rel_schema(rel) == schema


@pytest.mark.parametrize("maintain", [False, True])
def test_single_field_read_projection_preserves_the_row_struct(maintain):
    rel = _read(_struct(i64(), string(), boolean(nullable=False)), _select(2))
    rel.read.projection.maintain_singular_struct = maintain
    assert infer_rel_schema(rel) == _struct(boolean(nullable=False))


@pytest.mark.parametrize("maintain", [False, True])
def test_single_field_read_projection_preserves_nested_structs(maintain):
    rel = _read(
        _struct(i64(), stt.Type(struct=_struct(i64(), string(), nullable=NULL))),
        _select(MASK.StructItem(field=1, child=MASK.Select(struct=_select(1)))),
    )
    rel.read.projection.maintain_singular_struct = maintain

    assert infer_rel_schema(rel) == _struct(
        stt.Type(struct=_struct(string(), nullable=NULL))
    )


def test_read_projection_precedes_emit():
    schema = _struct(i64(nullable=False), string(), boolean(nullable=False))
    rel = _read(schema, _select(2, 0), emit=[1, 0, 1])
    assert infer_rel_schema(rel) == _struct(
        i64(nullable=False), boolean(nullable=False), i64(nullable=False)
    )


def test_read_emit_cannot_index_a_field_removed_by_projection():
    rel = _read(_struct(i64(), string(), boolean()), _select(2), emit=[1])
    with pytest.raises(IndexError):
        infer_rel_schema(rel)


def test_read_projection_keeps_nested_structure_and_root_names():
    inner = _struct(
        i64(nullable=False),
        string(),
        boolean(nullable=False),
        nullable=NULL,
        variation=8,
    )
    rel = _read(
        _struct(i32(), stt.Type(struct=inner), string()),
        _select(MASK.StructItem(field=1, child=MASK.Select(struct=_select(2, 0))), 0),
        names=["unused", "original_struct", "id", "text", "flag", "other"],
    )
    root_names = ["renamed_struct", "renamed_flag", "renamed_id", "renamed_scalar"]
    plan = stp.Plan(
        relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=root_names))]
    )
    before = plan.SerializeToString()

    assert infer_plan_schema(plan) == stt.NamedStruct(
        names=root_names,
        struct=_struct(
            stt.Type(
                struct=_struct(
                    boolean(nullable=False),
                    i64(nullable=False),
                    nullable=NULL,
                    variation=8,
                )
            ),
            i32(),
        ),
    )
    assert plan.SerializeToString() == before


@pytest.mark.parametrize("kind", ["list", "map"])
def test_read_projection_prunes_collection_children(kind):
    element = stt.Type(
        struct=_struct(i64(nullable=False), string(), nullable=NULL, variation=9)
    )
    child = MASK.Select(struct=_select(1))
    if kind == "list":
        field = stt.Type(
            list=stt.Type.List(
                type=element, nullability=NULL, type_variation_reference=10
            )
        )
        selection = MASK.Select(
            list=MASK.ListSelect(
                selection=[
                    MASK.ListSelect.ListSelectItem(
                        item=MASK.ListSelect.ListSelectItem.ListElement(field=0)
                    )
                ],
                child=child,
            )
        )
        expected = stt.Type(
            list=stt.Type.List(
                type=stt.Type(struct=_struct(string(), nullable=NULL, variation=9)),
                nullability=NULL,
                type_variation_reference=10,
            )
        )
    else:
        field = stt.Type(
            map=stt.Type.Map(
                key=string(nullable=False),
                value=element,
                nullability=NULL,
                type_variation_reference=10,
            )
        )
        selection = MASK.Select(
            map=MASK.MapSelect(key=MASK.MapSelect.MapKey(map_key="k"), child=child)
        )
        expected = stt.Type(
            map=stt.Type.Map(
                key=string(nullable=False),
                value=stt.Type(struct=_struct(string(), nullable=NULL, variation=9)),
                nullability=NULL,
                type_variation_reference=10,
            )
        )
    rel = _read(_struct(field), _select(MASK.StructItem(field=0, child=selection)))
    before = rel.SerializeToString()
    assert infer_rel_schema(rel) == _struct(expected)
    assert rel.SerializeToString() == before


def test_read_projection_recurses_through_nested_collections():
    # list<map<string, list<struct<i64, string>>>> -> the same wrappers, struct<string>.
    def wrapped(inner):
        return stt.Type(
            list=stt.Type.List(
                type=stt.Type(
                    map=stt.Type.Map(
                        key=string(nullable=False),
                        value=stt.Type(list=stt.Type.List(type=inner, nullability=REQ)),
                        nullability=NULL,
                    )
                ),
                nullability=NULL,
            )
        )

    selection = MASK.Select(
        list=MASK.ListSelect(
            child=MASK.Select(
                map=MASK.MapSelect(
                    child=MASK.Select(
                        list=MASK.ListSelect(
                            child=MASK.Select(struct=_select(1)),
                        )
                    )
                ),
            )
        )
    )
    rel = _read(
        _struct(wrapped(stt.Type(struct=_struct(i64(), string())))),
        _select(MASK.StructItem(field=0, child=selection)),
    )
    assert infer_rel_schema(rel) == _struct(wrapped(stt.Type(struct=_struct(string()))))


@pytest.mark.parametrize("kind", ["list", "map"])
def test_read_collection_selection_without_child_keeps_its_type(kind):
    if kind == "list":
        field = stt.Type(list=stt.Type.List(type=i64(), nullability=NULL))
        child = MASK.Select(
            list=MASK.ListSelect(
                selection=[
                    MASK.ListSelect.ListSelectItem(
                        slice=MASK.ListSelect.ListSelectItem.ListSlice(start=1, end=3)
                    )
                ]
            )
        )
    else:
        field = stt.Type(
            map=stt.Type.Map(key=string(nullable=False), value=i64(), nullability=REQ)
        )
        child = MASK.Select(
            map=MASK.MapSelect(
                expression=MASK.MapSelect.MapKeyExpression(map_key_expression="k*")
            )
        )
    rel = _read(
        _struct(string(), field), _select(MASK.StructItem(field=1, child=child))
    )
    assert infer_rel_schema(rel) == _struct(field)


@pytest.mark.parametrize("index", [-1, 2])
@pytest.mark.parametrize("nested", [False, True])
def test_read_projection_rejects_invalid_struct_indices(index, nested):
    schema = _struct(i64(), string())
    select = _select(index)
    if nested:
        schema = _struct(stt.Type(struct=schema))
        select = _select(MASK.StructItem(field=0, child=MASK.Select(struct=select)))
    with pytest.raises(ValueError, match=f"field index {index}"):
        infer_rel_schema(_read(schema, select))


@pytest.mark.parametrize(
    "child",
    [
        MASK.Select(struct=_select(0)),
        MASK.Select(list=MASK.ListSelect()),
        MASK.Select(map=MASK.MapSelect()),
        MASK.Select(),
    ],
)
def test_read_projection_rejects_inapplicable_child_selection(child):
    rel = _read(_struct(i64()), _select(MASK.StructItem(field=0, child=child)))
    with pytest.raises(ValueError, match="Read projection"):
        infer_rel_schema(rel)


def test_project_above_masked_read_uses_projected_indices():
    rel = _read(_struct(i64(nullable=False), string(), boolean()), _select(1, 0))
    project = stalg.Rel(
        project=stalg.ProjectRel(
            input=rel,
            expressions=[
                stalg.Expression(
                    selection=stalg.Expression.FieldReference(
                        direct_reference=stalg.Expression.ReferenceSegment(
                            struct_field=stalg.Expression.ReferenceSegment.StructField(
                                field=0
                            )
                        ),
                        root_reference=stalg.Expression.FieldReference.RootReference(),
                    )
                )
            ],
            common=stalg.RelCommon(emit=stalg.RelCommon.Emit(output_mapping=[2])),
        )
    )
    assert infer_rel_schema(project) == _struct(string())
