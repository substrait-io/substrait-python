"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
_sym_db = _symbol_database.Default()
from ..proto import algebra_pb2 as proto_dot_algebra__pb2
from ..proto.extensions import extensions_pb2 as proto_dot_extensions_dot_extensions__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x10proto/plan.proto\x12\x05proto\x1a\x13proto/algebra.proto\x1a!proto/extensions/extensions.proto"[\n\x07PlanRel\x12\x1e\n\x03rel\x18\x01 \x01(\x0b2\n.proto.RelH\x00R\x03rel\x12$\n\x04root\x18\x02 \x01(\x0b2\x0e.proto.RelRootH\x00R\x04rootB\n\n\x08rel_type"\xfd\x02\n\x04Plan\x12(\n\x07version\x18\x06 \x01(\x0b2\x0e.proto.VersionR\x07version\x12K\n\x0eextension_uris\x18\x01 \x03(\x0b2$.proto.extensions.SimpleExtensionURIR\rextensionUris\x12L\n\nextensions\x18\x02 \x03(\x0b2,.proto.extensions.SimpleExtensionDeclarationR\nextensions\x12,\n\trelations\x18\x03 \x03(\x0b2\x0e.proto.PlanRelR\trelations\x12T\n\x13advanced_extensions\x18\x04 \x01(\x0b2#.proto.extensions.AdvancedExtensionR\x12advancedExtensions\x12,\n\x12expected_type_urls\x18\x05 \x03(\tR\x10expectedTypeUrls"7\n\x0bPlanVersion\x12(\n\x07version\x18\x06 \x01(\x0b2\x0e.proto.VersionR\x07version"\xa9\x01\n\x07Version\x12!\n\x0cmajor_number\x18\x01 \x01(\rR\x0bmajorNumber\x12!\n\x0cminor_number\x18\x02 \x01(\rR\x0bminorNumber\x12!\n\x0cpatch_number\x18\x03 \x01(\rR\x0bpatchNumber\x12\x19\n\x08git_hash\x18\x04 \x01(\tR\x07gitHash\x12\x1a\n\x08producer\x18\x05 \x01(\tR\x08producerB#\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobufb\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'proto.plan_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b'\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobuf'
    _PLANREL._serialized_start = 83
    _PLANREL._serialized_end = 174
    _PLAN._serialized_start = 177
    _PLAN._serialized_end = 558
    _PLANVERSION._serialized_start = 560
    _PLANVERSION._serialized_end = 615
    _VERSION._serialized_start = 618
    _VERSION._serialized_end = 787