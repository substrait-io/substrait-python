import substrait.gen.proto.type_pb2 as stt
from substrait.utils import type_num_names


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
