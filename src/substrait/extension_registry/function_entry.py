"""Function entry class for extension registry."""

from enum import Enum
from typing import Optional, Union

from substrait.type_pb2 import Type
from substrait_extensions.extensions import simple_extensions as se

from substrait.derivation_expression import _parse, evaluate

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
        function_type: FunctionType = FunctionType.SCALAR,
    ) -> None:
        self.name = name
        self.impl = impl
        self.normalized_inputs: list = []
        self.urn: str = urn
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

    def satisfies_signature(self, signature: tuple | list) -> Optional[Type]:
        """Match ``signature`` against this overload, returning its output type.

        ``signature`` interleaves value-operand ``Type``\\ s with enumeration
        selections as plain string tokens, in declared argument order (an enum
        argument's token must be a member of the overload's option domain).
        Returns the derived output ``Type`` on a match, or ``None`` otherwise.
        """
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
            if isinstance(x, list) != isinstance(y, str):
                # An enumeration slot (domain list) accepts only a selection token,
                # and a value slot only a Type -- reject either kind in the other.
                return None
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
        try:
            output_type = evaluate(self.impl.return_, parameters)
        except Exception:
            return None  # return type cannot be derived for these arguments
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
