"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
_sym_db = _symbol_database.Default()
from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x16pysubstrait/type.proto\x12\x0bpysubstrait\x1a\x1bgoogle/protobuf/empty.proto"\xa8)\n\x04Type\x12/\n\x04bool\x18\x01 \x01(\x0b2\x19.pysubstrait.Type.BooleanH\x00R\x04bool\x12&\n\x02i8\x18\x02 \x01(\x0b2\x14.pysubstrait.Type.I8H\x00R\x02i8\x12)\n\x03i16\x18\x03 \x01(\x0b2\x15.pysubstrait.Type.I16H\x00R\x03i16\x12)\n\x03i32\x18\x05 \x01(\x0b2\x15.pysubstrait.Type.I32H\x00R\x03i32\x12)\n\x03i64\x18\x07 \x01(\x0b2\x15.pysubstrait.Type.I64H\x00R\x03i64\x12,\n\x04fp32\x18\n \x01(\x0b2\x16.pysubstrait.Type.FP32H\x00R\x04fp32\x12,\n\x04fp64\x18\x0b \x01(\x0b2\x16.pysubstrait.Type.FP64H\x00R\x04fp64\x122\n\x06string\x18\x0c \x01(\x0b2\x18.pysubstrait.Type.StringH\x00R\x06string\x122\n\x06binary\x18\r \x01(\x0b2\x18.pysubstrait.Type.BinaryH\x00R\x06binary\x12;\n\ttimestamp\x18\x0e \x01(\x0b2\x1b.pysubstrait.Type.TimestampH\x00R\ttimestamp\x12,\n\x04date\x18\x10 \x01(\x0b2\x16.pysubstrait.Type.DateH\x00R\x04date\x12,\n\x04time\x18\x11 \x01(\x0b2\x16.pysubstrait.Type.TimeH\x00R\x04time\x12E\n\rinterval_year\x18\x13 \x01(\x0b2\x1e.pysubstrait.Type.IntervalYearH\x00R\x0cintervalYear\x12B\n\x0cinterval_day\x18\x14 \x01(\x0b2\x1d.pysubstrait.Type.IntervalDayH\x00R\x0bintervalDay\x12B\n\x0ctimestamp_tz\x18\x1d \x01(\x0b2\x1d.pysubstrait.Type.TimestampTZH\x00R\x0btimestampTz\x12,\n\x04uuid\x18  \x01(\x0b2\x16.pysubstrait.Type.UUIDH\x00R\x04uuid\x12<\n\nfixed_char\x18\x15 \x01(\x0b2\x1b.pysubstrait.Type.FixedCharH\x00R\tfixedChar\x125\n\x07varchar\x18\x16 \x01(\x0b2\x19.pysubstrait.Type.VarCharH\x00R\x07varchar\x12B\n\x0cfixed_binary\x18\x17 \x01(\x0b2\x1d.pysubstrait.Type.FixedBinaryH\x00R\x0bfixedBinary\x125\n\x07decimal\x18\x18 \x01(\x0b2\x19.pysubstrait.Type.DecimalH\x00R\x07decimal\x122\n\x06struct\x18\x19 \x01(\x0b2\x18.pysubstrait.Type.StructH\x00R\x06struct\x12,\n\x04list\x18\x1b \x01(\x0b2\x16.pysubstrait.Type.ListH\x00R\x04list\x12)\n\x03map\x18\x1c \x01(\x0b2\x15.pysubstrait.Type.MapH\x00R\x03map\x12B\n\x0cuser_defined\x18\x1e \x01(\x0b2\x1d.pysubstrait.Type.UserDefinedH\x00R\x0buserDefined\x12C\n\x1buser_defined_type_reference\x18\x1f \x01(\rB\x02\x18\x01H\x00R\x18userDefinedTypeReference\x1a\x84\x01\n\x07Boolean\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x7f\n\x02I8\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x80\x01\n\x03I16\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x80\x01\n\x03I32\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x80\x01\n\x03I64\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x81\x01\n\x04FP32\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x81\x01\n\x04FP64\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x83\x01\n\x06String\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x83\x01\n\x06Binary\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x86\x01\n\tTimestamp\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x81\x01\n\x04Date\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x81\x01\n\x04Time\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x88\x01\n\x0bTimestampTZ\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x89\x01\n\x0cIntervalYear\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x88\x01\n\x0bIntervalDay\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x81\x01\n\x04UUID\x128\n\x18type_variation_reference\x18\x01 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x02 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x9e\x01\n\tFixedChar\x12\x16\n\x06length\x18\x01 \x01(\x05R\x06length\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x03 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\x9c\x01\n\x07VarChar\x12\x16\n\x06length\x18\x01 \x01(\x05R\x06length\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x03 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\xa0\x01\n\x0bFixedBinary\x12\x16\n\x06length\x18\x01 \x01(\x05R\x06length\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x03 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\xb8\x01\n\x07Decimal\x12\x14\n\x05scale\x18\x01 \x01(\x05R\x05scale\x12\x1c\n\tprecision\x18\x02 \x01(\x05R\tprecision\x128\n\x18type_variation_reference\x18\x03 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x04 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\xac\x01\n\x06Struct\x12\'\n\x05types\x18\x01 \x03(\x0b2\x11.pysubstrait.TypeR\x05types\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x03 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\xa8\x01\n\x04List\x12%\n\x04type\x18\x01 \x01(\x0b2\x11.pysubstrait.TypeR\x04type\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x03 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\xce\x01\n\x03Map\x12#\n\x03key\x18\x01 \x01(\x0b2\x11.pysubstrait.TypeR\x03key\x12\'\n\x05value\x18\x02 \x01(\x0b2\x11.pysubstrait.TypeR\x05value\x128\n\x18type_variation_reference\x18\x03 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x04 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x1a\xf5\x01\n\x0bUserDefined\x12%\n\x0etype_reference\x18\x01 \x01(\rR\rtypeReference\x128\n\x18type_variation_reference\x18\x02 \x01(\rR\x16typeVariationReference\x12?\n\x0bnullability\x18\x03 \x01(\x0e2\x1d.pysubstrait.Type.NullabilityR\x0bnullability\x12D\n\x0ftype_parameters\x18\x04 \x03(\x0b2\x1b.pysubstrait.Type.ParameterR\x0etypeParameters\x1a\xe0\x01\n\tParameter\x12,\n\x04null\x18\x01 \x01(\x0b2\x16.google.protobuf.EmptyH\x00R\x04null\x120\n\tdata_type\x18\x02 \x01(\x0b2\x11.pysubstrait.TypeH\x00R\x08dataType\x12\x1a\n\x07boolean\x18\x03 \x01(\x08H\x00R\x07boolean\x12\x1a\n\x07integer\x18\x04 \x01(\x03H\x00R\x07integer\x12\x14\n\x04enum\x18\x05 \x01(\tH\x00R\x04enum\x12\x18\n\x06string\x18\x06 \x01(\tH\x00R\x06stringB\x0b\n\tparameter"^\n\x0bNullability\x12\x1b\n\x17NULLABILITY_UNSPECIFIED\x10\x00\x12\x18\n\x14NULLABILITY_NULLABLE\x10\x01\x12\x18\n\x14NULLABILITY_REQUIRED\x10\x02B\x06\n\x04kind"U\n\x0bNamedStruct\x12\x14\n\x05names\x18\x01 \x03(\tR\x05names\x120\n\x06struct\x18\x02 \x01(\x0b2\x18.pysubstrait.Type.StructR\x06structB/\n\x14io.pysubstrait.protoP\x01\xaa\x02\x14Pysubstrait.Protobufb\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'pysubstrait.type_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b'\n\x14io.pysubstrait.protoP\x01\xaa\x02\x14Pysubstrait.Protobuf'
    _TYPE.fields_by_name['user_defined_type_reference']._options = None
    _TYPE.fields_by_name['user_defined_type_reference']._serialized_options = b'\x18\x01'
    _TYPE._serialized_start = 69
    _TYPE._serialized_end = 5357
    _TYPE_BOOLEAN._serialized_start = 1416
    _TYPE_BOOLEAN._serialized_end = 1548
    _TYPE_I8._serialized_start = 1550
    _TYPE_I8._serialized_end = 1677
    _TYPE_I16._serialized_start = 1680
    _TYPE_I16._serialized_end = 1808
    _TYPE_I32._serialized_start = 1811
    _TYPE_I32._serialized_end = 1939
    _TYPE_I64._serialized_start = 1942
    _TYPE_I64._serialized_end = 2070
    _TYPE_FP32._serialized_start = 2073
    _TYPE_FP32._serialized_end = 2202
    _TYPE_FP64._serialized_start = 2205
    _TYPE_FP64._serialized_end = 2334
    _TYPE_STRING._serialized_start = 2337
    _TYPE_STRING._serialized_end = 2468
    _TYPE_BINARY._serialized_start = 2471
    _TYPE_BINARY._serialized_end = 2602
    _TYPE_TIMESTAMP._serialized_start = 2605
    _TYPE_TIMESTAMP._serialized_end = 2739
    _TYPE_DATE._serialized_start = 2742
    _TYPE_DATE._serialized_end = 2871
    _TYPE_TIME._serialized_start = 2874
    _TYPE_TIME._serialized_end = 3003
    _TYPE_TIMESTAMPTZ._serialized_start = 3006
    _TYPE_TIMESTAMPTZ._serialized_end = 3142
    _TYPE_INTERVALYEAR._serialized_start = 3145
    _TYPE_INTERVALYEAR._serialized_end = 3282
    _TYPE_INTERVALDAY._serialized_start = 3285
    _TYPE_INTERVALDAY._serialized_end = 3421
    _TYPE_UUID._serialized_start = 3424
    _TYPE_UUID._serialized_end = 3553
    _TYPE_FIXEDCHAR._serialized_start = 3556
    _TYPE_FIXEDCHAR._serialized_end = 3714
    _TYPE_VARCHAR._serialized_start = 3717
    _TYPE_VARCHAR._serialized_end = 3873
    _TYPE_FIXEDBINARY._serialized_start = 3876
    _TYPE_FIXEDBINARY._serialized_end = 4036
    _TYPE_DECIMAL._serialized_start = 4039
    _TYPE_DECIMAL._serialized_end = 4223
    _TYPE_STRUCT._serialized_start = 4226
    _TYPE_STRUCT._serialized_end = 4398
    _TYPE_LIST._serialized_start = 4401
    _TYPE_LIST._serialized_end = 4569
    _TYPE_MAP._serialized_start = 4572
    _TYPE_MAP._serialized_end = 4778
    _TYPE_USERDEFINED._serialized_start = 4781
    _TYPE_USERDEFINED._serialized_end = 5026
    _TYPE_PARAMETER._serialized_start = 5029
    _TYPE_PARAMETER._serialized_end = 5253
    _TYPE_NULLABILITY._serialized_start = 5255
    _TYPE_NULLABILITY._serialized_end = 5349
    _NAMEDSTRUCT._serialized_start = 5359
    _NAMEDSTRUCT._serialized_end = 5444