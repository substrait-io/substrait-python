# ruff: noqa: F401


def test_imports():
    """Temporary sanity test"""
    from substrait.algebra_pb2 import Expression
    from substrait.extended_expression_pb2 import ExtendedExpression
    from substrait.extensions.extensions_pb2 import SimpleExtensionURN
    from substrait.plan_pb2 import Plan
    from substrait.type_pb2 import Type


def test_proto_proxy_module():
    """Test that protocol classes are made available in substrait.proto"""
    import substrait.proto

    assert {"Plan", "Type", "NamedStruct", "RelRoot"} <= set(dir(substrait.proto))
    assert {
        "algebra",
        "extensions",
        "extended_expression",
        "plan",
        "type",
    } <= set(dir(substrait.proto))
