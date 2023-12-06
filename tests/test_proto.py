# ruff: noqa: F401


def test_imports():
    """Temporary sanity test"""
    from substrait.gen.proto.algebra_pb2 import Expression
    from substrait.gen.proto.capabilities_pb2 import Capabilities
    from substrait.gen.proto.extended_expression_pb2 import ExtendedExpression
    from substrait.gen.proto.function_pb2 import FunctionSignature
    from substrait.gen.proto.parameterized_types_pb2 import ParameterizedType
    from substrait.gen.proto.plan_pb2 import Plan
    from substrait.gen.proto.type_expressions_pb2 import DerivationExpression
    from substrait.gen.proto.type_pb2 import Type
    from substrait.gen.proto.extensions.extensions_pb2 import SimpleExtensionURI
