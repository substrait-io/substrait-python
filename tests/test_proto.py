# ruff: noqa: F401


def test_imports():
    """Temporary sanity test"""
    from substrait.algebra_pb2 import Expression
    from substrait.capabilities_pb2 import Capabilities
    from substrait.extended_expression_pb2 import ExtendedExpression
    from substrait.extensions.extensions_pb2 import SimpleExtensionURN
    from substrait.function_pb2 import FunctionSignature
    from substrait.parameterized_types_pb2 import ParameterizedType
    from substrait.plan_pb2 import Plan
    from substrait.type_expressions_pb2 import DerivationExpression
    from substrait.type_pb2 import Type


def test_proto_proxy_module():
    """Test that protocol classes are made available in substrait.proto"""
    import substrait.proto

    assert {"Plan", "Type", "NamedStruct", "RelRoot"} <= set(dir(substrait.proto))
    assert {
        "algebra",
        "capabilities",
        "extensions",
        "extended_expression",
        "function",
        "parameterized_types",
        "plan",
        "type_expressions",
        "type",
    } <= set(dir(substrait.proto))
