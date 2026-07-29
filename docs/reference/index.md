---
icon: lucide/book-open
---

# API reference

Generated from the docstrings of the `substrait.dataframe` package. For a
task-oriented introduction, start with the [guide](../getting-started.md).

## Entry points & facade

::: substrait.dataframe
    options:
      show_root_heading: false
      members: false

## The DataFrame

::: substrait.dataframe.frame
    options:
      heading_level: 3
      members:
        - DataFrame
        - GroupBy
        - LateralLeft
        - read_named_table
        - from_records
        - read_parquet
        - read_csv
        - read_orc
        - read_arrow
        - read_extension_table
        - extension_leaf
        - create_table
        - create_view
        - drop_table
        - drop_view
        - update_table
        - default_registry

## Expressions

::: substrait.dataframe.expr
    options:
      heading_level: 3
      members:
        - Expr
        - Measure
        - When
        - col
        - lit
        - outer
        - when
        - coalesce
        - parameter
        - current_timestamp
        - current_date
        - current_timezone
        - scalar_subquery
        - exists
        - unique
        - any_
        - all_
        - infer_literal_type

## The function namespace

::: substrait.dataframe.functions
    options:
      heading_level: 3
      members:
        - functions_for

## Data types

::: substrait.dataframe.dtypes
    options:
      heading_level: 3

## Extension relations

::: substrait.dataframe.extension_relations
    options:
      heading_level: 3
