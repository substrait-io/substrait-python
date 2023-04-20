def test_imports():
    from substrait.proto.pysubstrait.algebra_pb2 import Expression
    from substrait.proto.pysubstrait.capabilities_pb2 import Capabilities
    from substrait.proto.pysubstrait.extended_expression_pb2 import ExtendedExpression
    from substrait.proto.pysubstrait.function_pb2 import FunctionSignature
    from substrait.proto.pysubstrait.parameterized_types_pb2 import ParameterizedType
    from substrait.proto.pysubstrait.plan_pb2 import Plan
    from substrait.proto.pysubstrait.type_expressions_pb2 import DerivationExpression
    from substrait.proto.pysubstrait.type_pb2 import Type
    from substrait.proto.pysubstrait.extensions.extensions_pb2 import SimpleExtensionURI
