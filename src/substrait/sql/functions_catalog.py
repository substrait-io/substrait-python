import pathlib

import yaml

from substrait import proto


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
        self._registered_extensions = {}
        self._functions = {}
        self._functions_return_type = {}
        self._register_builtins()

    def load_standard_extensions(self, dirpath):
        for ext in self.STANDARD_EXTENSIONS:
            self.load(dirpath, ext)

    def load(self, dirpath, filename):
        with open(pathlib.Path(dirpath) / filename.strip("/")) as f:
            sections = yaml.safe_load(f)

        loaded_functions = set()
        functions_return_type = {}
        for functions in sections.values():
            for function in functions:
                function_name = function["name"]
                for impl in function.get("impls", []):
                    # TODO: There seem to be some functions that have arguments without type. What to do?
                    argtypes = [t.get("value", "unknown") for t in impl.get("args", [])]
                    if not argtypes:
                        signature = function_name
                    else:
                        signature = f"{function_name}:{'_'.join(argtypes)}"
                    loaded_functions.add(signature)
                    functions_return_type[signature] = self._type_from_name(
                        impl["return"]
                    )

        self._register_extensions(filename, loaded_functions, functions_return_type)

    def _register_extensions(
        self, extension_uri, loaded_functions, functions_return_type
    ):
        if extension_uri not in self._registered_extensions:
            ext_anchor_id = len(self._registered_extensions) + 1
            self._registered_extensions[extension_uri] = proto.SimpleExtensionURI(
                extension_uri_anchor=ext_anchor_id, uri=extension_uri
            )

        for function in loaded_functions:
            if function in self._functions:
                extensions_by_anchor = self.extension_uris_by_anchor
                existing_function = self._functions[function]
                function_extension = extensions_by_anchor[
                    existing_function.extension_uri_reference
                ].uri
                raise ValueError(
                    f"Duplicate function definition: {existing_function.name} from {extension_uri}, already loaded from {function_extension}"
                )
            extension_anchor = self._registered_extensions[
                extension_uri
            ].extension_uri_anchor
            function_anchor = len(self._functions) + 1
            self._functions[function] = (
                proto.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=extension_anchor,
                    name=function,
                    function_anchor=function_anchor,
                )
            )
            self._functions_return_type[function] = functions_return_type[function]

    def _register_builtins(self):
        self._functions["not:boolean"] = (
            proto.SimpleExtensionDeclaration.ExtensionFunction(
                name="not",
                function_anchor=len(self._functions) + 1,
            )
        )
        self._functions_return_type["not:boolean"] = proto.Type(
            bool=proto.Type.Boolean()
        )

    def _type_from_name(self, typename):
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
            type_descriptor = proto.Type.DESCRIPTOR.fields_by_name[
                typename
            ].message_type
        except KeyError:
            # TODO: improve resolution of complext type like LIST?<any>
            print("Unsupported type", typename)
            return None

        type_class = getattr(proto.Type, type_descriptor.name)
        nullability = (
            proto.Type.Nullability.NULLABILITY_REQUIRED
            if not nullable
            else proto.Type.Nullability.NULLABILITY_NULLABLE
        )
        return proto.Type(**{typename: type_class(nullability=nullability)})

    @property
    def extension_uris_by_anchor(self):
        return {
            ext.extension_uri_anchor: ext
            for ext in self._registered_extensions.values()
        }

    @property
    def extension_uris(self):
        return list(self._registered_extensions.values())

    @property
    def extensions(self):
        return list(self._functions.values())

    def signature(self, function_name, proto_argtypes):
        def _normalize_arg_types(argtypes):
            for argtype in argtypes:
                kind = argtype.WhichOneof("kind")
                if kind == "bool":
                    yield "boolean"
                else:
                    yield kind

        return f"{function_name}:{'_'.join(_normalize_arg_types(proto_argtypes))}"

    def function_anchor(self, function):
        return self._functions[function].function_anchor

    def function_return_type(self, function):
        return self._functions_return_type[function]

    def extensions_for_functions(self, functions):
        uris_anchors = set()
        extensions = []
        for f in functions:
            ext = self._functions[f]
            if not ext.extension_uri_reference:
                # Built-in function
                continue
            uris_anchors.add(ext.extension_uri_reference)
            extensions.append(proto.SimpleExtensionDeclaration(extension_function=ext))

        uris_by_anchor = self.extension_uris_by_anchor
        extension_uris = [uris_by_anchor[uri_anchor] for uri_anchor in uris_anchors]
        return extension_uris, extensions
