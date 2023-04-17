"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
_sym_db = _symbol_database.Default()
from ..pysubstrait import algebra_pb2 as pysubstrait_dot_algebra__pb2
from ..pysubstrait.extensions import extensions_pb2 as pysubstrait_dot_extensions_dot_extensions__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x16pysubstrait/plan.proto\x12\x0bpysubstrait\x1a\x19pysubstrait/algebra.proto\x1a\'pysubstrait/extensions/extensions.proto"g\n\x07PlanRel\x12$\n\x03rel\x18\x01 \x01(\x0b2\x10.pysubstrait.RelH\x00R\x03rel\x12*\n\x04root\x18\x02 \x01(\x0b2\x14.pysubstrait.RelRootH\x00R\x04rootB\n\n\x08rel_type"\x9b\x03\n\x04Plan\x12.\n\x07version\x18\x06 \x01(\x0b2\x14.pysubstrait.VersionR\x07version\x12Q\n\x0eextension_uris\x18\x01 \x03(\x0b2*.pysubstrait.extensions.SimpleExtensionURIR\rextensionUris\x12R\n\nextensions\x18\x02 \x03(\x0b22.pysubstrait.extensions.SimpleExtensionDeclarationR\nextensions\x122\n\trelations\x18\x03 \x03(\x0b2\x14.pysubstrait.PlanRelR\trelations\x12Z\n\x13advanced_extensions\x18\x04 \x01(\x0b2).pysubstrait.extensions.AdvancedExtensionR\x12advancedExtensions\x12,\n\x12expected_type_urls\x18\x05 \x03(\tR\x10expectedTypeUrls"=\n\x0bPlanVersion\x12.\n\x07version\x18\x06 \x01(\x0b2\x14.pysubstrait.VersionR\x07version"\xa9\x01\n\x07Version\x12!\n\x0cmajor_number\x18\x01 \x01(\rR\x0bmajorNumber\x12!\n\x0cminor_number\x18\x02 \x01(\rR\x0bminorNumber\x12!\n\x0cpatch_number\x18\x03 \x01(\rR\x0bpatchNumber\x12\x19\n\x08git_hash\x18\x04 \x01(\tR\x07gitHash\x12\x1a\n\x08producer\x18\x05 \x01(\tR\x08producerB/\n\x14io.pysubstrait.protoP\x01\xaa\x02\x14Pysubstrait.Protobufb\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'pysubstrait.plan_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b'\n\x14io.pysubstrait.protoP\x01\xaa\x02\x14Pysubstrait.Protobuf'
    _PLANREL._serialized_start = 107
    _PLANREL._serialized_end = 210
    _PLAN._serialized_start = 213
    _PLAN._serialized_end = 624
    _PLANVERSION._serialized_start = 626
    _PLANVERSION._serialized_end = 687
    _VERSION._serialized_start = 690
    _VERSION._serialized_end = 859