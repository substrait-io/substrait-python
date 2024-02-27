"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
_sym_db = _symbol_database.Default()
from ..proto import type_pb2 as proto_dot_type__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1fproto/parameterized_types.proto\x12\x05proto\x1a\x10proto/type.proto"\xf5!\n\x11ParameterizedType\x12)\n\x04bool\x18\x01 \x01(\x0b2\x13.proto.Type.BooleanH\x00R\x04bool\x12 \n\x02i8\x18\x02 \x01(\x0b2\x0e.proto.Type.I8H\x00R\x02i8\x12#\n\x03i16\x18\x03 \x01(\x0b2\x0f.proto.Type.I16H\x00R\x03i16\x12#\n\x03i32\x18\x05 \x01(\x0b2\x0f.proto.Type.I32H\x00R\x03i32\x12#\n\x03i64\x18\x07 \x01(\x0b2\x0f.proto.Type.I64H\x00R\x03i64\x12&\n\x04fp32\x18\n \x01(\x0b2\x10.proto.Type.FP32H\x00R\x04fp32\x12&\n\x04fp64\x18\x0b \x01(\x0b2\x10.proto.Type.FP64H\x00R\x04fp64\x12,\n\x06string\x18\x0c \x01(\x0b2\x12.proto.Type.StringH\x00R\x06string\x12,\n\x06binary\x18\r \x01(\x0b2\x12.proto.Type.BinaryH\x00R\x06binary\x129\n\ttimestamp\x18\x0e \x01(\x0b2\x15.proto.Type.TimestampB\x02\x18\x01H\x00R\ttimestamp\x12&\n\x04date\x18\x10 \x01(\x0b2\x10.proto.Type.DateH\x00R\x04date\x12&\n\x04time\x18\x11 \x01(\x0b2\x10.proto.Type.TimeH\x00R\x04time\x12?\n\rinterval_year\x18\x13 \x01(\x0b2\x18.proto.Type.IntervalYearH\x00R\x0cintervalYear\x12<\n\x0cinterval_day\x18\x14 \x01(\x0b2\x17.proto.Type.IntervalDayH\x00R\x0bintervalDay\x12@\n\x0ctimestamp_tz\x18\x1d \x01(\x0b2\x17.proto.Type.TimestampTZB\x02\x18\x01H\x00R\x0btimestampTz\x12&\n\x04uuid\x18  \x01(\x0b2\x10.proto.Type.UUIDH\x00R\x04uuid\x12P\n\nfixed_char\x18\x15 \x01(\x0b2/.proto.ParameterizedType.ParameterizedFixedCharH\x00R\tfixedChar\x12I\n\x07varchar\x18\x16 \x01(\x0b2-.proto.ParameterizedType.ParameterizedVarCharH\x00R\x07varchar\x12V\n\x0cfixed_binary\x18\x17 \x01(\x0b21.proto.ParameterizedType.ParameterizedFixedBinaryH\x00R\x0bfixedBinary\x12I\n\x07decimal\x18\x18 \x01(\x0b2-.proto.ParameterizedType.ParameterizedDecimalH\x00R\x07decimal\x12k\n\x13precision_timestamp\x18" \x01(\x0b28.proto.ParameterizedType.ParameterizedPrecisionTimestampH\x00R\x12precisionTimestamp\x12r\n\x16precision_timestamp_tz\x18# \x01(\x0b2:.proto.ParameterizedType.ParameterizedPrecisionTimestampTZH\x00R\x14precisionTimestampTz\x12F\n\x06struct\x18\x19 \x01(\x0b2,.proto.ParameterizedType.ParameterizedStructH\x00R\x06struct\x12@\n\x04list\x18\x1b \x01(\x0b2*.proto.ParameterizedType.ParameterizedListH\x00R\x04list\x12=\n\x03map\x18\x1c \x01(\x0b2).proto.ParameterizedType.ParameterizedMapH\x00R\x03map\x12V\n\x0cuser_defined\x18\x1e \x01(\x0b21.proto.ParameterizedType.ParameterizedUserDefinedH\x00R\x0buserDefined\x126\n\x14user_defined_pointer\x18\x1f \x01(\rB\x02\x18\x01H\x00R\x12userDefinedPointer\x12O\n\x0etype_parameter\x18! \x01(\x0b2&.proto.ParameterizedType.TypeParameterH\x00R\rtypeParameter\x1aU\n\rTypeParameter\x12\x12\n\x04name\x18\x01 \x01(\tR\x04name\x120\n\x06bounds\x18\x02 \x03(\x0b2\x18.proto.ParameterizedTypeR\x06bounds\x1a\xde\x01\n\x10IntegerParameter\x12\x12\n\x04name\x18\x01 \x01(\tR\x04name\x12\\\n\x15range_start_inclusive\x18\x02 \x01(\x0b2(.proto.ParameterizedType.NullableIntegerR\x13rangeStartInclusive\x12X\n\x13range_end_exclusive\x18\x03 \x01(\x0b2(.proto.ParameterizedType.NullableIntegerR\x11rangeEndExclusive\x1a\'\n\x0fNullableInteger\x12\x14\n\x05value\x18\x01 \x01(\x03R\x05value\x1a\xc0\x01\n\x16ParameterizedFixedChar\x12>\n\x06length\x18\x01 \x01(\x0b2&.proto.ParameterizedType.IntegerOptionR\x06length\x12+\n\x11variation_pointer\x18\x02 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xbe\x01\n\x14ParameterizedVarChar\x12>\n\x06length\x18\x01 \x01(\x0b2&.proto.ParameterizedType.IntegerOptionR\x06length\x12+\n\x11variation_pointer\x18\x02 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xc2\x01\n\x18ParameterizedFixedBinary\x12>\n\x06length\x18\x01 \x01(\x0b2&.proto.ParameterizedType.IntegerOptionR\x06length\x12+\n\x11variation_pointer\x18\x02 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x82\x02\n\x14ParameterizedDecimal\x12<\n\x05scale\x18\x01 \x01(\x0b2&.proto.ParameterizedType.IntegerOptionR\x05scale\x12D\n\tprecision\x18\x02 \x01(\x0b2&.proto.ParameterizedType.IntegerOptionR\tprecision\x12+\n\x11variation_pointer\x18\x03 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x04 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xcf\x01\n\x1fParameterizedPrecisionTimestamp\x12D\n\tprecision\x18\x01 \x01(\x0b2&.proto.ParameterizedType.IntegerOptionR\tprecision\x12+\n\x11variation_pointer\x18\x02 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xd1\x01\n!ParameterizedPrecisionTimestampTZ\x12D\n\tprecision\x18\x01 \x01(\x0b2&.proto.ParameterizedType.IntegerOptionR\tprecision\x12+\n\x11variation_pointer\x18\x02 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xad\x01\n\x13ParameterizedStruct\x12.\n\x05types\x18\x01 \x03(\x0b2\x18.proto.ParameterizedTypeR\x05types\x12+\n\x11variation_pointer\x18\x02 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1av\n\x18ParameterizedNamedStruct\x12\x14\n\x05names\x18\x01 \x03(\tR\x05names\x12D\n\x06struct\x18\x02 \x01(\x0b2,.proto.ParameterizedType.ParameterizedStructR\x06struct\x1a\xa9\x01\n\x11ParameterizedList\x12,\n\x04type\x18\x01 \x01(\x0b2\x18.proto.ParameterizedTypeR\x04type\x12+\n\x11variation_pointer\x18\x02 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xd6\x01\n\x10ParameterizedMap\x12*\n\x03key\x18\x01 \x01(\x0b2\x18.proto.ParameterizedTypeR\x03key\x12.\n\x05value\x18\x02 \x01(\x0b2\x18.proto.ParameterizedTypeR\x05value\x12+\n\x11variation_pointer\x18\x03 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x04 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\xa5\x01\n\x18ParameterizedUserDefined\x12!\n\x0ctype_pointer\x18\x01 \x01(\rR\x0btypePointer\x12+\n\x11variation_pointer\x18\x02 \x01(\rR\x10variationPointer\x129\n\x0bnullability\x18\x03 \x01(\x0e2\x17.proto.Type.NullabilityR\x0bnullability\x1a\x86\x01\n\rIntegerOption\x12\x1a\n\x07literal\x18\x01 \x01(\x05H\x00R\x07literal\x12I\n\tparameter\x18\x02 \x01(\x0b2).proto.ParameterizedType.IntegerParameterH\x00R\tparameterB\x0e\n\x0cinteger_typeB\x06\n\x04kindB#\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobufb\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'proto.parameterized_types_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b'\n\x0eio.proto.protoP\x01\xaa\x02\x0eProto.Protobuf'
    _PARAMETERIZEDTYPE.fields_by_name['timestamp']._options = None
    _PARAMETERIZEDTYPE.fields_by_name['timestamp']._serialized_options = b'\x18\x01'
    _PARAMETERIZEDTYPE.fields_by_name['timestamp_tz']._options = None
    _PARAMETERIZEDTYPE.fields_by_name['timestamp_tz']._serialized_options = b'\x18\x01'
    _PARAMETERIZEDTYPE.fields_by_name['user_defined_pointer']._options = None
    _PARAMETERIZEDTYPE.fields_by_name['user_defined_pointer']._serialized_options = b'\x18\x01'
    _PARAMETERIZEDTYPE._serialized_start = 61
    _PARAMETERIZEDTYPE._serialized_end = 4402
    _PARAMETERIZEDTYPE_TYPEPARAMETER._serialized_start = 1785
    _PARAMETERIZEDTYPE_TYPEPARAMETER._serialized_end = 1870
    _PARAMETERIZEDTYPE_INTEGERPARAMETER._serialized_start = 1873
    _PARAMETERIZEDTYPE_INTEGERPARAMETER._serialized_end = 2095
    _PARAMETERIZEDTYPE_NULLABLEINTEGER._serialized_start = 2097
    _PARAMETERIZEDTYPE_NULLABLEINTEGER._serialized_end = 2136
    _PARAMETERIZEDTYPE_PARAMETERIZEDFIXEDCHAR._serialized_start = 2139
    _PARAMETERIZEDTYPE_PARAMETERIZEDFIXEDCHAR._serialized_end = 2331
    _PARAMETERIZEDTYPE_PARAMETERIZEDVARCHAR._serialized_start = 2334
    _PARAMETERIZEDTYPE_PARAMETERIZEDVARCHAR._serialized_end = 2524
    _PARAMETERIZEDTYPE_PARAMETERIZEDFIXEDBINARY._serialized_start = 2527
    _PARAMETERIZEDTYPE_PARAMETERIZEDFIXEDBINARY._serialized_end = 2721
    _PARAMETERIZEDTYPE_PARAMETERIZEDDECIMAL._serialized_start = 2724
    _PARAMETERIZEDTYPE_PARAMETERIZEDDECIMAL._serialized_end = 2982
    _PARAMETERIZEDTYPE_PARAMETERIZEDPRECISIONTIMESTAMP._serialized_start = 2985
    _PARAMETERIZEDTYPE_PARAMETERIZEDPRECISIONTIMESTAMP._serialized_end = 3192
    _PARAMETERIZEDTYPE_PARAMETERIZEDPRECISIONTIMESTAMPTZ._serialized_start = 3195
    _PARAMETERIZEDTYPE_PARAMETERIZEDPRECISIONTIMESTAMPTZ._serialized_end = 3404
    _PARAMETERIZEDTYPE_PARAMETERIZEDSTRUCT._serialized_start = 3407
    _PARAMETERIZEDTYPE_PARAMETERIZEDSTRUCT._serialized_end = 3580
    _PARAMETERIZEDTYPE_PARAMETERIZEDNAMEDSTRUCT._serialized_start = 3582
    _PARAMETERIZEDTYPE_PARAMETERIZEDNAMEDSTRUCT._serialized_end = 3700
    _PARAMETERIZEDTYPE_PARAMETERIZEDLIST._serialized_start = 3703
    _PARAMETERIZEDTYPE_PARAMETERIZEDLIST._serialized_end = 3872
    _PARAMETERIZEDTYPE_PARAMETERIZEDMAP._serialized_start = 3875
    _PARAMETERIZEDTYPE_PARAMETERIZEDMAP._serialized_end = 4089
    _PARAMETERIZEDTYPE_PARAMETERIZEDUSERDEFINED._serialized_start = 4092
    _PARAMETERIZEDTYPE_PARAMETERIZEDUSERDEFINED._serialized_end = 4257
    _PARAMETERIZEDTYPE_INTEGEROPTION._serialized_start = 4260
    _PARAMETERIZEDTYPE_INTEGEROPTION._serialized_end = 4394