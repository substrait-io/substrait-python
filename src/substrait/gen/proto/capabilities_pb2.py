"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x18proto/capabilities.proto\x12\x05proto"\xe8\x02\n\x0cCapabilities\x12-\n\x12substrait_versions\x18\x01 \x03(\tR\x11substraitVersions\x12?\n\x1cadvanced_extension_type_urls\x18\x02 \x03(\tR\x19advancedExtensionTypeUrls\x12P\n\x11simple_extensions\x18\x03 \x03(\x0b2#.proto.Capabilities.SimpleExtensionR\x10simpleExtensions\x1a\x95\x01\n\x0fSimpleExtension\x12\x10\n\x03uri\x18\x01 \x01(\tR\x03uri\x12#\n\rfunction_keys\x18\x02 \x03(\tR\x0cfunctionKeys\x12\x1b\n\ttype_keys\x18\x03 \x03(\tR\x08typeKeys\x12.\n\x13type_variation_keys\x18\x04 \x03(\tR\x11typeVariationKeysB#\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobufb\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'proto.capabilities_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b'\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobuf'
    _CAPABILITIES._serialized_start = 36
    _CAPABILITIES._serialized_end = 396
    _CAPABILITIES_SIMPLEEXTENSION._serialized_start = 247
    _CAPABILITIES_SIMPLEEXTENSION._serialized_end = 396