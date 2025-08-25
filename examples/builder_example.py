from substrait.builders.plan import (
    read_named_table,
    project,
    filter,
    sort,
    fetch,
)
from substrait.builders.extended_expression import (
    column,
    scalar_function,
    literal,
)
from substrait.builders.type import i64, boolean, struct, named_struct, fp64, string
from substrait.extension_registry import ExtensionRegistry
from substrait.builders.display import pretty_print_plan, pretty_print_expression
import substrait.gen.proto.algebra_pb2 as stalg

registry = ExtensionRegistry(load_default_extensions=True)


def basic_example():
    ns = named_struct(
        names=["id", "is_applicable"],
        struct=struct(types=[i64(nullable=False), boolean()]),
    )

    table = read_named_table("example_table", ns)
    table = filter(table, expression=column("is_applicable"))
    table = filter(
        table,
        expression=scalar_function(
            "functions_comparison.yaml",
            "lt",
            expressions=[column("id"), literal(100, i64())],
        ),
    )
    table = project(table, expressions=[column("id")])

    print(table(registry))
    pretty_print_plan(table(registry), use_colors=True)

    """
  extension_uris {
    extension_uri_anchor: 13
    uri: "functions_comparison.yaml"
  }
  extensions {
    extension_function {
      extension_uri_reference: 13
      function_anchor: 495
      name: "lt"
    }
  }
  relations {
    root {
      input {
        project {
          common {
            emit {
              output_mapping: 2
            }
          }
          input {
            filter {
              input {
                filter {
                  input {
                    read {
                      common {
                        direct {
                        }
                      }
                      base_schema {
                        names: "id"
                        names: "is_applicable"
                        struct {
                          types {
                            i64 {
                              nullability: NULLABILITY_REQUIRED
                            }
                          }
                          types {
                            bool {
                              nullability: NULLABILITY_NULLABLE
                            }
                          }
                          nullability: NULLABILITY_NULLABLE
                        }
                      }
                      named_table {
                        names: "example_table"
                      }
                    }
                  }
                  condition {
                    selection {
                      direct_reference {
                        struct_field {
                          field: 1
                        }
                      }
                      root_reference {
                      }
                    }
                  }
                }
              }
              condition {
                scalar_function {
                  function_reference: 495
                  output_type {
                    bool {
                      nullability: NULLABILITY_NULLABLE
                    }
                  }
                  arguments {
                    value {
                      selection {
                        direct_reference {
                          struct_field {
                          }
                        }
                        root_reference {
                        }
                      }
                    }
                  }
                  arguments {
                    value {
                      literal {
                        i64: 100
                        nullable: true
                      }
                    }
                  }
                }
              }
            }
          }
          expressions {
            selection {
              direct_reference {
                struct_field {
                }
              }
              root_reference {
              }
            }
          }
        }
      }
      names: "id"
    }
  }
  """


def advanced_example():
    print("=== Simple Example ===")
    # Simple example (original)
    ns = named_struct(
        names=["id", "is_applicable"],
        struct=struct(types=[i64(nullable=False), boolean()]),
    )

    table = read_named_table("example_table", ns)
    table = filter(table, expression=column("is_applicable"))
    table = filter(
        table,
        expression=scalar_function(
            "functions_comparison.yaml",
            "lt",
            expressions=[column("id"), literal(100, i64())],
        ),
    )
    table = project(table, expressions=[column("id")])

    print("Simple filtered table:")
    pretty_print_plan(table(registry), use_colors=True)

    print("\n" + "=" * 50 + "\n")

    print("=== Scalar Function with Options Example ===")
    # Example with scalar function that has options
    users_schema = named_struct(
        names=["user_id", "name", "age", "salary"],
        struct=struct(
            types=[
                i64(nullable=False),  # user_id
                string(nullable=False),  # name
                i64(nullable=False),  # age
                fp64(nullable=False),  # salary
            ]
        ),
    )

    users = read_named_table("users", users_schema)

    # Filter users with age > 25
    adult_users = filter(
        users,
        expression=scalar_function(
            "functions_comparison.yaml",
            "gt",
            expressions=[column("age"), literal(25, i64())],
        ),
    )

    # Project with calculated fields
    enriched_users = project(
        adult_users,
        expressions=[
            column("user_id"),
            column("name"),
            column("age"),
            column("salary"),
            # Add a calculated field (this would show function options if available)
            scalar_function(
                "functions_arithmetic.yaml",
                "multiply",
                expressions=[column("salary"), literal(1.1, fp64())],
                alias="salary_with_bonus",
            ),
        ],
    )

    print("Users with age > 25 and calculated salary:")
    pretty_print_plan(enriched_users(registry), use_colors=True)

    print("\n" + "=" * 50 + "\n")

    print("=== Sort and Fetch Example ===")
    # Example with sort and fetch operations
    orders_schema = named_struct(
        names=["order_id", "amount", "status"],
        struct=struct(
            types=[
                i64(nullable=False),  # order_id
                fp64(nullable=False),  # amount
                string(nullable=False),  # status
            ]
        ),
    )

    orders = read_named_table("orders", orders_schema)

    # Filter orders with amount > 50
    high_value_orders = filter(
        orders,
        expression=scalar_function(
            "functions_comparison.yaml",
            "gt",
            expressions=[column("amount"), literal(50.0, fp64())],
        ),
    )

    # Sort by amount descending
    sorted_orders = sort(
        high_value_orders,
        expressions=[
            (
                column("amount"),
                stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST,
            )  # descending order
        ],
    )

    # Limit to top 5 results
    final_result = fetch(
        sorted_orders, offset=literal(0, i64()), count=literal(5, i64())
    )

    print("Top 5 high-value orders sorted by amount:")
    pretty_print_plan(final_result(registry), use_colors=True)

    print("\n" + "=" * 50 + "\n")


def expression_only_example():
    print("=== Expression-Only Example ===")
    # Show complex expression structure
    complex_expr = scalar_function(
        "functions_arithmetic.yaml",
        "multiply",
        expressions=[
            scalar_function(
                "functions_arithmetic.yaml",
                "add",
                expressions=[
                    column("base_salary"),
                    scalar_function(
                        "functions_arithmetic.yaml",
                        "multiply",
                        expressions=[
                            column("base_salary"),
                            literal(0.15, fp64()),  # 15% bonus
                        ],
                    ),
                ],
            ),
            scalar_function(
                "functions_arithmetic.yaml",
                "subtract",
                expressions=[
                    literal(1.0, fp64()),
                    literal(0.25, fp64()),  # 25% tax rate
                ],
            ),
        ],
    )

    print("Complex salary calculation expression:")
    # Create a simple plan to wrap the expression
    dummy_schema = named_struct(
        names=["base_salary"], struct=struct(types=[fp64(nullable=False)])
    )
    dummy_table = read_named_table("dummy", dummy_schema)
    dummy_plan = project(dummy_table, expressions=[complex_expr])
    pretty_print_plan(dummy_plan(registry), use_colors=True)

    print("\n" + "=" * 50 + "\n")

    print("=== Manual Map Literal Example ===")
    # Example with manually constructed map literal

    # Create a map literal manually
    map_literal_expr = stalg.Expression(
        literal=stalg.Expression.Literal(
            map=stalg.Expression.Literal.Map(
                key_values=[
                    stalg.Expression.Literal.Map.KeyValue(
                        key=stalg.Expression.Literal(string="batch_size"),
                        value=stalg.Expression.Literal(i64=1000),
                    ),
                    stalg.Expression.Literal.Map.KeyValue(
                        key=stalg.Expression.Literal(string="timeout"),
                        value=stalg.Expression.Literal(i64=30),
                    ),
                    stalg.Expression.Literal.Map.KeyValue(
                        key=stalg.Expression.Literal(string="retry_count"),
                        value=stalg.Expression.Literal(i64=3),
                    ),
                ]
            )
        )
    )
    print("Simple map literal:")
    print(f"  Type: {type(map_literal_expr)}")
    print(f"  Has literal field: {map_literal_expr.HasField('literal')}")
    if map_literal_expr.HasField("literal"):
        print(f"  Has map field: {map_literal_expr.literal.HasField('map')}")
        if map_literal_expr.literal.HasField("map"):
            print(
                f"  Map key_values count: {len(map_literal_expr.literal.map.key_values)}"
            )

    print("\nTesting pretty_print_expression:")
    pretty_print_expression(map_literal_expr, use_colors=True)

    # Create a nested map literal to test recursion
    nested_map_expr = stalg.Expression(
        literal=stalg.Expression.Literal(
            map=stalg.Expression.Literal.Map(
                key_values=[
                    stalg.Expression.Literal.Map.KeyValue(
                        key=stalg.Expression.Literal(string="config"),
                        value=stalg.Expression.Literal(
                            map=stalg.Expression.Literal.Map(
                                key_values=[
                                    stalg.Expression.Literal.Map.KeyValue(
                                        key=stalg.Expression.Literal(
                                            string="threshold"
                                        ),
                                        value=stalg.Expression.Literal(i64=50),
                                    ),
                                    stalg.Expression.Literal.Map.KeyValue(
                                        key=stalg.Expression.Literal(string="enabled"),
                                        value=stalg.Expression.Literal(boolean=True),
                                    ),
                                ]
                            )
                        ),
                    ),
                    stalg.Expression.Literal.Map.KeyValue(
                        key=stalg.Expression.Literal(string="version"),
                        value=stalg.Expression.Literal(string="1.0.0"),
                    ),
                ]
            )
        )
    )

    print("\nNested map literal:")
    print(f"  Type: {type(nested_map_expr)}")
    print(f"  Has literal field: {nested_map_expr.HasField('literal')}")
    if nested_map_expr.HasField("literal"):
        print(f"  Has map field: {nested_map_expr.literal.HasField('map')}")
        if nested_map_expr.literal.HasField("map"):
            print(
                f"  Map key_values count: {len(nested_map_expr.literal.map.key_values)}"
            )
            # Check if it has nested maps
            for i, kv in enumerate(nested_map_expr.literal.map.key_values):
                if kv.value.HasField("map"):
                    print(
                        f"  Key {i} has nested map with {len(kv.value.map.key_values)} entries"
                    )

    print("\nTesting pretty_print_expression with nested map:")
    pretty_print_expression(nested_map_expr, use_colors=True)


if __name__ == "__main__":
    basic_example()
    advanced_example()
    expression_only_example()
