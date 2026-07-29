Release Notes
---

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
