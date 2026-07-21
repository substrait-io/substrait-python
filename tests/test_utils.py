import pytest
import substrait.extended_expression_pb2 as stee
import substrait.extensions.extensions_pb2 as ste
import substrait.type_pb2 as stt

from substrait.utils import (
    merge_extension_declarations,
    merge_extension_urns,
    merge_extensions_into,
    type_num_names,
)


def test_type_num_names_flat_struct():
    assert (
        type_num_names(
            stt.Type(
                struct=stt.Type.Struct(
                    types=[
                        stt.Type(i64=stt.Type.I64()),
                        stt.Type(string=stt.Type.String()),
                        stt.Type(fp32=stt.Type.FP32()),
                    ]
                )
            )
        )
        == 4
    )


def test_type_num_names_nested_struct():
    assert (
        type_num_names(
            stt.Type(
                struct=stt.Type.Struct(
                    types=[
                        stt.Type(i64=stt.Type.I64()),
                        stt.Type(
                            struct=stt.Type.Struct(
                                types=[
                                    stt.Type(i64=stt.Type.I64()),
                                    stt.Type(fp32=stt.Type.FP32()),
                                ]
                            )
                        ),
                        stt.Type(fp32=stt.Type.FP32()),
                    ]
                )
            )
        )
        == 6
    )


def test_type_num_names_flat_list():
    assert (
        type_num_names(
            stt.Type(
                struct=stt.Type.Struct(
                    types=[
                        stt.Type(i64=stt.Type.I64()),
                        stt.Type(list=stt.Type.List(type=stt.Type(i64=stt.Type.I64()))),
                        stt.Type(fp32=stt.Type.FP32()),
                    ]
                )
            )
        )
        == 4
    )


def test_type_num_names_nested_list():
    assert (
        type_num_names(
            stt.Type(
                struct=stt.Type.Struct(
                    types=[
                        stt.Type(i64=stt.Type.I64()),
                        stt.Type(
                            list=stt.Type.List(
                                type=stt.Type(
                                    struct=stt.Type.Struct(
                                        types=[
                                            stt.Type(i64=stt.Type.I64()),
                                            stt.Type(fp32=stt.Type.FP32()),
                                        ]
                                    )
                                )
                            )
                        ),
                        stt.Type(fp32=stt.Type.FP32()),
                    ]
                )
            )
        )
        == 6
    )


def test_merge_extension_urns_deduplicates():
    """Test that merging extension URNs deduplicates correctly."""
    # Create duplicate URN extensions
    urn1 = ste.SimpleExtensionURN(extension_urn_anchor=1, urn="extension:example:test")
    urn2 = ste.SimpleExtensionURN(extension_urn_anchor=1, urn="extension:example:test")
    urn3 = ste.SimpleExtensionURN(extension_urn_anchor=2, urn="extension:example:other")

    merged_urns = merge_extension_urns([urn1], [urn2, urn3])

    assert len(merged_urns) == 2
    assert merged_urns[0].urn == "extension:example:test"
    assert merged_urns[1].urn == "extension:example:other"


def _extension_function(urn_reference, function_anchor, name):
    return ste.SimpleExtensionDeclaration(
        extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
            extension_urn_reference=urn_reference,
            function_anchor=function_anchor,
            name=name,
        )
    )


def test_merge_extensions_into_appends_new_and_dedupes_on_identity():
    """merge_extensions_into keeps target's entries and appends only novel ones,
    keying on the same anchor/name identity as the merge_* helpers."""
    target = stee.ExtendedExpression(
        extension_urns=[ste.SimpleExtensionURN(extension_urn_anchor=1, urn="A")],
        extensions=[_extension_function(1, 10, "f:i8")],
    )
    source = stee.ExtendedExpression(
        extension_urns=[
            ste.SimpleExtensionURN(extension_urn_anchor=1, urn="A"),  # dup URN string
            ste.SimpleExtensionURN(extension_urn_anchor=2, urn="B"),
        ],
        extensions=[
            # Same (urn reference, name) as target's -- a duplicate by identity even
            # though the function anchor differs, so it must not be appended (this is
            # what distinguishes identity dedup from strict proto equality).
            _extension_function(1, 99, "f:i8"),
            _extension_function(2, 11, "g:i8"),
        ],
    )

    merge_extensions_into(target, source)

    assert [u.urn for u in target.extension_urns] == ["A", "B"]
    assert [d.extension_function.name for d in target.extensions] == ["f:i8", "g:i8"]
    # target's original declaration is kept; source's identity-duplicate is dropped.
    assert target.extensions[0].extension_function.function_anchor == 10


def test_merge_extensions_into_merges_multiple_sources():
    target = stee.ExtendedExpression()
    source1 = stee.ExtendedExpression(
        extension_urns=[ste.SimpleExtensionURN(extension_urn_anchor=1, urn="A")],
        extensions=[_extension_function(1, 10, "f:i8")],
    )
    source2 = stee.ExtendedExpression(
        extension_urns=[ste.SimpleExtensionURN(extension_urn_anchor=2, urn="B")],
        extensions=[_extension_function(2, 11, "g:i8")],
    )

    merge_extensions_into(target, source1, source2)

    assert [u.urn for u in target.extension_urns] == ["A", "B"]
    assert [d.extension_function.name for d in target.extensions] == ["f:i8", "g:i8"]


def test_merge_extension_declarations_rejects_non_function_mapping():
    """Only ``extension_function`` declarations are supported so far; a type /
    type-variation declaration raises an informative NotImplementedError naming
    the unsupported mapping type."""
    declaration = ste.SimpleExtensionDeclaration(
        extension_type=ste.SimpleExtensionDeclaration.ExtensionType()
    )

    with pytest.raises(NotImplementedError, match="extension_type"):
        merge_extension_declarations([declaration])
