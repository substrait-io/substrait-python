import itertools
import re
from collections import defaultdict
from importlib.resources import files as importlib_files
from pathlib import Path
from typing import Optional, Union

import yaml

from substrait.gen.antlr.SubstraitTypeParser import SubstraitTypeParser
from substrait.gen.json import simple_extensions as se
from substrait.gen.proto.type_pb2 import Type
from substrait.simple_extension_utils import build_simple_extensions

from .bimap import UriUrnBiDiMap
from .derivation_expression import _evaluate, _parse, evaluate

DEFAULT_URN_PREFIX = "https://github.com/substrait-io/substrait/blob/main/extensions"

# Format: extension:<organization>:<name>
# Example: extension:io.substrait:functions_arithmetic
URN_PATTERN = re.compile(r"^extension:[^:]+:[^:]+$")


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
}


def normalize_substrait_type_names(typ: str) -> str:
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
        raise Exception(f"Unrecognized substrait type {typ}")


def violates_integer_option(actual: int, option, parameters: dict):
    option_numeric = None
    if isinstance(option, SubstraitTypeParser.NumericLiteralContext):
        option_numeric = int(str(option.Number()))
    elif isinstance(option, SubstraitTypeParser.NumericParameterNameContext):
        parameter_name = str(option.Identifier())

        if parameter_name not in parameters:
            parameters[parameter_name] = actual
        option_numeric = parameters[parameter_name]
    else:
        raise Exception(
            f"Input should be either NumericLiteralContext or NumericParameterNameContext, got {type(option)} instead"
        )
    return actual != option_numeric


def types_equal(type1: Type, type2: Type, check_nullability=False):
    if check_nullability:
        return type1 == type2
    else:
        x, y = Type(), Type()
        x.CopyFrom(type1)
        y.CopyFrom(type2)
        x.__getattribute__(
            x.WhichOneof("kind")
        ).nullability = Type.Nullability.NULLABILITY_UNSPECIFIED
        y.__getattribute__(
            y.WhichOneof("kind")
        ).nullability = Type.Nullability.NULLABILITY_UNSPECIFIED
        return x == y


def handle_parameter_cover(
    covered: Type, parameter_name: str, parameters: dict, check_nullability: bool
):
    if parameter_name in parameters:
        covering = parameters[parameter_name]
        return types_equal(covering, covered, check_nullability)
    else:
        parameters[parameter_name] = covered
        return True


def _check_nullability(check_nullability, parameterized_type, covered, kind) -> bool:
    if not check_nullability:
        return True
    # The ANTLR context stores a Token called ``isnull`` – it is
    # present when the type is declared as nullable.
    nullability = (
        Type.Nullability.NULLABILITY_NULLABLE
        if getattr(parameterized_type, "isnull", None) is not None
        else Type.Nullability.NULLABILITY_REQUIRED
    )
    # if nullability == Type.Nullability.NULLABILITY_NULLABLE:
    #     return True  # is still true even if the covered is required
    # The protobuf message stores its own enum – we compare the two.
    covered_nullability = getattr(
        getattr(covered, kind),  # e.g. covered.varchar
        "nullability",
        None,
    )
    return nullability == covered_nullability


def covers(
    covered: Type,
    covering: SubstraitTypeParser.TypeLiteralContext,
    parameters: dict,
    check_nullability=False,
):
    if isinstance(covering, SubstraitTypeParser.ParameterNameContext):
        parameter_name = str(covering.Identifier())
        return handle_parameter_cover(
            covered, parameter_name, parameters, check_nullability
        )
    covering: SubstraitTypeParser.TypeDefContext = covering.typeDef()

    any_type: SubstraitTypeParser.AnyTypeContext = covering.anyType()
    if any_type:
        if any_type.AnyVar():
            return handle_parameter_cover(
                covered, any_type.AnyVar().symbol.text, parameters, check_nullability
            )
        else:
            return True

    scalar_type = covering.scalarType()
    if scalar_type:
        covering = _evaluate(covering, {})
        return types_equal(covering, covered, check_nullability)

    parameterized_type = covering.parameterizedType()
    if parameterized_type:
        return _cover_parametrized_type(
            covered, parameterized_type, parameters, check_nullability
        )


def check_violates_integer_option_parameters(
    covered, parameterized_type, attributes, parameters
):
    for attr in attributes:
        if not hasattr(covered, attr) and not hasattr(parameterized_type, attr):
            return False
        covered_attr = getattr(covered, attr)
        param_attr = getattr(parameterized_type, attr)
        if violates_integer_option(covered_attr, param_attr, parameters):
            return True
    return False


def _cover_parametrized_type(
    covered: Type,
    parameterized_type: SubstraitTypeParser.ParameterizedTypeContext,
    parameters: dict,
    check_nullability=False,
):
    kind = covered.WhichOneof("kind")

    if not _check_nullability(check_nullability, parameterized_type, covered, kind):
        return False

    if isinstance(parameterized_type, SubstraitTypeParser.VarCharContext):
        return kind == "varchar" and not check_violates_integer_option_parameters(
            covered.varchar, parameterized_type, ["length"], parameters
        )

    if isinstance(parameterized_type, SubstraitTypeParser.FixedCharContext):
        return kind == "fixed_char" and not check_violates_integer_option_parameters(
            covered.fixed_char, parameterized_type, ["length"], parameters
        )

    if isinstance(parameterized_type, SubstraitTypeParser.FixedBinaryContext):
        return kind == "fixed_binary" and not check_violates_integer_option_parameters(
            covered.fixed_binary, parameterized_type, ["length"], parameters
        )

    if isinstance(parameterized_type, SubstraitTypeParser.DecimalContext):
        return kind == "decimal" and not check_violates_integer_option_parameters(
            covered.decimal, parameterized_type, ["scale", "precision"], parameters
        )

    if isinstance(parameterized_type, SubstraitTypeParser.PrecisionTimestampContext):
        return (
            kind == "precision_timestamp"
            and not check_violates_integer_option_parameters(
                covered.precision_timestamp,
                parameterized_type,
                ["precision"],
                parameters,
            )
        )

    if isinstance(parameterized_type, SubstraitTypeParser.PrecisionTimestampTZContext):
        return (
            kind == "precision_timestamp_tz"
            and not check_violates_integer_option_parameters(
                covered.precision_timestamp_tz,
                parameterized_type,
                ["precision"],
                parameters,
            )
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

    raise Exception(f"Unhandled type {type(parameterized_type)}")


class FunctionEntry:
    def __init__(
        self, urn: str, name: str, impl: Union[se.Impl, se.Impl1, se.Impl2], anchor: int
    ) -> None:
        self.name = name
        self.impl = impl
        self.normalized_inputs: list = []
        self.urn: str = urn
        self.anchor = anchor
        self.arguments = []
        self.nullability = (
            impl.nullability if impl.nullability else se.NullabilityHandling.MIRROR
        )

        if impl.args:
            for arg in impl.args:
                if isinstance(arg, se.ValueArg):
                    self.arguments.append(_parse(arg.value))
                    self.normalized_inputs.append(
                        normalize_substrait_type_names(arg.value)
                    )
                elif isinstance(arg, se.EnumerationArg):
                    self.arguments.append(arg.options)
                    self.normalized_inputs.append("req")

    def __repr__(self) -> str:
        return f"{self.name}:{'_'.join(self.normalized_inputs)}"

    def satisfies_signature(self, signature: tuple) -> Optional[str]:
        if self.impl.variadic:
            min_args_allowed = self.impl.variadic.min or 0
            if len(signature) < min_args_allowed:
                return None
            inputs = [self.arguments[0]] * len(signature)
        else:
            inputs = self.arguments
        if len(inputs) != len(signature):
            return None

        zipped_args = list(zip(inputs, signature))

        parameters = {}

        for x, y in zipped_args:
            if isinstance(y, str):
                if y not in x:
                    return None
            else:
                if not covers(
                    y,
                    x,
                    parameters,
                    check_nullability=self.nullability
                    == se.NullabilityHandling.DISCRETE,
                ):
                    return None

        output_type = evaluate(self.impl.return_, parameters)

        if self.nullability == se.NullabilityHandling.MIRROR:
            sig_contains_nullable = any([
                p.__getattribute__(p.WhichOneof("kind")).nullability
                == Type.NULLABILITY_NULLABLE
                for p in signature
                if isinstance(p, Type)
            ])
            output_type.__getattribute__(output_type.WhichOneof("kind")).nullability = (
                Type.NULLABILITY_NULLABLE
                if sig_contains_nullable
                else Type.NULLABILITY_REQUIRED
            )

        return output_type


class ExtensionRegistry:
    def __init__(self, load_default_extensions=True) -> None:
        self._urn_mapping: dict = defaultdict(dict)  # URN -> anchor ID
        # NOTE: during the URI -> URN migration, we only need an id generator for URN. We can use the same anchor for plan construction for URIs.
        self._urn_id_generator = itertools.count(1)

        self._function_mapping: dict = defaultdict(dict)
        self._id_generator = itertools.count(1)

        # Bidirectional URI <-> URN mapping (temporary during migration)
        self._uri_urn_bimap = UriUrnBiDiMap()

        if load_default_extensions:
            for fpath in importlib_files("substrait.extensions").glob(  # type: ignore
                "functions*.yaml"
            ):
                # Derive URI from DEFAULT_URN_PREFIX and filename
                uri = f"{DEFAULT_URN_PREFIX}/{fpath.name}"
                self.register_extension_yaml(fpath, uri=uri)

    def register_extension_yaml(
        self,
        fname: Union[str, Path],
        uri: str,
    ) -> None:
        """Register extensions from a YAML file.

        Args:
            fname: Path to the YAML file
            uri: URI for the extension (this is required during the URI -> URN migration)
        """
        fname = Path(fname)
        with open(fname) as f:  # type: ignore
            extension_definitions = yaml.safe_load(f)

        self.register_extension_dict(extension_definitions, uri=uri)

    def register_extension_dict(self, definitions: dict, uri: str) -> None:
        """Register extensions from a dictionary (parsed YAML).

        Args:
            definitions: The extension definitions dictionary
            uri: URI for the extension (for URI/URN bimap)
        """
        urn = definitions.get("urn")
        if not urn:
            raise ValueError("Extension definitions must contain a 'urn' field")

        self._validate_urn_format(urn)

        self._urn_mapping[urn] = next(self._urn_id_generator)

        self._uri_urn_bimap.put(uri, urn)

        simple_extensions = build_simple_extensions(definitions)

        functions = (
            (simple_extensions.scalar_functions or [])
            + (simple_extensions.aggregate_functions or [])
            + (simple_extensions.window_functions or [])
        )

        if functions:
            for function in functions:
                for impl in function.impls:
                    func = FunctionEntry(
                        urn, function.name, impl, next(self._id_generator)
                    )
                    if (
                        func.urn in self._function_mapping
                        and function.name in self._function_mapping[func.urn]
                    ):
                        self._function_mapping[func.urn][function.name].append(func)
                    else:
                        self._function_mapping[func.urn][function.name] = [func]

    # TODO add an optional return type check
    def lookup_function(
        self, urn: str, function_name: str, signature: tuple
    ) -> Optional[tuple[FunctionEntry, Type]]:
        if (
            urn not in self._function_mapping
            or function_name not in self._function_mapping[urn]
        ):
            return None
        functions = self._function_mapping[urn][function_name]
        for f in functions:
            assert isinstance(f, FunctionEntry)
            rtn = f.satisfies_signature(signature)
            if rtn is not None:
                return (f, rtn)

        return None

    def lookup_urn(self, urn: str) -> Optional[int]:
        return self._urn_mapping.get(urn, None)

    def lookup_uri_anchor(self, uri: str) -> Optional[int]:
        """Look up the anchor ID for a URI.

        During the migration period, URI and URN share the same anchor.
        This method converts the URI to its URN and returns the URN's anchor.

        Args:
            uri: The extension URI to look up

        Returns:
            The anchor ID for the URI (same as its corresponding URN), or None if not found
        """
        urn = self._uri_urn_bimap.get_urn(uri)
        if urn:
            return self._urn_mapping.get(urn)
        return None

    def _validate_urn_format(self, urn: str) -> None:
        """Validate that a URN follows the expected format.

        Expected format: extension:<organization>:<name>
        Example: extension:io.substrait:functions_arithmetic

        Args:
            urn: The URN to validate

        Raises:
            ValueError: If the URN format is invalid
        """
        if not URN_PATTERN.match(urn):
            raise ValueError(
                f"Invalid URN format: '{urn}'. "
                f"Expected format: extension:<organization>:<name> "
                f"(e.g., 'extension:io.substrait:functions_arithmetic')"
            )
