"""
Utility and debugging functions for Substrait.
"""

from typing import Iterable

import substrait.gen.proto.extensions.extensions_pb2 as ste
import substrait.gen.proto.type_pb2 as stp


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


def merge_extension_urns(*extension_urns: Iterable[ste.SimpleExtensionURN]):
    """Merges multiple sets of SimpleExtensionURN objects into a single set.
    The order of extensions is kept intact, while duplicates are discarded.
    Assumes that there are no collisions (different extensions having identical anchors).
    """
    seen_urns = set()
    ret = []

    for urns in extension_urns:
        for urn in urns:
            if urn.urn not in seen_urns:
                seen_urns.add(urn.urn)
                ret.append(urn)

    return ret


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

    During the URI/URN migration, declarations may have either or both references set.
    We deduplicate based on both references and the name without trying to resolve between them.
    """

    seen_extension_functions = set()
    ret = []

    for declarations in extension_declarations:
        for declaration in declarations:
            if declaration.WhichOneof("mapping_type") == "extension_function":
                ext_func = declaration.extension_function

                # Use both URI and URN references as-is in the identifier
                # Don't try to resolve or pick between them - just treat them as distinct types
                ident = (
                    ext_func.extension_urn_reference,
                    ext_func.extension_uri_reference,
                    ext_func.name,
                )
                if ident not in seen_extension_functions:
                    seen_extension_functions.add(ident)
                    ret.append(declaration)
            else:
                raise Exception("")  # TODO handle extension types

    return ret
