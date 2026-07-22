"""
Utility and debugging functions for Substrait.
"""

from typing import Iterable

import substrait.extensions.extensions_pb2 as ste
import substrait.type_pb2 as stp


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
                ext_func = declaration.extension_function

                ident = (
                    ext_func.extension_urn_reference,
                    ext_func.name,
                )
                if ident not in seen_extension_functions:
                    seen_extension_functions.add(ident)
                    ret.append(declaration)
            else:
                # TODO handle extension type / type-variation declarations.
                mapping_type = declaration.WhichOneof("mapping_type")
                raise NotImplementedError(
                    f"cannot merge extension declaration of type {mapping_type!r}; "
                    f"only 'extension_function' declarations are supported so far"
                )

    return ret


def merge_extensions_into(target, *sources):
    """Merge the extension URNs and declarations of ``sources`` into ``target`` in place.

    Appends any extension URNs / declarations carried by ``sources`` whose identity
    is not already present on ``target``, deduplicating with the same keys as
    :func:`merge_extension_urns` / :func:`merge_extension_declarations` (URN string,
    resp. ``(extension URN reference, name)``). This is the identity used by
    ``builders.plan._merge_extensions``, so the DataFrame/Expr layer and the plan
    builders agree on when extensions collapse.

    ``target`` and each ``source`` are messages carrying repeated ``extension_urns``
    and ``extensions`` fields (a ``Plan`` or an ``ExtendedExpression``). Unlike the
    functions above, this mutates ``target`` rather than returning a new list, for
    callers that have already materialized the message they are accumulating into.
    """
    merged_urns = merge_extension_urns(
        target.extension_urns, *(s.extension_urns for s in sources)
    )
    merged_extensions = merge_extension_declarations(
        target.extensions, *(s.extensions for s in sources)
    )
    target.ClearField("extension_urns")
    target.extension_urns.extend(merged_urns)
    target.ClearField("extensions")
    target.extensions.extend(merged_extensions)
