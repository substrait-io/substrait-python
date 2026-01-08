"""Function entry class for extension registry."""

from enum import Enum
from typing import Optional, Union

from substrait.derivation_expression import _parse, evaluate
from substrait.gen.json import simple_extensions as se
from substrait.gen.proto.type_pb2 import Type

from .signature_checker_helpers import covers, normalize_substrait_type_names


class FunctionType(Enum):
    SCALAR = "scalar"
    AGGREGATE = "aggregate"
    WINDOW = "window"


class FunctionEntry:
    def __init__(
        self,
        urn: str,
        name: str,
        impl: Union[se.Impl, se.Impl1, se.Impl2],
        anchor: int,
        function_type: FunctionType = FunctionType.SCALAR,
    ) -> None:
        self.name = name
        self.impl = impl
        self.normalized_inputs: list = []
        self.urn: str = urn
        self.anchor = anchor
        self.function_type = function_type
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

    def satisfies_signature(self, signature: tuple | list) -> Optional[str]:
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
        if self.nullability == se.NullabilityHandling.MIRROR and isinstance(
            output_type, Type
        ):
            sig_contains_nullable = any(
                [
                    p.__getattribute__(p.WhichOneof("kind")).nullability
                    == Type.NULLABILITY_NULLABLE
                    for p in signature
                    if isinstance(p, Type)
                ]
            )
            kind = output_type.WhichOneof("kind")
            if kind is not None:
                output_type.__getattribute__(kind).nullability = (
                    Type.NULLABILITY_NULLABLE
                    if sig_contains_nullable
                    else Type.NULLABILITY_REQUIRED
                )
        return output_type
