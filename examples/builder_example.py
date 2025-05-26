from substrait.builders.plan import read_named_table, project, filter
from substrait.builders.extended_expression import column, scalar_function, literal
from substrait.builders.type import i64, boolean, struct, named_struct
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=True)

ns = named_struct(
    names=["id", "is_applicable"], struct=struct(types=[i64(nullable=False), boolean()])
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
