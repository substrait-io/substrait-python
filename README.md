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

## Produce a Substrait Plan
The ``substrait.proto`` module provides access to the classes
that represent a substrait Plan, thus allowing to create new plans.

Here is an example plan equivalent to ``SELECT first_name FROM person``
where ``people`` table has ``first_name`` and ``surname`` columns of type ``String``

```
>>> from substrait import proto
>>> plan = proto.Plan(
...   relations=[
...     proto.PlanRel(
...       root=proto.RelRoot(
...         names=["first_name"], 
...         input=proto.Rel(
...           read=proto.ReadRel(
...             named_table=proto.ReadRel.NamedTable(names=["people"]),
...             base_schema=proto.NamedStruct(
...               names=["first_name", "surname"], 
...               struct=proto.Type.Struct(
...                 types=[
...                   proto.Type(string=proto.Type.String(nullability=proto.Type.Nullability.NULLABILITY_REQUIRED)), 
...                   proto.Type(string=proto.Type.String(nullability=proto.Type.Nullability.NULLABILITY_REQUIRED))
...                 ]  # /types
...               )  # /struct
...             )  # /base_schema
...           )  # /read
...         )  # /input
...       )  # /root
...     )  # /PlanRel
...   ]  # /relations
... )
>>> print(plan)
relations {
  root {
    input {
      read {
        base_schema {
          names: "first_name"
          names: "surname"
          struct {
            types {
              string {
                nullability: NULLABILITY_REQUIRED
              }
            }
            types {
              string {
                nullability: NULLABILITY_REQUIRED
              }
            }
          }
        }
        named_table {
          names: "people"
        }
      }
    }
    names: "first_name"
  }
}
>>> serialized_plan = p.SerializeToString()
>>> serialized_plan
b'\x1aA\x12?\n1\n/\x12#\n\nfirst_name\n\x07surname\x12\x0c\n\x04b\x02\x10\x02\n\x04b\x02\x10\x02:\x08\n\x06people\x12\nfirst_name'
```

## Consume the Substrait Plan
The same plan we generated in the previous example, 
can be loaded back from its binary representation
using the ``Plan.ParseFromString`` method:

```
>>> from substrait.proto import Plan
>>> p = Plan()
>>> p.ParseFromString(serialized_plan)
67
>>> p
relations {
  root {
    input {
      read {
        base_schema {
          names: "first_name"
          names: "surname"
          struct {
            types {
              string {
                nullability: NULLABILITY_REQUIRED
              }
            }
            types {
              string {
                nullability: NULLABILITY_REQUIRED
              }
            }
          }
        }
        named_table {
          names: "people"
        }
      }
    }
    names: "first_name"
  }
}
```

## Load a Substrait Plan from JSON
A substrait plan can be loaded from its JSON representation
using the ``substrait.json.load_json`` and ``substrait.json.parse_json``
functions:

```
>>> import substrait.json
>>> jsontext = """{
...   "relations":[
...     {
...       "root":{
...         "input":{
...           "read":{
...             "baseSchema":{
...               "names":[
...                 "first_name",
...                 "surname"
...               ],
...               "struct":{
...                 "types":[
...                   {
...                     "string":{
...                       "nullability":"NULLABILITY_REQUIRED"
...                     }
...                   },
...                   {
...                     "string":{
...                       "nullability":"NULLABILITY_REQUIRED"
...                     }
...                   }
...                 ]
...               }
...             },
...             "namedTable":{
...               "names":[
...                 "people"
...               ]
...             }
...           }
...         },
...         "names":[
...           "first_name"
...         ]
...       }
...     }
...   ]
... }"""
>>> substrait.json.parse_json(jsontext)
relations {
  root {
    input {
      read {
        base_schema {
          names: "first_name"
          names: "surname"
          struct {
            types {
              string {
                nullability: NULLABILITY_REQUIRED
              }
            }
            types {
              string {
                nullability: NULLABILITY_REQUIRED
              }
            }
          }
        }
        named_table {
          names: "people"
        }
      }
    }
    names: "first_name"
  }
}
```

## Produce a Substrait Plan with Ibis
Let's use an existing Substrait producer, [Ibis](https://ibis-project.org), 
to provide an example using Python Substrait as the consumer.

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

In [7]: from substrait.proto import Plan

In [8]: my_plan = Plan()

In [9]: my_plan.ParseFromString(protobuf_msg)
Out[9]: 186

In [10]: print(my_plan)
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
