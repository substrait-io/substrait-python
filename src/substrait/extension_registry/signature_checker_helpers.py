"""Helper functions for extension registry."""

from typing import Dict

from substrait.derivation_expression import _evaluate
from substrait.gen.antlr.SubstraitTypeParser import SubstraitTypeParser
from substrait.gen.proto.type_pb2 import Type

from .exceptions import UnhandledParameterizedTypeError, UnrecognizedSubstraitTypeError

# Type aliases
TypeParameterMapping = Dict[str, object]


# mapping from argument types to shortened signature names: https://substrait.io/extensions/#function-signature-compound-names
_normalized_key_names = {
    "i8": "i8",
    "i16": "i16",
    "i32": "i32",
    "i64": "i64",
    "fp32": "fp32",
    "fp64": "fp64",
    "string": "str",
    "binary": "vbin",
    "boolean": "bool",
    "timestamp": "ts",
    "timestamp_tz": "tstz",
    "date": "date",
    "time": "time",
    "interval_year": "iyear",
    "interval_day": "iday",
    "interval_compound": "icompound",
    "uuid": "uuid",
    "fixedchar": "fchar",
    "varchar": "vchar",
    "fixedbinary": "fbin",
    "decimal": "dec",
    "precision_time": "pt",
    "precision_timestamp": "pts",
    "precision_timestamp_tz": "ptstz",
    "struct": "struct",
    "list": "list",
    "map": "map",
    "func": "func",
}


def normalize_substrait_type_names(typ: str) -> str:
    """Normalize Substrait type names to their canonical short forms.

    Args:
        typ: The type string to normalize (may include type specifiers and nullability markers)

    Returns:
        The normalized type name

    Raises:
        UnrecognizedSubstraitTypeError: If the type is not recognized
    """
    # Strip type specifiers
    typ = typ.split("<")[0]
    # First strip nullability marker
    typ = typ.strip("?").lower()
    if typ.startswith("any"):
        return "any"
    elif typ.startswith("u!"):
        return typ
    elif typ in _normalized_key_names:
        return _normalized_key_names[typ]
    else:
        raise UnrecognizedSubstraitTypeError(f"Unrecognized substrait type {typ}")


def _check_integer_constraint(
    actual: int, constraint, parameters: TypeParameterMapping, subset: bool = False
) -> bool:
    """Check if an actual integer value matches a constraint.

    Args:
        actual: The actual integer value to check
        constraint: An ANTLR context for either a numeric literal or parameter name
        parameters: Mapping of parameter names to their resolved values
        subset: If True, checks if actual < constraint (for subset relationships).
                If False, checks if actual == constraint (for exact match).

    Returns:
        True if the constraint is satisfied, False otherwise

    Raises:
        TypeError: If constraint is not NumericLiteralContext or NumericParameterNameContext
    """
    constraint_numeric: int | None = None
    if isinstance(constraint, SubstraitTypeParser.NumericLiteralContext):
        constraint_numeric = int(str(constraint.Number()))
    elif isinstance(constraint, SubstraitTypeParser.NumericParameterNameContext):
        parameter_name = str(constraint.Identifier())
        if parameter_name not in parameters:
            parameters[parameter_name] = actual
        if isinstance(parameters[parameter_name], int):
            constraint_numeric = parameters[parameter_name]  # type:ignore
    else:
        raise TypeError(
            f"Constraint must be either NumericLiteralContext or NumericParameterNameContext, "
            f"got {type(constraint).__name__} instead"
        )
    if constraint_numeric is None:
        return False
    elif subset:
        return actual < constraint_numeric
    else:
        return actual == constraint_numeric


def types_equal(type1: Type, type2: Type, check_nullability=False):
    if check_nullability:
        return type1 == type2
    else:
        x, y = Type(), Type()
        x.CopyFrom(type1)
        y.CopyFrom(type2)
        x.__getattribute__(
            x.WhichOneof("kind")  # type:ignore
        ).nullability = Type.Nullability.NULLABILITY_UNSPECIFIED
        y.__getattribute__(
            y.WhichOneof("kind")  # type:ignore
        ).nullability = Type.Nullability.NULLABILITY_UNSPECIFIED
        return x == y


def _bind_type_parameter(
    covered: Type,
    parameter_name: str,
    parameters: TypeParameterMapping,
    check_nullability: bool,
) -> bool:
    """Bind a type parameter to a concrete type or verify consistency.

    If the parameter is already bound, verify that the new type is consistent with the
    previously bound type. Otherwise, bind the parameter to this concrete type.

    Args:
        covered: The concrete type to bind or verify against
        parameter_name: The name of the type parameter (e.g., 'T', 'L')
        parameters: Mapping of parameter names to their resolved types
        check_nullability: Whether to consider nullability when comparing types

    Returns:
        True if the parameter is successfully bound or verified, False if types are inconsistent
    """
    if parameter_name in parameters:
        bound_type = parameters[parameter_name]
        return types_equal(bound_type, covered, check_nullability)
    else:
        parameters[parameter_name] = covered
        return True


def _nullability_matches(
    check_nullability: bool, parameterized_type, covered: Type, kind: str
) -> bool:
    """Check if nullability constraints are satisfied.

    When check_nullability is False, any nullability is acceptable.

    When check_nullability is True, the nullability declared in the ANTLR parameterized type
    (via the ``isnull`` token) must match the nullability of the covered type's protobuf enum.

    Args:
        check_nullability: If False, return True immediately (no constraint checking)
        parameterized_type: ANTLR context that may have an ``isnull`` token attribute
        covered: The protobuf Type message to check
        kind: The field name on the covered type (e.g., 'varchar', 'list')

    Returns:
        True if nullability constraints are satisfied, False otherwise
    """
    if not check_nullability:
        return True

    # The ANTLR context stores a Token called ``isnull`` – it is
    # present when the type is declared as nullable.
    parameterized_nullability = (
        Type.Nullability.NULLABILITY_NULLABLE
        if getattr(parameterized_type, "isnull", None) is not None
        else Type.Nullability.NULLABILITY_REQUIRED
    )

    # The protobuf message stores its own enum – we compare the two.
    covered_nullability = getattr(
        getattr(covered, kind),  # e.g. covered.varchar
        "nullability",
        None,
    )

    return parameterized_nullability == covered_nullability


def check_integer_type_parameters(covered, parameterized_type, attributes, parameters):
    for attr in attributes:
        if not hasattr(covered, attr) and not hasattr(parameterized_type, attr):
            return True
        covered_attr = getattr(covered, attr)
        param_attr = getattr(parameterized_type, attr)
        if not _check_integer_constraint(covered_attr, param_attr, parameters):
            return False
    return True


def _handle_parameterized_type(
    parameterized_type: SubstraitTypeParser.ParameterizedTypeContext,
    covered: Type,
    parameters: dict,
    check_nullability=False,
):
    kind = covered.WhichOneof("kind")

    if not _nullability_matches(check_nullability, parameterized_type, covered, kind):
        return False

    if isinstance(parameterized_type, SubstraitTypeParser.VarCharContext):
        return kind == "varchar" and check_integer_type_parameters(
            covered.varchar, parameterized_type, ["length"], parameters
        )

    if isinstance(parameterized_type, SubstraitTypeParser.FixedCharContext):
        return kind == "fixed_char" and check_integer_type_parameters(
            covered.fixed_char, parameterized_type, ["length"], parameters
        )

    if isinstance(parameterized_type, SubstraitTypeParser.FixedBinaryContext):
        return kind == "fixed_binary" and check_integer_type_parameters(
            covered.fixed_binary, parameterized_type, ["length"], parameters
        )

    if isinstance(parameterized_type, SubstraitTypeParser.DecimalContext):
        return kind == "decimal" and check_integer_type_parameters(
            covered.decimal, parameterized_type, ["scale", "precision"], parameters
        )

    if isinstance(parameterized_type, SubstraitTypeParser.PrecisionTimeContext):
        return kind == "precision_time" and check_integer_type_parameters(
            covered.precision_time,
            parameterized_type,
            ["precision"],
            parameters,
        )

    if isinstance(parameterized_type, SubstraitTypeParser.PrecisionTimestampContext):
        return kind == "precision_timestamp" and check_integer_type_parameters(
            covered.precision_timestamp,
            parameterized_type,
            ["precision"],
            parameters,
        )

    if isinstance(parameterized_type, SubstraitTypeParser.PrecisionTimestampTZContext):
        return kind == "precision_timestamp_tz" and check_integer_type_parameters(
            covered.precision_timestamp_tz,
            parameterized_type,
            ["precision"],
            parameters,
        )

    if isinstance(parameterized_type, SubstraitTypeParser.PrecisionIntervalDayContext):
        return kind == "interval_day" and check_integer_type_parameters(
            covered.interval_day,
            parameterized_type,
            ["precision"],
            parameters,
        )

    if isinstance(parameterized_type, SubstraitTypeParser.ListContext):
        return kind == "list" and covers(
            covered.list.type,
            parameterized_type.expr(),
            parameters,
            check_nullability,
        )

    if isinstance(parameterized_type, SubstraitTypeParser.MapContext):
        return (
            kind == "map"
            and covers(
                covered.map.key, parameterized_type.key, parameters, check_nullability
            )
            and covers(
                covered.map.value,
                parameterized_type.value,
                parameters,
                check_nullability,
            )
        )

    if isinstance(parameterized_type, SubstraitTypeParser.StructContext):
        if kind != "struct":
            return False
        covered_types = covered.struct.types
        param_types = parameterized_type.expr() or []
        if not isinstance(param_types, list):
            param_types = [param_types]
        if len(covered_types) != len(param_types):
            return False
        for covered_field, param_field_ctx in zip(covered_types, param_types):
            if not covers(
                covered_field,
                param_field_ctx,
                parameters,
                check_nullability,  # type: ignore
            ):
                return False
        return True

    raise UnhandledParameterizedTypeError(f"Unhandled type {type(parameterized_type)}")


def covers(
    covered: Type,
    covering: SubstraitTypeParser.TypeLiteralContext,
    parameters: TypeParameterMapping,
    check_nullability: bool = False,
) -> bool:
    """Check if a concrete type is covered by a parameterized type signature.

    A type is "covered" if it satisfies the constraints specified in the parameterized type
    and is consistent with any type parameters encountered.

    Args:
        covered: The concrete type being checked
        covering: The parameterized type signature to check against
        parameters: Mapping of type parameter names to their bound types
        check_nullability: If True, nullability must match exactly. If False, nullability is ignored.

    Returns:
        True if the covered type satisfies the covering type's constraints, False otherwise
    """
    # Handle parameter names
    if isinstance(covering, SubstraitTypeParser.ParameterNameContext):
        parameter_name = str(covering.Identifier())
        return _bind_type_parameter(
            covered, parameter_name, parameters, check_nullability
        )

    covering_typedef: SubstraitTypeParser.TypeDefContext = covering.typeDef()  # type:ignore

    # Handle any types
    any_type: SubstraitTypeParser.AnyTypeContext = covering_typedef.anyType()  # type:ignore
    if any_type:
        if any_type.AnyVar():
            return _bind_type_parameter(
                covered,
                any_type.AnyVar().symbol.text,
                parameters,
                check_nullability,  # type:ignore
            )
        else:
            return True

    # Handle scalar types
    scalar_type = covering_typedef.scalarType()
    if scalar_type:
        covering_resolved = _evaluate(covering_typedef, {})
        return types_equal(covering_resolved, covered, check_nullability)

    # Handle parameterized types using singledispatch
    parameterized_type = covering_typedef.parameterizedType()
    if parameterized_type:
        return _handle_parameterized_type(
            parameterized_type, covered, parameters, check_nullability
        )

    return False
