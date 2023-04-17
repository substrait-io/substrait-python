"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
_sym_db = _symbol_database.Default()
from ..pysubstrait import parameterized_types_pb2 as pysubstrait_dot_parameterized__types__pb2
from ..pysubstrait import type_pb2 as pysubstrait_dot_type__pb2
from ..pysubstrait import type_expressions_pb2 as pysubstrait_dot_type__expressions__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1apysubstrait/function.proto\x12\x0bpysubstrait\x1a%pysubstrait/parameterized_types.proto\x1a\x16pysubstrait/type.proto\x1a"pysubstrait/type_expressions.proto"\x91\x1a\n\x11FunctionSignature\x1a\xbe\x02\n\x10FinalArgVariadic\x12\x19\n\x08min_args\x18\x01 \x01(\x03R\x07minArgs\x12\x19\n\x08max_args\x18\x02 \x01(\x03R\x07maxArgs\x12f\n\x0bconsistency\x18\x03 \x01(\x0e2D.pysubstrait.FunctionSignature.FinalArgVariadic.ParameterConsistencyR\x0bconsistency"\x8b\x01\n\x14ParameterConsistency\x12%\n!PARAMETER_CONSISTENCY_UNSPECIFIED\x10\x00\x12$\n PARAMETER_CONSISTENCY_CONSISTENT\x10\x01\x12&\n"PARAMETER_CONSISTENCY_INCONSISTENT\x10\x02\x1a\x10\n\x0eFinalArgNormal\x1a\xd4\x04\n\x06Scalar\x12E\n\targuments\x18\x02 \x03(\x0b2\'.pysubstrait.FunctionSignature.ArgumentR\targuments\x12\x12\n\x04name\x18\x03 \x03(\tR\x04name\x12L\n\x0bdescription\x18\x04 \x01(\x0b2*.pysubstrait.FunctionSignature.DescriptionR\x0bdescription\x12$\n\rdeterministic\x18\x07 \x01(\x08R\rdeterministic\x12+\n\x11session_dependent\x18\x08 \x01(\x08R\x10sessionDependent\x12B\n\x0boutput_type\x18\t \x01(\x0b2!.pysubstrait.DerivationExpressionR\noutputType\x12M\n\x08variadic\x18\n \x01(\x0b2/.pysubstrait.FunctionSignature.FinalArgVariadicH\x00R\x08variadic\x12G\n\x06normal\x18\x0b \x01(\x0b2-.pysubstrait.FunctionSignature.FinalArgNormalH\x00R\x06normal\x12W\n\x0fimplementations\x18\x0c \x03(\x0b2-.pysubstrait.FunctionSignature.ImplementationR\x0fimplementationsB\x19\n\x17final_variable_behavior\x1a\xca\x05\n\tAggregate\x12E\n\targuments\x18\x02 \x03(\x0b2\'.pysubstrait.FunctionSignature.ArgumentR\targuments\x12\x12\n\x04name\x18\x03 \x01(\tR\x04name\x12L\n\x0bdescription\x18\x04 \x01(\x0b2*.pysubstrait.FunctionSignature.DescriptionR\x0bdescription\x12$\n\rdeterministic\x18\x07 \x01(\x08R\rdeterministic\x12+\n\x11session_dependent\x18\x08 \x01(\x08R\x10sessionDependent\x12B\n\x0boutput_type\x18\t \x01(\x0b2!.pysubstrait.DerivationExpressionR\noutputType\x12M\n\x08variadic\x18\n \x01(\x0b2/.pysubstrait.FunctionSignature.FinalArgVariadicH\x00R\x08variadic\x12G\n\x06normal\x18\x0b \x01(\x0b2-.pysubstrait.FunctionSignature.FinalArgNormalH\x00R\x06normal\x12\x18\n\x07ordered\x18\x0e \x01(\x08R\x07ordered\x12\x17\n\x07max_set\x18\x0c \x01(\x04R\x06maxSet\x12>\n\x11intermediate_type\x18\r \x01(\x0b2\x11.pysubstrait.TypeR\x10intermediateType\x12W\n\x0fimplementations\x18\x0f \x03(\x0b2-.pysubstrait.FunctionSignature.ImplementationR\x0fimplementationsB\x19\n\x17final_variable_behavior\x1a\x8b\x07\n\x06Window\x12E\n\targuments\x18\x02 \x03(\x0b2\'.pysubstrait.FunctionSignature.ArgumentR\targuments\x12\x12\n\x04name\x18\x03 \x03(\tR\x04name\x12L\n\x0bdescription\x18\x04 \x01(\x0b2*.pysubstrait.FunctionSignature.DescriptionR\x0bdescription\x12$\n\rdeterministic\x18\x07 \x01(\x08R\rdeterministic\x12+\n\x11session_dependent\x18\x08 \x01(\x08R\x10sessionDependent\x12N\n\x11intermediate_type\x18\t \x01(\x0b2!.pysubstrait.DerivationExpressionR\x10intermediateType\x12B\n\x0boutput_type\x18\n \x01(\x0b2!.pysubstrait.DerivationExpressionR\noutputType\x12M\n\x08variadic\x18\x10 \x01(\x0b2/.pysubstrait.FunctionSignature.FinalArgVariadicH\x00R\x08variadic\x12G\n\x06normal\x18\x11 \x01(\x0b2-.pysubstrait.FunctionSignature.FinalArgNormalH\x00R\x06normal\x12\x18\n\x07ordered\x18\x0b \x01(\x08R\x07ordered\x12\x17\n\x07max_set\x18\x0c \x01(\x04R\x06maxSet\x12Q\n\x0bwindow_type\x18\x0e \x01(\x0e20.pysubstrait.FunctionSignature.Window.WindowTypeR\nwindowType\x12W\n\x0fimplementations\x18\x0f \x03(\x0b2-.pysubstrait.FunctionSignature.ImplementationR\x0fimplementations"_\n\nWindowType\x12\x1b\n\x17WINDOW_TYPE_UNSPECIFIED\x10\x00\x12\x19\n\x15WINDOW_TYPE_STREAMING\x10\x01\x12\x19\n\x15WINDOW_TYPE_PARTITION\x10\x02B\x19\n\x17final_variable_behavior\x1a=\n\x0bDescription\x12\x1a\n\x08language\x18\x01 \x01(\tR\x08language\x12\x12\n\x04body\x18\x02 \x01(\tR\x04body\x1a\xb3\x01\n\x0eImplementation\x12F\n\x04type\x18\x01 \x01(\x0e22.pysubstrait.FunctionSignature.Implementation.TypeR\x04type\x12\x10\n\x03uri\x18\x02 \x01(\tR\x03uri"G\n\x04Type\x12\x14\n\x10TYPE_UNSPECIFIED\x10\x00\x12\x15\n\x11TYPE_WEB_ASSEMBLY\x10\x01\x12\x12\n\x0eTYPE_TRINO_JAR\x10\x02\x1a\x81\x04\n\x08Argument\x12\x12\n\x04name\x18\x01 \x01(\tR\x04name\x12M\n\x05value\x18\x02 \x01(\x0b25.pysubstrait.FunctionSignature.Argument.ValueArgumentH\x00R\x05value\x12J\n\x04type\x18\x03 \x01(\x0b24.pysubstrait.FunctionSignature.Argument.TypeArgumentH\x00R\x04type\x12J\n\x04enum\x18\x04 \x01(\x0b24.pysubstrait.FunctionSignature.Argument.EnumArgumentH\x00R\x04enum\x1a_\n\rValueArgument\x122\n\x04type\x18\x01 \x01(\x0b2\x1e.pysubstrait.ParameterizedTypeR\x04type\x12\x1a\n\x08constant\x18\x02 \x01(\x08R\x08constant\x1aB\n\x0cTypeArgument\x122\n\x04type\x18\x01 \x01(\x0b2\x1e.pysubstrait.ParameterizedTypeR\x04type\x1aD\n\x0cEnumArgument\x12\x18\n\x07options\x18\x01 \x03(\tR\x07options\x12\x1a\n\x08optional\x18\x02 \x01(\x08R\x08optionalB\x0f\n\rargument_kindB/\n\x14io.pysubstrait.protoP\x01\xaa\x02\x14Pysubstrait.Protobufb\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'pysubstrait.function_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b'\n\x14io.pysubstrait.protoP\x01\xaa\x02\x14Pysubstrait.Protobuf'
    _FUNCTIONSIGNATURE._serialized_start = 143
    _FUNCTIONSIGNATURE._serialized_end = 3488
    _FUNCTIONSIGNATURE_FINALARGVARIADIC._serialized_start = 165
    _FUNCTIONSIGNATURE_FINALARGVARIADIC._serialized_end = 483
    _FUNCTIONSIGNATURE_FINALARGVARIADIC_PARAMETERCONSISTENCY._serialized_start = 344
    _FUNCTIONSIGNATURE_FINALARGVARIADIC_PARAMETERCONSISTENCY._serialized_end = 483
    _FUNCTIONSIGNATURE_FINALARGNORMAL._serialized_start = 485
    _FUNCTIONSIGNATURE_FINALARGNORMAL._serialized_end = 501
    _FUNCTIONSIGNATURE_SCALAR._serialized_start = 504
    _FUNCTIONSIGNATURE_SCALAR._serialized_end = 1100
    _FUNCTIONSIGNATURE_AGGREGATE._serialized_start = 1103
    _FUNCTIONSIGNATURE_AGGREGATE._serialized_end = 1817
    _FUNCTIONSIGNATURE_WINDOW._serialized_start = 1820
    _FUNCTIONSIGNATURE_WINDOW._serialized_end = 2727
    _FUNCTIONSIGNATURE_WINDOW_WINDOWTYPE._serialized_start = 2605
    _FUNCTIONSIGNATURE_WINDOW_WINDOWTYPE._serialized_end = 2700
    _FUNCTIONSIGNATURE_DESCRIPTION._serialized_start = 2729
    _FUNCTIONSIGNATURE_DESCRIPTION._serialized_end = 2790
    _FUNCTIONSIGNATURE_IMPLEMENTATION._serialized_start = 2793
    _FUNCTIONSIGNATURE_IMPLEMENTATION._serialized_end = 2972
    _FUNCTIONSIGNATURE_IMPLEMENTATION_TYPE._serialized_start = 2901
    _FUNCTIONSIGNATURE_IMPLEMENTATION_TYPE._serialized_end = 2972
    _FUNCTIONSIGNATURE_ARGUMENT._serialized_start = 2975
    _FUNCTIONSIGNATURE_ARGUMENT._serialized_end = 3488
    _FUNCTIONSIGNATURE_ARGUMENT_VALUEARGUMENT._serialized_start = 3238
    _FUNCTIONSIGNATURE_ARGUMENT_VALUEARGUMENT._serialized_end = 3333
    _FUNCTIONSIGNATURE_ARGUMENT_TYPEARGUMENT._serialized_start = 3335
    _FUNCTIONSIGNATURE_ARGUMENT_TYPEARGUMENT._serialized_end = 3401
    _FUNCTIONSIGNATURE_ARGUMENT_ENUMARGUMENT._serialized_start = 3403
    _FUNCTIONSIGNATURE_ARGUMENT_ENUMARGUMENT._serialized_end = 3471