import substrait.gen.proto.type_pb2 as stp
import substrait.gen.proto.extensions.extensions_pb2 as ste
from typing import Iterable


def type_num_names(typ: stp.Type):
    kind = typ.WhichOneof("kind")
    if kind == "struct":
        lengths = [type_num_names(t) for t in typ.struct.types]
        return sum(lengths) + 1
    elif kind == "list":
        return type_num_names(typ.list.type)
    elif kind == "map":
        return type_num_names(typ.map.key) + type_num_names(typ.map.value)
    else:
        return 1


def merge_extension_uris(*extension_uris: Iterable[ste.SimpleExtensionURI]):
    """Merges multiple sets of SimpleExtensionURI objects into a single set.
    The order of extensions is kept intact, while duplicates are discarded.
    Assumes that there are no collisions (different extensions having identical anchors).
    """
    seen_uris = set()
    ret = []

    for uris in extension_uris:
        for uri in uris:
            if uri.uri not in seen_uris:
                seen_uris.add(uri.uri)
                ret.append(uri)

    return ret


def merge_extension_declarations(
    *extension_declarations: Iterable[ste.SimpleExtensionDeclaration],
):
    """Merges multiple sets of SimpleExtensionDeclaration objects into a single set.
    The order of extension declarations is kept intact, while duplicates are discarded.
    Assumes that there are no collisions (different extension declarations having identical anchors).
    """

    seen_extension_functions = set()
    ret = []

    for declarations in extension_declarations:
        for declaration in declarations:
            if declaration.WhichOneof("mapping_type") == "extension_function":
                ident = (
                    declaration.extension_function.extension_uri_reference,
                    declaration.extension_function.name,
                )
                if ident not in seen_extension_functions:
                    seen_extension_functions.add(ident)
                    ret.append(declaration)
            else:
                raise Exception("")  # TODO handle extension types

    return ret
