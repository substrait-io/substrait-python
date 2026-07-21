# Custom extensions

Substrait is extensible: engines define their own functions, types, and
relations via extensions. This page covers using a custom
[`ExtensionRegistry`](#the-registry) and building [user-defined
relations](#extension-relations).

## The registry

Every `DataFrame` carries an `ExtensionRegistry`. The default
(`sub.default_registry()`) is preloaded with the standard extensions and shared
across frames. To use custom functions, build your own registry and register
extensions on it:

```python
--8<-- "examples/guide/custom_extensions.py:registry_setup"
```

Pass the registry to a [source function](data-sources.md) so the whole chain
uses it:

```python
--8<-- "examples/guide/custom_extensions.py:pass_registry"
```

### Reaching custom functions by name

The global `sub.f` only knows the *default* extensions. For functions from your
registry, build a bound namespace with `functions_for`, or use `df.f` (which is
bound to that frame's registry automatically):

```python
--8<-- "examples/guide/custom_extensions.py:reach_functions"
```

See [The function namespace](functions.md) for more.

## Extension relations

When you need a relation Substrait has no built-in for, implement a **detail**
class describing how to (de)serialize its `google.protobuf.Any` payload and how
to derive its output schema. This mirrors substrait-java's
`LeafRelDetail` / `SingleRelDetail` / `MultiRelDetail`. There are three abstract
base classes, by input arity:

| ABC | Inputs | `derive_schema` receives |
|-----|--------|--------------------------|
| `ExtensionLeafDetail` | 0 | (nothing) |
| `ExtensionSingleDetail` | 1 | the input `Type.Struct` |
| `ExtensionMultiDetail` | N | a list of input `Type.Struct` |

Each requires `to_any()`, `from_any(cls, detail)`, and `derive_schema(...)`, plus
a `type_url` identifying the payload.

```python
--8<-- "examples/guide/custom_extensions.py:detail_class"
```

### Building the relation

Use the frame verbs / entry point matching the arity:

```python
--8<-- "examples/guide/custom_extensions.py:build_relation"
```

`DataFrame.extension` also accepts a raw `google.protobuf.Any` directly, in
which case the input schema is assumed to pass through unchanged.

### Registering for schema inference

substrait-python re-derives schemas from the serialized proto, where the detail
is an opaque `Any`. So inference can follow your relation, register the detail
class — then inference reconstructs it from the plan's `Any` and calls
`derive_schema`:

```python
--8<-- "examples/guide/custom_extensions.py:register_relation"
```

Registration is process-global (type URLs are globally unique), so inference
then works on any plan containing that relation.

## Next

- [Data sources](data-sources.md) — `read_extension_table` and `extension_leaf`.
- [Consuming plans](consuming-plans.md) — serialize and hand off the plan.
