def test_imports():
    """Temporary sanity test"""
    from substrait.proto.algebra_pb2 import Expression
    from substrait.proto.capabilities_pb2 import Capabilities
    from substrait.proto.extended_expression_pb2 import ExtendedExpression
    from substrait.proto.function_pb2 import FunctionSignature
    from substrait.proto.parameterized_types_pb2 import ParameterizedType
    from substrait.proto.plan_pb2 import Plan
    from substrait.proto.type_expressions_pb2 import DerivationExpression
    from substrait.proto.type_pb2 import Type
    from substrait.proto.extensions.extensions_pb2 import SimpleExtensionURI
