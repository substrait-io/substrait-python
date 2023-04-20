"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
_sym_db = _symbol_database.Default()
from ..pysubstrait import algebra_pb2 as pysubstrait_dot_algebra__pb2
from ..pysubstrait.extensions import extensions_pb2 as pysubstrait_dot_extensions_dot_extensions__pb2
from ..pysubstrait import plan_pb2 as pysubstrait_dot_plan__pb2
from ..pysubstrait import type_pb2 as pysubstrait_dot_type__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n%pysubstrait/extended_expression.proto\x12\x0bpysubstrait\x1a\x19pysubstrait/algebra.proto\x1a\'pysubstrait/extensions/extensions.proto\x1a\x16pysubstrait/plan.proto\x1a\x16pysubstrait/type.proto"\xbc\x01\n\x13ExpressionReference\x129\n\nexpression\x18\x01 \x01(\x0b2\x17.pysubstrait.ExpressionH\x00R\nexpression\x12:\n\x07measure\x18\x02 \x01(\x0b2\x1e.pysubstrait.AggregateFunctionH\x00R\x07measure\x12!\n\x0coutput_names\x18\x03 \x03(\tR\x0boutputNamesB\x0b\n\texpr_type"\xf7\x03\n\x12ExtendedExpression\x12.\n\x07version\x18\x07 \x01(\x0b2\x14.pysubstrait.VersionR\x07version\x12Q\n\x0eextension_uris\x18\x01 \x03(\x0b2*.pysubstrait.extensions.SimpleExtensionURIR\rextensionUris\x12R\n\nextensions\x18\x02 \x03(\x0b22.pysubstrait.extensions.SimpleExtensionDeclarationR\nextensions\x12E\n\rreferred_expr\x18\x03 \x03(\x0b2 .pysubstrait.ExpressionReferenceR\x0creferredExpr\x129\n\x0bbase_schema\x18\x04 \x01(\x0b2\x18.pysubstrait.NamedStructR\nbaseSchema\x12Z\n\x13advanced_extensions\x18\x05 \x01(\x0b2).pysubstrait.extensions.AdvancedExtensionR\x12advancedExtensions\x12,\n\x12expected_type_urls\x18\x06 \x03(\tR\x10expectedTypeUrlsB/\n\x14io.pysubstrait.protoP\x01\xaa\x02\x14Pysubstrait.Protobufb\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'pysubstrait.extended_expression_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b'\n\x14io.pysubstrait.protoP\x01\xaa\x02\x14Pysubstrait.Protobuf'
    _EXPRESSIONREFERENCE._serialized_start = 171
    _EXPRESSIONREFERENCE._serialized_end = 359
    _EXTENDEDEXPRESSION._serialized_start = 362
    _EXTENDEDEXPRESSION._serialized_end = 865