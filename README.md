# Substrait

![PyPI version](https://badge.fury.io/py/substrait.svg)
![conda-forge version](https://anaconda.org/conda-forge/python-substrait/badges/version.svg)

A Python package for [Substrait](https://substrait.io), the cross-language specification for data compute operations.

## Installation

You can install the Python substrait bindings from PyPI or conda-forge

```sh
pip install substrait
```

```sh
conda install -c conda-forge python-substrait  # or use mamba
```

## Goals
This project aims to provide a Python interface for the Substrait specification. It will allow users to construct and manipulate a Substrait Plan from Python for evaluation by a Substrait consumer, such as DataFusion or DuckDB.

## Non-goals
This project is not an execution engine for Substrait Plans.

## Status
This is an experimental package that is still under development.

# Example
At the moment, this project contains only generated Python classes for the Substrait protobuf messages. Let's use an existing Substrait producer, [Ibis](https://ibis-project.org), to provide an example using Python Substrait as the consumer.
## Produce a Substrait Plan with Ibis
```
In [1]: import ibis

In [2]: movie_ratings = ibis.table(
   ...:     [
   ...:         ("tconst", "str"),
   ...:         ("averageRating", "str"),
   ...:         ("numVotes", "str"),
   ...:     ],
   ...:     name="ratings",
   ...: )
   ...:

In [3]: query = movie_ratings.select(
   ...:     movie_ratings.tconst,
   ...:     avg_rating=movie_ratings.averageRating.cast("float"),
   ...:     num_votes=movie_ratings.numVotes.cast("int"),
   ...: )

In [4]: from ibis_substrait.compiler.core import SubstraitCompiler

In [5]: compiler = SubstraitCompiler()

In [6]: protobuf_msg = compiler.compile(query).SerializeToString()

In [7]: type(protobuf_msg)
Out[7]: bytes
```
## Consume the Substrait Plan using Python Substrait
```
In [8]: import substrait

In [9]: from substrait.gen.proto.plan_pb2 import Plan

In [10]: my_plan = Plan()

In [11]: my_plan.ParseFromString(protobuf_msg)
Out[11]: 186

In [12]: print(my_plan)
relations {
  root {
    input {
      project {
        common {
          emit {
            output_mapping: 3
            output_mapping: 4
            output_mapping: 5
          }
        }
        input {
          read {
            common {
              direct {
              }
            }
            base_schema {
              names: "tconst"
              names: "averageRating"
              names: "numVotes"
              struct {
                types {
                  string {
                    nullability: NULLABILITY_NULLABLE
                  }
                }
                types {
                  string {
                    nullability: NULLABILITY_NULLABLE
                  }
                }
                types {
                  string {
                    nullability: NULLABILITY_NULLABLE
                  }
                }
                nullability: NULLABILITY_REQUIRED
              }
            }
            named_table {
              names: "ratings"
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
        expressions {
          cast {
            type {
              fp64 {
                nullability: NULLABILITY_NULLABLE
              }
            }
            input {
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
            failure_behavior: FAILURE_BEHAVIOR_THROW_EXCEPTION
          }
        }
        expressions {
          cast {
            type {
              i64 {
                nullability: NULLABILITY_NULLABLE
              }
            }
            input {
              selection {
                direct_reference {
                  struct_field {
                    field: 2
                  }
                }
                root_reference {
                }
              }
            }
            failure_behavior: FAILURE_BEHAVIOR_THROW_EXCEPTION
          }
        }
      }
    }
    names: "tconst"
    names: "avg_rating"
    names: "num_votes"
  }
}
version {
  minor_number: 24
  producer: "ibis-substrait"
}
```
