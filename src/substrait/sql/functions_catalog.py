import os
import pathlib
from collections.abc import Iterable

import yaml

from substrait.gen.proto.type_pb2 import Type as SubstraitType
from substrait.gen.proto.extensions.extensions_pb2 import (
    SimpleExtensionURI,
    SimpleExtensionDeclaration,
)


class RegisteredSubstraitFunction:
    """A Substrait function loaded from an extension file.

    The FunctionsCatalog will keep a collection of RegisteredSubstraitFunction
    and will use them to generate the necessary extension URIs and extensions.
    """

    def __init__(self, signature: str, function_anchor: int | None, impl: dict):
        self.signature = signature
        self.function_anchor = function_anchor
        self.variadic = impl.get("variadic", False)

        if "return" in impl:
            self.return_type = self._type_from_name(impl["return"])
        else:
            # We do always need a return type
            # to know which type to propagate up to the invoker
            _, argtypes = FunctionsCatalog.parse_signature(signature)
            # TODO: Is this the right way to handle this?
            self.return_type = self._type_from_name(argtypes[0])

    @property
    def name(self) -> str:
        name, _ = FunctionsCatalog.parse_signature(self.signature)
        return name

    @property
    def arguments(self) -> list[str]:
        _, argtypes = FunctionsCatalog.parse_signature(self.signature)
        return argtypes

    @property
    def arguments_type(self) -> list[SubstraitType | None]:
        return [self._type_from_name(arg) for arg in self.arguments]

    def _type_from_name(self, typename: str) -> SubstraitType | None:
        # TODO: improve support complext type like LIST?<any>
        typename, *_ = typename.split("<", 1)
        typename = typename.lower()

        nullable = False
        if typename.endswith("?"):
            nullable = True

        typename = typename.strip("?")
        if typename in ("any", "any1"):
            return None

        if typename == "boolean":
            # For some reason boolean is an exception to the naming convention
            typename = "bool"

        try:
            type_descriptor = SubstraitType.DESCRIPTOR.fields_by_name[
                typename
            ].message_type
        except KeyError:
            # TODO: improve resolution of complext type like LIST?<any>
            print("Unsupported type", typename)
            return None

        type_class = getattr(SubstraitType, type_descriptor.name)
        nullability = (
            SubstraitType.Nullability.NULLABILITY_REQUIRED
            if not nullable
            else SubstraitType.Nullability.NULLABILITY_NULLABLE
        )
        return SubstraitType(**{typename: type_class(nullability=nullability)})


class FunctionsCatalog:
    """Catalog of Substrait functions and extensions.

    Loads extensions from YAML files and records the declared functions.
    Given a set of functions it can generate the necessary extension URIs
    and extensions to be included in an ExtendedExpression or Plan.
    """

    # TODO: Find a way to support standard extensions in released distribution.
    # IE: Include the standard extension yaml files in the package data and
    # update them when gen_proto is used..
    STANDARD_EXTENSIONS = (
        "/functions_aggregate_approx.yaml",
        "/functions_aggregate_generic.yaml",
        "/functions_arithmetic.yaml",
        "/functions_arithmetic_decimal.yaml",
        "/functions_boolean.yaml",
        "/functions_comparison.yaml",
        # "/functions_datetime.yaml", for now skip, it has duplicated functions
        "/functions_geometry.yaml",
        "/functions_logarithmic.yaml",
        "/functions_rounding.yaml",
        "/functions_set.yaml",
        "/functions_string.yaml",
    )

    def __init__(self):
        self._substrait_extension_uris = {}
        self._substrait_extension_functions = {}
        self._functions = {}

    def load_standard_extensions(self, dirpath: str | os.PathLike):
        """Load all standard substrait extensions from the target directory."""
        for ext in self.STANDARD_EXTENSIONS:
            self.load(dirpath, ext)

    def load(self, dirpath: str | os.PathLike, filename: str):
        """Load an extension from a YAML file in a target directory."""
        with open(pathlib.Path(dirpath) / filename.strip("/")) as f:
            sections = yaml.safe_load(f)

        loaded_functions = {}
        for functions in sections.values():
            for function in functions:
                function_name = function["name"]
                for impl in function.get("impls", []):
                    # TODO: There seem to be some functions that have arguments without type. What to do?
                    # TODO: improve support complext type like LIST?<any>
                    argtypes = [
                        t.get("value", "unknown").strip("?")
                        for t in impl.get("args", [])
                    ]
                    if not argtypes:
                        signature = function_name
                    else:
                        signature = f"{function_name}:{'_'.join(argtypes)}"
                    loaded_functions[signature] = RegisteredSubstraitFunction(
                        signature, None, impl
                    )

        self._register_extensions(filename, loaded_functions)

    def _register_extensions(
        self,
        extension_uri: str,
        loaded_functions: dict[str, RegisteredSubstraitFunction],
    ):
        if extension_uri not in self._substrait_extension_uris:
            ext_anchor_id = len(self._substrait_extension_uris) + 1
            self._substrait_extension_uris[extension_uri] = SimpleExtensionURI(
                extension_uri_anchor=ext_anchor_id, uri=extension_uri
            )

        for signature, registered_function in loaded_functions.items():
            if signature in self._substrait_extension_functions:
                extensions_by_anchor = self.extension_uris_by_anchor
                existing_function = self._substrait_extension_functions[signature]
                function_extension = extensions_by_anchor[
                    existing_function.extension_uri_reference
                ].uri
                raise ValueError(
                    f"Duplicate function definition: {existing_function.name} from {extension_uri}, already loaded from {function_extension}"
                )
            extension_anchor = self._substrait_extension_uris[
                extension_uri
            ].extension_uri_anchor
            function_anchor = len(self._substrait_extension_functions) + 1
            self._substrait_extension_functions[signature] = (
                SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=extension_anchor,
                    name=signature,
                    function_anchor=function_anchor,
                )
            )
            registered_function.function_anchor = function_anchor
            self._functions.setdefault(registered_function.name, []).append(
                registered_function
            )

    @property
    def extension_uris_by_anchor(self) -> dict[int, SimpleExtensionURI]:
        return {
            ext.extension_uri_anchor: ext
            for ext in self._substrait_extension_uris.values()
        }

    @property
    def extension_uris(self) -> list[SimpleExtensionURI]:
        return list(self._substrait_extension_uris.values())

    @property
    def extensions_functions(
        self,
    ) -> list[SimpleExtensionDeclaration.ExtensionFunction]:
        return list(self._substrait_extension_functions.values())

    @classmethod
    def make_signature(
        cls, function_name: str, proto_argtypes: Iterable[SubstraitType]
    ):
        """Create a function signature from a function name and substrait types.

        The signature is generated according to Function Signature Compound Names
        as described in the Substrait documentation.
        """

        def _normalize_arg_types(argtypes):
            for argtype in argtypes:
                kind = argtype.WhichOneof("kind")
                if kind == "bool":
                    yield "boolean"
                else:
                    yield kind

        return f"{function_name}:{'_'.join(_normalize_arg_types(proto_argtypes))}"

    @classmethod
    def parse_signature(cls, signature: str) -> tuple[str, list[str]]:
        """Parse a function signature and returns name and type names"""
        try:
            function_name, signature_args = signature.split(":")
        except ValueError:
            function_name = signature
            argtypes = []
        else:
            argtypes = signature_args.split("_")
        return function_name, argtypes

    def extensions_for_functions(
        self, function_signatures: Iterable[str]
    ) -> tuple[list[SimpleExtensionURI], list[SimpleExtensionDeclaration]]:
        """Given a set of function signatures, return the necessary extensions.

        The function will return the URIs of the extensions and the extension
        that have to be declared in the plan to use the functions.
        """
        uris_anchors = set()
        extensions = []
        for f in function_signatures:
            ext = self._substrait_extension_functions[f]
            uris_anchors.add(ext.extension_uri_reference)
            extensions.append(SimpleExtensionDeclaration(extension_function=ext))

        uris_by_anchor = self.extension_uris_by_anchor
        extension_uris = [uris_by_anchor[uri_anchor] for uri_anchor in uris_anchors]
        return extension_uris, extensions

    def lookup_function(self, signature: str) -> RegisteredSubstraitFunction | None:
        """Given the signature of a function invocation, return the matching function."""
        function_name, invocation_argtypes = self.parse_signature(signature)

        functions = self._functions.get(function_name)
        if not functions:
            # No function with such a name at all.
            return None

        is_variadic = functions[0].variadic
        if is_variadic:
            # If it's variadic we care about only the first parameter.
            invocation_argtypes = invocation_argtypes[:1]

        found_function = None
        for function in functions:
            accepted_function_arguments = function.arguments
            for argidx, argtype in enumerate(invocation_argtypes):
                try:
                    accepted_argument = accepted_function_arguments[argidx]
                except IndexError:
                    # More arguments than available were provided
                    break
                if accepted_argument != argtype and accepted_argument not in (
                    "any",
                    "any1",
                ):
                    break
            else:
                if argidx < len(accepted_function_arguments) - 1:
                    # Not enough arguments were provided
                    remainder = accepted_function_arguments[argidx + 1 :]
                    if all(arg.endswith("?") for arg in remainder):
                        # All remaining arguments are optional
                        found_function = function
                else:
                    found_function = function

        return found_function
