"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
_sym_db = _symbol_database.Default()
from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x10proto/type.proto\x12\x05proto\x1a\x1bgoogle/protobuf/empty.proto"\xd9&\n\x04Type\x12)\n\x04bool\x18\x01 \x01(\x0b2\x13.proto.Type.BooleanH\x00R\x04bool\x12 \n\x02i8\x18\x02 \x01(\x0b2\x0e.proto.Type.I8H\x00R\x02i8\x12#\n\x03i16\x18\x03 \x01(\x0b2\x0f.proto.Type.I16H\x00R\x03i16\x12#\n\x03i32\x18\x05 \x01(\x0b2\x0f.proto.Type.I32H\x00R\x03i32\x12#\n\x03i64\x18\x07 \x01(\x0b2\x0f.proto.Type.I64H\x00R\x03i64\x12&\n\x04fp32\x18\n \x01(\x0b2\x10.proto.Type.FP32H\x00R\x04fp32\x12&\n\x04fp64\x18\x0b \x01(\x0b2\x10.proto.Type.FP64H\x00R\x04fp64\x12,\n\x06string\x18\x0c \x01(\x0b2\x12.proto.Type.StringH\x00R\x06string\x12,\n\x06binary\x18\r \x01(\x0b2\x12.proto.Type.BinaryH\x00R\x06binary\x125\n\ttimestamp\x18\x0e \x01(\x0b2\x15.proto.Type.TimestampH\x00R\ttimestamp\x12&\n\x04date\x18\x10 \x01(\x0b2\x10.proto.Type.DateH\x00R\x04date\x12&\n\x04time\x18\x11 \x01(\x0b2\x10.proto.Type.TimeH\x00R\x04time\x12?\n\rinterval_year\x18\x13 \x01(\x0b2\x18.proto.Type.IntervalYearH\x00R\x0cintervalYear\x12<\n\x0cinterval_day\x18\x14 \x01(\x0b2\x17.proto.Type.IntervalDayH\x00R\x0bintervalDay\x12<\n\x0ctimestamp_tz\x18\x1d \x01(\x0b2\x17.proto.Type.TimestampTZH\x00R\x0btimestampTz\x12&\n\x04uuid\x18  \x01(\x0b2\x10.proto.Type.UUIDH\x00R\x04uuid\x126\n\nfixed_char\x18\x15 \x01(\x0b2\x15.proto.Type.FixedCharH\x00R\tfixedChar\x12/\n\x07varchar\x18\x16 \x01(\x0b2\x13.proto.Type.VarCharH\x00R\x07varchar\x12<\n\x0cfixed_binary\x18\x17 \x01(\x0b2\x17.proto.Type.FixedBinaryH\x00R\x0bfixedBinary\x12/\n\x07decimal\x18\x18 \x01(\x0b2\x13.proto.Type.DecimalH\x00R\x07decimal\x12,\n\x06struct\x18\x19 \x01(\x0b2\x12.proto.Type.StructH\x00R\x06struct\x12&\n\x04list\x18\x1b \x01(\x0b2\x10.proto.Type.ListH\x00R\x04list\x12#\n\x03map\x18\x1c \x01(\x0b2\x0f.proto.Type.MapH\x00R\x03map\x12<\n\x0cuser_defined\x18\x1e \x01(\x0b2\x17.proto.Type.UserDefinedH\x00R\x0buserDefined\x12C\n\x1buser_defined_type_reference\x18\x1f \x01(\rB\x02\x18\x01H\x00R\x18userDefinedTypeReference\x1a~\n\x07Boolean\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1ay\n\x02I8\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1az\n\x03I16\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1az\n\x03I32\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1az\n\x03I64\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a{\n\x04FP32\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a{\n\x04FP64\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a}\n\x06String\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a}\n\x06Binary\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x80\x01\n\tTimestamp\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a{\n\x04Date\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a{\n\x04Time\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x82\x01\n\x0bTimestampTZ\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x83\x01\n\x0cIntervalYear\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x82\x01\n\x0bIntervalDay\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a{\n\x04UUID\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x02 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x98\x01\n\tFixedChar\x12\x16\n\x06length\x18\x01 \x01(\x05R\x06length\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x96\x01\n\x07VarChar\x12\x16\n\x06length\x18\x01 \x01(\x05R\x06length\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x9a\x01\n\x0bFixedBinary\x12\x16\n\x06length\x18\x01 \x01(\x05R\x06length\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xb2\x01\n\x07Decimal\x12\x14\n\x05scale\x18\x01 \x01(\x05R\x05scale\x12\x1c\n\tprecision\x18\x02 \x01(\x05R\tprecision\x128\n\x18type_variation_reference\x18\x03 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x04 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xa0\x01\n\x06Struct\x12!\n\x05types\x18\x01 \x03(\x0b2\x0b.proto.TypeR\x05types\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x9c\x01\n\x04List\x12\x1f\n\x04type\x18\x01 \x01(\x0b2\x0b.proto.TypeR\x04type\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xbc\x01\n\x03Map\x12\x1d\n\x03key\x18\x01 \x01(\x0b2\x0b.proto.TypeR\x03key\x12!\n\x05value\x18\x02 \x01(\x0b2\x0b.proto.TypeR\x05value\x128\n\x18type_variation_reference\x18\x03 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x04 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xe9\x01\n\x0bUserDefined\x12%\n\x0etype_reference\x18\x01 \x01(\rR\rtypeReference\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x12>\n\x0ftype_parameters\x18\x04 \x03(\x0b2\x15.proto.Type.ParameterR\x0etypeParameters\x1a\xda\x01\n\tParameter\x12,\n\x04null\x18\x01 \x01(\x0b2\x16.google.protobuf.EmptyH\x00R\x04null\x12*\n\tdata_type\x18\x02 \x01(\x0b2\x0b.proto.TypeH\x00R\x08dataType\x12\x1a\n\x07boolean\x18\x03 \x01(\x08H\x00R\x07boolean\x12\x1a\n\x07integer\x18\x04 \x01(\x03H\x00R\x07integer\x12\x14\n\x04enum\x18\x05 \x01(\tH\x00R\x04enum\x12\x18\n\x06string\x18\x06 \x01(\tH\x00R\x06stringB\x0b\n\tparameter"^\n\x0bNullability\x12\x1b\n\x17NULLABILITY_UNSPECIFIED\x10\x00\x12\x18\n\x14NULLABILITY_NULLABLE\x10\x01\x12\x18\n\x14NULLABILITY_REQUIRED\x10\x02B\x06\n\x04kind"O\n\x0bNamedStruct\x12\x14\n\x05names\x18\x01 \x03(\tR\x05names\x12*\n\x06struct\x18\x02 \x01(\x0b2\x12.proto.Type.StructR\x06structB#\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobufb\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'proto.type_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b'\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobuf'
    _TYPE.fields_by_name['user_defined_type_reference']._options = None
    _TYPE.fields_by_name['user_defined_type_reference']._serialized_options = b'\x18\x01'
    _TYPE._serialized_start = 57
    _TYPE._serialized_end = 5010
    _TYPE_BOOLEAN._serialized_start = 1259
    _TYPE_BOOLEAN._serialized_end = 1385
    _TYPE_I8._serialized_start = 1387
    _TYPE_I8._serialized_end = 1508
    _TYPE_I16._serialized_start = 1510
    _TYPE_I16._serialized_end = 1632
    _TYPE_I32._serialized_start = 1634
    _TYPE_I32._serialized_end = 1756
    _TYPE_I64._serialized_start = 1758
    _TYPE_I64._serialized_end = 1880
    _TYPE_FP32._serialized_start = 1882
    _TYPE_FP32._serialized_end = 2005
    _TYPE_FP64._serialized_start = 2007
    _TYPE_FP64._serialized_end = 2130
    _TYPE_STRING._serialized_start = 2132
    _TYPE_STRING._serialized_end = 2257
    _TYPE_BINARY._serialized_start = 2259
    _TYPE_BINARY._serialized_end = 2384
    _TYPE_TIMESTAMP._serialized_start = 2387
    _TYPE_TIMESTAMP._serialized_end = 2515
    _TYPE_DATE._serialized_start = 2517
    _TYPE_DATE._serialized_end = 2640
    _TYPE_TIME._serialized_start = 2642
    _TYPE_TIME._serialized_end = 2765
    _TYPE_TIMESTAMPTZ._serialized_start = 2768
    _TYPE_TIMESTAMPTZ._serialized_end = 2898
    _TYPE_INTERVALYEAR._serialized_start = 2901
    _TYPE_INTERVALYEAR._serialized_end = 3032
    _TYPE_INTERVALDAY._serialized_start = 3035
    _TYPE_INTERVALDAY._serialized_end = 3165
    _TYPE_UUID._serialized_start = 3167
    _TYPE_UUID._serialized_end = 3290
    _TYPE_FIXEDCHAR._serialized_start = 3293
    _TYPE_FIXEDCHAR._serialized_end = 3445
    _TYPE_VARCHAR._serialized_start = 3448
    _TYPE_VARCHAR._serialized_end = 3598
    _TYPE_FIXEDBINARY._serialized_start = 3601
    _TYPE_FIXEDBINARY._serialized_end = 3755
    _TYPE_DECIMAL._serialized_start = 3758
    _TYPE_DECIMAL._serialized_end = 3936
    _TYPE_STRUCT._serialized_start = 3939
    _TYPE_STRUCT._serialized_end = 4099
    _TYPE_LIST._serialized_start = 4102
    _TYPE_LIST._serialized_end = 4258
    _TYPE_MAP._serialized_start = 4261
    _TYPE_MAP._serialized_end = 4449
    _TYPE_USERDEFINED._serialized_start = 4452
    _TYPE_USERDEFINED._serialized_end = 4685
    _TYPE_PARAMETER._serialized_start = 4688
    _TYPE_PARAMETER._serialized_end = 4906
    _TYPE_NULLABILITY._serialized_start = 4908
    _TYPE_NULLABILITY._serialized_end = 5002
    _NAMEDSTRUCT._serialized_start = 5012
    _NAMEDSTRUCT._serialized_end = 5091