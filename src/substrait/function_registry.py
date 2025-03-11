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

_normalized_key_names = {
    "binary": "vbin",
    "interval_compound": "icompound",
    "interval_day": "iday",
    "interval_year": "iyear",
    "string": "str",
    "timestamp": "ts",
    "timestamp_tz": "tstz",
}


def normalize_substrait_type_names(typ: str) -> str:
    # First strip off any punctuation
    typ = typ.strip("?").lower()

    # Common prefixes whose information does not matter to an extension function
    # signature
    for complex_type, abbr in [
        ("fixedchar", "fchar"),
        ("varchar", "vchar"),
        ("fixedbinary", "fbin"),
        ("decimal", "dec"),
        ("precision_timestamp", "pts"),
        ("precision_timestamp_tz", "ptstz"),
        ("struct", "struct"),
        ("list", "list"),
        ("map", "map"),
        ("any", "any"),
        ("boolean", "bool"),
    ]:
        if typ.lower().startswith(complex_type):
            typ = abbr

    # Then pass through the dictionary of mappings, defaulting to just the
    # existing string
    typ = _normalized_key_names.get(typ.lower(), typ.lower())
    return typ


def to_integer_option(txt: str):
    if txt.isnumeric():
        return ParameterizedType.IntegerOption(literal=int(txt))
    else:
        return ParameterizedType.IntegerOption(
            parameter=ParameterizedType.IntegerParameter(name=txt)
        )


def to_parameterized_type(dtype: str):
    if dtype == "boolean":
        return ParameterizedType(bool=Type.Boolean())
    elif dtype == "i8":
        return ParameterizedType(i8=Type.I8())
    elif dtype == "i16":
        return ParameterizedType(i16=Type.I16())
    elif dtype == "i32":
        return ParameterizedType(i32=Type.I32())
    elif dtype == "i64":
        return ParameterizedType(i64=Type.I64())
    elif dtype == "fp32":
        return ParameterizedType(fp32=Type.FP32())
    elif dtype == "fp64":
        return ParameterizedType(fp64=Type.FP64())
    elif dtype == "timestamp":
        return ParameterizedType(timestamp=Type.Timestamp())
    elif dtype == "timestamp_tz":
        return ParameterizedType(timestamp_tz=Type.TimestampTZ())
    elif dtype == "date":
        return ParameterizedType(date=Type.Date())
    elif dtype == "time":
        return ParameterizedType(time=Type.Time())
    elif dtype == "interval_year":
        return ParameterizedType(interval_year=Type.IntervalYear())
    elif dtype.startswith("decimal") or dtype.startswith("DECIMAL"):
        (_, precision, scale, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            decimal=ParameterizedType.ParameterizedDecimal(
                scale=to_integer_option(scale), precision=to_integer_option(precision)
            )
        )
    elif dtype.startswith("varchar"):
        (_, length, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            varchar=ParameterizedType.ParameterizedVarChar(
                length=to_integer_option(length)
            )
        )
    elif dtype.startswith("precision_timestamp"):
        (_, precision, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            precision_timestamp=ParameterizedType.ParameterizedPrecisionTimestamp(
                precision=to_integer_option(precision)
            )
        )
    elif dtype.startswith("precision_timestamp_tz"):
        (_, precision, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            precision_timestamp_tz=ParameterizedType.ParameterizedPrecisionTimestampTZ(
                precision=to_integer_option(precision)
            )
        )
    elif dtype.startswith("fixedchar"):
        (_, length, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            fixed_char=ParameterizedType.ParameterizedFixedChar(
                length=to_integer_option(length)
            )
        )
    elif dtype == "string":
        return ParameterizedType(string=Type.String())
    elif dtype.startswith("list"):
        inner_dtype = dtype[5:-1]
        return ParameterizedType(
            list=ParameterizedType.ParameterizedList(
                type=to_parameterized_type(inner_dtype)
            )
        )
    elif dtype.startswith("interval_day"):
        (_, precision, _) = re.split(r"\W+", dtype)

        return ParameterizedType(
            interval_day=ParameterizedType.ParameterizedIntervalDay(
                precision=to_integer_option(precision)
            )
        )
    elif dtype.startswith("any"):
        return ParameterizedType(
            type_parameter=ParameterizedType.TypeParameter(name=dtype)
        )
    elif dtype.startswith("u!") or dtype == "geometry":
        return ParameterizedType(
            user_defined=ParameterizedType.ParameterizedUserDefined()
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


def covers(dtype: Type, parameterized_type: ParameterizedType, parameters: dict):
    expected_kind = parameterized_type.WhichOneof("kind")

    if expected_kind == "type_parameter":
        parameter_name = parameterized_type.type_parameter.name
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

    kind = dtype.WhichOneof("kind")

    if kind != expected_kind:
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
    def __init__(self, uri: str, name: str, impl: Mapping[str, Any], anchor: int) -> None:
        self.name = name
        self.normalized_inputs: list = []
        self.uri: str = uri
        self.anchor = anchor
        self.arguments = []
        self.rtn = impl["return"]
        self.nullability = impl.get("nullability", False)
        self.variadic = impl.get("variadic", False)
        if input_args := impl.get("args", []):
            for val in input_args:
                if typ := val.get("value"):
                    self.arguments.append(to_parameterized_type(typ.strip("?")))
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
                if not covers(y, x, parameters):
                    return None

        return evaluate(self.rtn, parameters)


class FunctionRegistry:
    def __init__(self) -> None:
        self._function_mapping: dict = defaultdict(dict)
        self.id_generator = itertools.count(1)

        self.uri_aliases = {}

        for fpath in importlib_files("substrait.extensions").glob(  # type: ignore
            "functions*.yaml"
        ):
            uri = f"https://github.com/substrait-io/substrait/blob/main/extensions/{fpath.name}"
            self.uri_aliases[fpath.name] = uri
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
                    func = FunctionEntry(uri, function["name"], impl, next(self.id_generator))
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
        uri = self.uri_aliases.get(uri, uri)

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
