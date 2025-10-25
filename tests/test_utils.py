import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.utils import type_num_names, merge_extension_uris, merge_extension_urns


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


def test_merge_extension_uris_deduplicates():
    """Test that merging extension URIs deduplicates correctly."""
    # Create duplicate URI extensions
    uri1 = ste.SimpleExtensionURI(
        extension_uri_anchor=1, uri="https://example.com/test.yaml"
    )
    uri2 = ste.SimpleExtensionURI(
        extension_uri_anchor=1, uri="https://example.com/test.yaml"
    )
    uri3 = ste.SimpleExtensionURI(
        extension_uri_anchor=2, uri="https://example.com/other.yaml"
    )

    merged_uris = merge_extension_uris([uri1], [uri2, uri3])

    assert len(merged_uris) == 2
    assert merged_uris[0].uri == "https://example.com/test.yaml"
    assert merged_uris[1].uri == "https://example.com/other.yaml"


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
