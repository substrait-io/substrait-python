from substrait.gen.proto.parameterized_types_pb2 import ParameterizedType
from substrait.gen.proto.type_pb2 import Type
from importlib.resources import files as importlib_files
import itertools
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional, Union
from .derivation_expression import evaluate

import yaml
import re


DEFAULT_URI_PREFIX = "https://github.com/substrait-io/substrait/blob/main/extensions"


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
    else:
        return _normalized_key_names[typ]


def to_integer_option(txt: str):
    if txt.isnumeric():
        return ParameterizedType.IntegerOption(literal=int(txt))
    else:
        return ParameterizedType.IntegerOption(
            parameter=ParameterizedType.IntegerParameter(name=txt)
        )


# TODO try using antlr grammar here as well
def to_parameterized_type(dtype: str):
    if "?" in dtype:
        dtype = dtype.replace("?", "")
        nullability = Type.NULLABILITY_NULLABLE
    else:
        nullability = Type.NULLABILITY_REQUIRED

    if dtype == "boolean":
        return ParameterizedType(bool=Type.Boolean(nullability=nullability))
    elif dtype == "i8":
        return ParameterizedType(i8=Type.I8(nullability=nullability))
    elif dtype == "i16":
        return ParameterizedType(i16=Type.I16(nullability=nullability))
    elif dtype == "i32":
        return ParameterizedType(i32=Type.I32(nullability=nullability))
    elif dtype == "i64":
        return ParameterizedType(i64=Type.I64(nullability=nullability))
    elif dtype == "fp32":
        return ParameterizedType(fp32=Type.FP32(nullability=nullability))
    elif dtype == "fp64":
        return ParameterizedType(fp64=Type.FP64(nullability=nullability))
    elif dtype == "timestamp":
        return ParameterizedType(timestamp=Type.Timestamp(nullability=nullability))
    elif dtype == "timestamp_tz":
        return ParameterizedType(timestamp_tz=Type.TimestampTZ(nullability=nullability))
    elif dtype == "date":
        return ParameterizedType(date=Type.Date(nullability=nullability))
    elif dtype == "time":
        return ParameterizedType(time=Type.Time(nullability=nullability))
    elif dtype == "interval_year":
        return ParameterizedType(
            interval_year=Type.IntervalYear(nullability=nullability)
        )
    elif dtype.startswith("decimal") or dtype.startswith("DECIMAL"):
        (_, precision, scale, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            decimal=ParameterizedType.ParameterizedDecimal(
                scale=to_integer_option(scale),
                precision=to_integer_option(precision),
                nullability=nullability,
            )
        )
    elif dtype.startswith("varchar"):
        (_, length, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            varchar=ParameterizedType.ParameterizedVarChar(
                length=to_integer_option(length), nullability=nullability
            )
        )
    elif dtype.startswith("precision_timestamp"):
        (_, precision, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            precision_timestamp=ParameterizedType.ParameterizedPrecisionTimestamp(
                precision=to_integer_option(precision), nullability=nullability
            )
        )
    elif dtype.startswith("precision_timestamp_tz"):
        (_, precision, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            precision_timestamp_tz=ParameterizedType.ParameterizedPrecisionTimestampTZ(
                precision=to_integer_option(precision), nullability=nullability
            )
        )
    elif dtype.startswith("fixedchar"):
        (_, length, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            fixed_char=ParameterizedType.ParameterizedFixedChar(
                length=to_integer_option(length), nullability=nullability
            )
        )
    elif dtype == "string":
        return ParameterizedType(string=Type.String(nullability=nullability))
    elif dtype.startswith("list"):
        inner_dtype = dtype[5:-1]
        return ParameterizedType(
            list=ParameterizedType.ParameterizedList(
                type=to_parameterized_type(inner_dtype), nullability=nullability
            )
        )
    elif dtype.startswith("interval_day"):
        (_, precision, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            interval_day=ParameterizedType.ParameterizedIntervalDay(
                precision=to_integer_option(precision), nullability=nullability
            )
        )
    elif dtype.startswith("any"):
        return ParameterizedType(
            type_parameter=ParameterizedType.TypeParameter(name=dtype)
        )
    elif dtype.startswith("u!") or dtype == "geometry":
        return ParameterizedType(
            user_defined=ParameterizedType.ParameterizedUserDefined(
                nullability=nullability
            )
        )
    else:
        raise Exception(f"Unknown type - {dtype}")


def violates_integer_option(
    actual: int, option: ParameterizedType.IntegerOption, parameters: dict
):
    integer_type = option.WhichOneof("integer_type")

    if integer_type == "literal" and actual != option.literal:
        return True
    else:
        parameter_name = option.parameter.name
        if parameter_name in parameters and parameters[parameter_name] != actual:
            return True
        else:
            parameters[parameter_name] = actual

    return False


def covers(
    dtype: Type,
    parameterized_type: ParameterizedType,
    parameters: dict,
    check_nullability=False,
):
    expected_kind = parameterized_type.WhichOneof("kind")

    if expected_kind == "type_parameter":
        parameter_name = parameterized_type.type_parameter.name
        # TODO figure out how to do nullability checks with "any" types
        if parameter_name == "any":
            return True
        else:
            if parameter_name in parameters and parameters[
                parameter_name
            ].SerializeToString(deterministic=True) != dtype.SerializeToString(
                deterministic=True
            ):
                return False
            else:
                parameters[parameter_name] = dtype
                return True

    expected_nullability = parameterized_type.__getattribute__(
        parameterized_type.WhichOneof("kind")
    ).nullability

    kind = dtype.WhichOneof("kind")

    if kind != expected_kind:
        return False

    if (
        check_nullability
        and dtype.__getattribute__(dtype.WhichOneof("kind")).nullability
        != expected_nullability
    ):
        return False

    if kind == "decimal":
        if violates_integer_option(
            dtype.decimal.scale, parameterized_type.decimal.scale, parameters
        ) or violates_integer_option(
            dtype.decimal.precision, parameterized_type.decimal.precision, parameters
        ):
            return False

    # TODO handle all types
    return True


class FunctionEntry:
    def __init__(
        self, uri: str, name: str, impl: Mapping[str, Any], anchor: int
    ) -> None:
        self.name = name
        self.normalized_inputs: list = []
        self.uri: str = uri
        self.anchor = anchor
        self.arguments = []
        self.rtn = impl["return"]
        self.nullability = impl.get("nullability", "MIRROR")
        self.variadic = impl.get("variadic", False)
        if input_args := impl.get("args", []):
            for val in input_args:
                if typ := val.get("value"):
                    self.arguments.append(to_parameterized_type(typ))
                    self.normalized_inputs.append(normalize_substrait_type_names(typ))
                elif arg_name := val.get("name", None):
                    self.arguments.append(val.get("options"))
                    self.normalized_inputs.append("req")

    def __repr__(self) -> str:
        return f"{self.name}:{'_'.join(self.normalized_inputs)}"

    def satisfies_signature(self, signature: tuple) -> Optional[str]:
        if self.variadic:
            min_args_allowed = self.variadic.get("min", 0)
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
            if type(y) == str:
                if y not in x:
                    return None
            else:
                if not covers(
                    y, x, parameters, check_nullability=self.nullability == "DISCRETE"
                ):
                    return None

        output_type = evaluate(self.rtn, parameters)
        print(output_type)

        if self.nullability == "MIRROR":
            sig_contains_nullable = any(
                [
                    p.__getattribute__(p.WhichOneof("kind")).nullability
                    == Type.NULLABILITY_NULLABLE
                    for p in signature
                    if type(p) == Type
                ]
            )
            output_type.__getattribute__(output_type.WhichOneof("kind")).nullability = (
                Type.NULLABILITY_NULLABLE
                if sig_contains_nullable
                else Type.NULLABILITY_REQUIRED
            )

        return output_type


class FunctionRegistry:
    def __init__(self, load_default_extensions=True) -> None:
        self._function_mapping: dict = defaultdict(dict)
        self._id_generator = itertools.count(1)

        self._uri_aliases = {}

        if load_default_extensions:
            for fpath in importlib_files("substrait.extensions").glob(  # type: ignore
                "functions*.yaml"
            ):
                uri = f"{DEFAULT_URI_PREFIX}/{fpath.name}"
                self._uri_aliases[fpath.name] = uri
                self.register_extension_yaml(fpath, uri)

    def register_extension_yaml(
        self,
        fname: Union[str, Path],
        uri: str,
    ) -> None:
        fname = Path(fname)
        with open(fname) as f:  # type: ignore
            extension_definitions = yaml.safe_load(f)

        self.register_extension_dict(extension_definitions, uri)

    def register_extension_dict(self, definitions: dict, uri: str) -> None:
        for named_functions in definitions.values():
            for function in named_functions:
                for impl in function.get("impls", []):
                    func = FunctionEntry(
                        uri, function["name"], impl, next(self._id_generator)
                    )
                    if (
                        func.uri in self._function_mapping
                        and function["name"] in self._function_mapping[func.uri]
                    ):
                        self._function_mapping[func.uri][function["name"]].append(func)
                    else:
                        self._function_mapping[func.uri][function["name"]] = [func]

    # TODO add an optional return type check
    def lookup_function(
        self, uri: str, function_name: str, signature: tuple
    ) -> Optional[tuple[FunctionEntry, Type]]:
        uri = self._uri_aliases.get(uri, uri)

        if (
            uri not in self._function_mapping
            or function_name not in self._function_mapping[uri]
        ):
            return None
        functions = self._function_mapping[uri][function_name]
        for f in functions:
            assert isinstance(f, FunctionEntry)
            rtn = f.satisfies_signature(signature)
            if rtn is not None:
                return (f, rtn)

        return None
