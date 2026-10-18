Release Notes
---

## [0.37.0](https://github.com/substrait-io/substrait-python/compare/v0.36.0...v0.37.0) (2026-10-18)

### ⚠ BREAKING CHANGES

* following spec v0.105.0, `avg` over a decimal derives a
nullable `DECIMAL?<38,S>` result. Following spec v0.106.0, the `date`
and `precision_time` `round_calendar` overloads no longer take a
trailing origin argument; plans must use the signatures without it.
* `project`, `select` and `aggregate` grouping
expressions now raise `ValueError` for an expression with two or more
output names that do not match its output type, nested fields included,
and for an expression with no output names; previously only the first
name was kept. `column()` raises when an alias list has two or more
names but not exactly one per field, and a single alias on a struct
column now keeps its nested names (`column("s", alias="z")` gives `["z",
"x", "y"]` instead of `["z"]`). Rename a column with a single alias, or
pass a list that names every field in depth-first order.
* **deps:** return type derivation expressions now bind `!` tighter
than `AND` and `OR` and group chained `? :` conditionals to the right,
following spec v0.104.0. User-defined extension YAMLs that relied on the
previous grouping derive different return types.

### Features

* read and write detached expression subtrees ([#317](https://github.com/substrait-io/substrait-python/issues/317)) ([c946391](https://github.com/substrait-io/substrait-python/commit/c946391714ba1353c33d862b290ce63333cc5178))
* read file-level extension descriptions ([#316](https://github.com/substrait-io/substrait-python/issues/316)) ([f850593](https://github.com/substrait-io/substrait-python/commit/f85059303db11eea100ad64a8b69738d0b6f224f))

### Bug Fixes

* carry struct columns' full names through select, project and aggregate ([#313](https://github.com/substrait-io/substrait-python/issues/313)) ([6905dd9](https://github.com/substrait-io/substrait-python/commit/6905dd90e3a0c9eb82ebb8efb45e3994b7c140db))
* **extension_registry:** load default extensions via iterdir() ([#285](https://github.com/substrait-io/substrait-python/issues/285)) ([6dc4111](https://github.com/substrait-io/substrait-python/commit/6dc4111d9920e8e6a205daa18a0dd58d94f58972))
* name the missing column in column-not-found errors and test on Python 3.14 ([#306](https://github.com/substrait-io/substrait-python/issues/306)) ([b60e8b4](https://github.com/substrait-io/substrait-python/commit/b60e8b48295560ae530bacc35234c592addb94fd))
* update ruff to 0.16 and address its lint findings ([#305](https://github.com/substrait-io/substrait-python/issues/305)) ([8277940](https://github.com/substrait-io/substrait-python/commit/82779404124943f0bb257eb7cd65334d9825a32e))

### Miscellaneous Chores

* **deps:** bump substrait packages to 0.104.0 ([#309](https://github.com/substrait-io/substrait-python/issues/309)) ([46d10f6](https://github.com/substrait-io/substrait-python/commit/46d10f623913663eaad3fb58d286628b7ba9523b))

## [0.36.0](https://github.com/substrait-io/substrait-python/compare/v0.35.0...v0.36.0) (2026-10-11)

### ⚠ BREAKING CHANGES

* **type-inference:** Nested struct references now infer the terminal field
type instead of the outer struct. Invalid field paths are rejected.
* **type-inference:** Type inference inside lambda bodies now resolves root
references against the input row and parameter references against the
selected lambda scope. References to a missing enclosing lambda scope
raise an error. Consumers relying on the previous parameter-row
conflation must use the appropriate reference kind and steps_out.
* **type-inference:** Expand and unpivot switching fields now infer a
nullable output when any duplicate is nullable. Consumers that assumed a
required output from the first duplicate must use the combined
nullability.

### Bug Fixes

* **type-inference:** combine Expand switching field nullability ([#289](https://github.com/substrait-io/substrait-python/issues/289)) ([09fb608](https://github.com/substrait-io/substrait-python/commit/09fb60829642924b466780fcb3880317feeb863c))
* **type-inference:** follow nested struct field references ([#294](https://github.com/substrait-io/substrait-python/issues/294)) ([3908dac](https://github.com/substrait-io/substrait-python/commit/3908dac735dc03a137dca13131bf13b8d0aad3a6))
* **type-inference:** resolve lambda scopes and invocation types ([#292](https://github.com/substrait-io/substrait-python/issues/292)) ([35cab19](https://github.com/substrait-io/substrait-python/commit/35cab19e6a2f6fe8663d813c0fd10b00df600527))

## [0.35.0](https://github.com/substrait-io/substrait-python/compare/v0.34.0...v0.35.0) (2026-10-04)

### ⚠ BREAKING CHANGES

* a grouping key absent from some grouping set is now
inferred nullable, so every schema derived from an aggregate with more
than one grouping set changes; a single grouping set and plain
`group_by` are unchanged. A `MIRROR` function over such a key now
returns a nullable result, and `write_named_table` after a
`rollup`/`cube` declares those columns nullable in
`WriteRel.table_schema`, so a `WRITE_OP_CTAS` consumer emits nullable
columns where it previously emitted `NOT NULL`. A user-registered
`DISCRETE` overload declared over a required argument no longer binds to
such a key and raises `Unknown function`; add an explicit cast. No
standard extension uses `DISCRETE`.
* Left, right, outer and single joins now infer nullable
fields on the null-padded side. A schema that repeated a required
declaration there changes, along with anything derived from it. A
lateral join of a right-oriented type now raises ValueError, and
`to_id_based_outer_references` leaves a correlation into the condition
of any join but an inner one offset-based.

### Bug Fixes

* make a grouping key nullable when a grouping set leaves it out ([#279](https://github.com/substrait-io/substrait-python/issues/279)) ([046a23c](https://github.com/substrait-io/substrait-python/commit/046a23c1b31a4c0d2bf331983d069f4f8ab3d3bd))
* make a join's null-padded side nullable ([#272](https://github.com/substrait-io/substrait-python/issues/272)) ([24fba23](https://github.com/substrait-io/substrait-python/commit/24fba23b170a69e8192fa4865b13b1d9b6e4da7f))

## [0.34.0](https://github.com/substrait-io/substrait-python/compare/v0.33.0...v0.34.0) (2026-09-27)

### ⚠ BREAKING CHANGES

* ReadRel projection masks now change inferred output
schemas and the indices seen by emit and parent relations. Invalid mask
field indices and selector/type mismatches now raise errors instead of
being ignored.

### Bug Fixes

* apply ReadRel projection during schema inference ([#266](https://github.com/substrait-io/substrait-python/issues/266)) ([1cf8842](https://github.com/substrait-io/substrait-python/commit/1cf88427a53fff03fb23d54fa1096c584eaf9e7b))

### Performance Improvements

* infer each relation's schema once per build, not once per level ([#250](https://github.com/substrait-io/substrait-python/issues/250)) ([5425a2f](https://github.com/substrait-io/substrait-python/commit/5425a2fc420bfa648ab411a6a70f427e42f71911))

## [0.33.0](https://github.com/substrait-io/substrait-python/compare/v0.32.0...v0.33.0) (2026-09-20)

### ⚠ BREAKING CHANGES

* Mark joins no longer expose columns from the other
input. Output field indices change, and post-join filters must use only
the selected input and the marker.

### Bug Fixes

* derive mark join output from the selected input ([#265](https://github.com/substrait-io/substrait-python/issues/265)) ([45c8ca7](https://github.com/substrait-io/substrait-python/commit/45c8ca7d14f90b687e54e053751779409def9ee1)), closes [#263](https://github.com/substrait-io/substrait-python/issues/263)

## [0.32.0](https://github.com/substrait-io/substrait-python/compare/v0.31.0...v0.32.0) (2026-09-13)

### Features

* implement enum function arguments ([#259](https://github.com/substrait-io/substrait-python/issues/259)) ([f45be3a](https://github.com/substrait-io/substrait-python/commit/f45be3acb5b493f7508cec818d32661a6f8fa99f)), closes [#258](https://github.com/substrait-io/substrait-python/issues/258)

### Bug Fixes

* reject non-boolean filter/join conditions at build time ([#271](https://github.com/substrait-io/substrait-python/issues/271)) ([e001537](https://github.com/substrait-io/substrait-python/commit/e001537ed200f46cac43a54b5f24461d673ae382)), closes [#270](https://github.com/substrait-io/substrait-python/issues/270)

## [0.31.0](https://github.com/substrait-io/substrait-python/compare/v0.30.0...v0.31.0) (2026-08-16)

### ⚠ BREAKING CHANGES

* emitted extension anchors are numbered per plan, so
plans compared byte-for-byte against output from an earlier release will
differ. Anchors are plan-local by spec, so plan semantics are
unaffected. `ExtensionRegistry.lookup_urn` and `FunctionEntry.anchor`
are removed; use `has_urn()` / `urns()` for URN membership, and
`(entry.urn, str(entry))` as a function's durable identity.
`ExtensionCollector.adopt` raises on an input declaring two different
functions at one anchor, and `aggregate` raises on a measure that is not
an aggregate function; both previously produced a plan with an ambiguous
or dangling function reference.

### Features

* assign extension anchors per plan, not per registry ([#245](https://github.com/substrait-io/substrait-python/issues/245)) ([4834cae](https://github.com/substrait-io/substrait-python/commit/4834cae77acf248330faae6cef2f8de2d8d58156))

## [0.30.0](https://github.com/substrait-io/substrait-python/compare/v0.29.0...v0.30.0) (2026-07-29)

### ⚠ BREAKING CHANGES

* DataFrame-produced plans now encode correlated 
references as `rel_reference` rather than `steps_out` (except a reducing
join's condition scope, which cannot be expressed id-based and stays
`steps_out`). The builders and inference are backward-compatible (both
forms are read; builders still emit `steps_out`).
* make OuterReference.steps_out 1-based per the Substrait spec (#233)
* **deps:** Requires substrait 0.98.0, whose protobuf definitions drop
several long-deprecated fields. Plans or code that read the removed fields will
break:

- FetchRel.offset / FetchRel.count        → offset_expr / count_expr
- ReadRel.VirtualTable.values             → expressions
- HashJoinRel/MergeJoinRel.left_keys/right_keys → keys
- IntervalDayToSecond.microseconds        → subseconds (+ precision)

substrait-python's builders already emit the replacement fields, so no
builder/consumer API change is required. The only user-visible change is the
plan printer's virtual-table output, which now renders `literal: <value>` via
the shared expression renderer instead of the removed field-typed struct
renderer.
* **deps:** An unset `IntervalDay.precision` no longer defaults to
microseconds (6). Producers must set precision explicitly and consumers
should reject an unset precision; picosecond precision (12) is now
allowed. The `interval_day()` builder already requires an explicit
precision, so no API change is needed.

### Features

* add LateralJoinRel support (inference + builders) ([#228](https://github.com/substrait-io/substrait-python/issues/228)) ([68df5fb](https://github.com/substrait-io/substrait-python/commit/68df5fb11d8501fdcf5972e853f085d82fd0cd06))
* add Plan.ExecutionBehavior support ([#224](https://github.com/substrait-io/substrait-python/issues/224)) ([4d183f5](https://github.com/substrait-io/substrait-python/commit/4d183f5934204b395fe910332aa5b0faa413f333))
* **builders:** add ConsistentPartitionWindowRel builder ([#158](https://github.com/substrait-io/substrait-python/issues/158)) ([23d4274](https://github.com/substrait-io/substrait-python/commit/23d4274f6a82eb6f82135b580472216aa4245c19))
* bump substrait packages to 0.86.0 and support additional extension metadata ([#168](https://github.com/substrait-io/substrait-python/issues/168)) ([1e34f42](https://github.com/substrait-io/substrait-python/commit/1e34f421086cb9db44ab4d90274438793be7897b))
* ergonomic native DataFrame/Expr API (substrait.api) ([#204](https://github.com/substrait-io/substrait-python/issues/204)) ([702e045](https://github.com/substrait-io/substrait-python/commit/702e045df0f26c96d3e5c3a4b21848f206b896a9))
* expose residual_expression and post_join_filter on join builders ([#225](https://github.com/substrait-io/substrait-python/issues/225)) ([5814bab](https://github.com/substrait-io/substrait-python/commit/5814bab135825848c2d828720557d49e4560eaad))
* id-based outer-reference resolution (Substrait v0.89.0) ([#239](https://github.com/substrait-io/substrait-python/issues/239)) ([9a0fa08](https://github.com/substrait-io/substrait-python/commit/9a0fa08d72d116a9fcc05e75aa14b54ec03047b6))
* shared subplans (ReferenceRel) / DataFrame.cache() (CTEs) ([#235](https://github.com/substrait-io/substrait-python/issues/235)) ([4436530](https://github.com/substrait-io/substrait-python/commit/44365300cd7a65938e0b0f1b5c8e75ebbdacf374))

### Bug Fixes

* add missing interval_day derivation expression ([#175](https://github.com/substrait-io/substrait-python/issues/175)) ([077859b](https://github.com/substrait-io/substrait-python/commit/077859b3ba4ea429ad14967dbe75abb988ef270d)), closes [#174](https://github.com/substrait-io/substrait-python/issues/174)
* combine set-operation nullability across all inputs ([#221](https://github.com/substrait-io/substrait-python/issues/221)) ([be531c4](https://github.com/substrait-io/substrait-python/commit/be531c4aa7b9a45fe423ff1bb59e034b5ac60d1f)), closes [#206](https://github.com/substrait-io/substrait-python/issues/206) [#220](https://github.com/substrait-io/substrait-python/issues/220)
* **extensions:** expose top-level metadata in YAML extension files ([#170](https://github.com/substrait-io/substrait-python/issues/170)) ([6e6b956](https://github.com/substrait-io/substrait-python/commit/6e6b956299d8bed04e344decc2ac4e08739d765f)), closes [#149](https://github.com/substrait-io/substrait-python/issues/149)
* make OuterReference.steps_out 1-based per the Substrait spec ([#233](https://github.com/substrait-io/substrait-python/issues/233)) ([6632b69](https://github.com/substrait-io/substrait-python/commit/6632b69d97630c966530f478a7144ea6b7bcc606))
* raise clear parse error for invalid derivation expressions ([#222](https://github.com/substrait-io/substrait-python/issues/222)) ([8a0beae](https://github.com/substrait-io/substrait-python/commit/8a0beae24a28b90ad31cccaa6ace8cdf8ccf2011))
* read SetRel.common in set-relation schema inference ([#218](https://github.com/substrait-io/substrait-python/issues/218)) ([0edecbb](https://github.com/substrait-io/substrait-python/commit/0edecbbc91f1a2d45832c59a5b5473415d118657))

### Miscellaneous Chores

* **deps:** bump substrait packages to 0.97.0 ([#230](https://github.com/substrait-io/substrait-python/issues/230)) ([1310537](https://github.com/substrait-io/substrait-python/commit/1310537f9766e004c98d9f17fdca10fde52e5da1))
* **deps:** bump substrait packages to 0.98.0 ([#232](https://github.com/substrait-io/substrait-python/issues/232)) ([6df75cd](https://github.com/substrait-io/substrait-python/commit/6df75cde8d04c60fdeb2b0edb3f2aaa9a69cdf9f))
