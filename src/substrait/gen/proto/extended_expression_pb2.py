"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
_sym_db = _symbol_database.Default()
from ..proto import algebra_pb2 as proto_dot_algebra__pb2
from ..proto.extensions import extensions_pb2 as proto_dot_extensions_dot_extensions__pb2
from ..proto import plan_pb2 as proto_dot_plan__pb2
from ..proto import type_pb2 as proto_dot_type__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1fproto/extended_expression.proto\x12\x05proto\x1a\x13proto/algebra.proto\x1a!proto/extensions/extensions.proto\x1a\x10proto/plan.proto\x1a\x10proto/type.proto"\xb0\x01\n\x13ExpressionReference\x123\n\nexpression\x18\x01 \x01(\x0b2\x11.proto.ExpressionH\x00R\nexpression\x124\n\x07measure\x18\x02 \x01(\x0b2\x18.proto.AggregateFunctionH\x00R\x07measure\x12!\n\x0coutput_names\x18\x03 \x03(\tR\x0boutputNamesB\x0b\n\texpr_type"\xd3\x03\n\x12ExtendedExpression\x12(\n\x07version\x18\x07 \x01(\x0b2\x0e.proto.VersionR\x07version\x12K\n\x0eextension_uris\x18\x01 \x03(\x0b2$.proto.extensions.SimpleExtensionURIR\rextensionUris\x12L\n\nextensions\x18\x02 \x03(\x0b2,.proto.extensions.SimpleExtensionDeclarationR\nextensions\x12?\n\rreferred_expr\x18\x03 \x03(\x0b2\x1a.proto.ExpressionReferenceR\x0creferredExpr\x123\n\x0bbase_schema\x18\x04 \x01(\x0b2\x12.proto.NamedStructR\nbaseSchema\x12T\n\x13advanced_extensions\x18\x05 \x01(\x0b2#.proto.extensions.AdvancedExtensionR\x12advancedExtensions\x12,\n\x12expected_type_urls\x18\x06 \x03(\tR\x10expectedTypeUrlsB#\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobufb\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'proto.extended_expression_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b'\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobuf'
    _EXPRESSIONREFERENCE._serialized_start = 135
    _EXPRESSIONREFERENCE._serialized_end = 311
    _EXTENDEDEXPRESSION._serialized_start = 314
    _EXTENDEDEXPRESSION._serialized_end = 781