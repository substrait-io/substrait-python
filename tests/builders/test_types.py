import substrait.gen.proto.type_pb2 as stt
from substrait.builders.type import boolean, i64
from substrait.builders.type import named_struct
import pytest


def test_named_struct_required():
    struct = stt.Type.Struct(
        types=[i64(nullable=False), boolean()],
        nullability=stt.Type.NULLABILITY_REQUIRED,
    )

    named = named_struct(names=["index", "valid"], struct=stt.Type(struct=struct))
    assert named
    assert named.struct.nullability == stt.Type.NULLABILITY_REQUIRED
    assert named.names == ["index", "valid"]


def test_named_struct_unspecified():
    struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

    named = named_struct(names=["index", "valid"], struct=stt.Type(struct=struct))
    assert named
    assert named.struct.nullability == stt.Type.NULLABILITY_REQUIRED
    assert named.names == ["index", "valid"]


def test_named_struct_nullable():
    struct = stt.Type.Struct(
        types=[i64(nullable=False), boolean()],
        nullability=stt.Type.NULLABILITY_NULLABLE,
    )

    with pytest.raises(
        Exception, match=r"NamedStruct must not contain a nullable struct"
    ):
        named_struct(names=["index", "valid"], struct=stt.Type(struct=struct))
