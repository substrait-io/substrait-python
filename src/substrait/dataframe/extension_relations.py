"""Abstract base classes for user-defined (extension) relations.

These mirror substrait-java's ``Extension.LeafRelDetail`` / ``SingleRelDetail`` /
``MultiRelDetail``: a user implements a *detail* class that knows how to
(de)serialize its ``google.protobuf.Any`` payload and how to derive its output
schema from its inputs. With that, the ergonomic frame can build a custom
relation, and schema inference can treat it like any built-in one.

Because substrait-python re-derives schemas from the serialized proto (whose
``detail`` is an opaque ``Any``), register the detail class with
``ExtensionRegistry.register_extension_relation`` so inference can reconstruct
it from a plan and call ``derive_schema`` -- the analog of substrait-java's
extension lookup used when reading a plan back.

``derive_schema`` receives the input(s) as ``Type.Struct`` (types only, as
available during both build and inference) and returns a ``NamedStruct`` so the
relation's output column names are defined by the extension.
"""

from __future__ import annotations

import abc

import substrait.type_pb2 as stt
from google.protobuf.any_pb2 import Any


class ExtensionLeafDetail(abc.ABC):
    """Behavior of a zero-input ``ExtensionLeafRel``."""

    #: The ``google.protobuf.Any`` ``type_url`` identifying this detail.
    type_url: str

    @abc.abstractmethod
    def to_any(self) -> Any:
        """Serialize this detail to a ``google.protobuf.Any``."""

    @classmethod
    @abc.abstractmethod
    def from_any(cls, detail: Any) -> "ExtensionLeafDetail":
        """Reconstruct a detail from its ``google.protobuf.Any``."""

    @abc.abstractmethod
    def derive_schema(self) -> stt.NamedStruct:
        """The relation's output schema."""


class ExtensionSingleDetail(abc.ABC):
    """Behavior of a single-input ``ExtensionSingleRel``."""

    type_url: str

    @abc.abstractmethod
    def to_any(self) -> Any:
        """Serialize this detail to a ``google.protobuf.Any``."""

    @classmethod
    @abc.abstractmethod
    def from_any(cls, detail: Any) -> "ExtensionSingleDetail":
        """Reconstruct a detail from its ``google.protobuf.Any``."""

    @abc.abstractmethod
    def derive_schema(self, input: stt.Type.Struct) -> stt.NamedStruct:
        """The output schema given the input relation's type."""


class ExtensionMultiDetail(abc.ABC):
    """Behavior of a multi-input ``ExtensionMultiRel``."""

    type_url: str

    @abc.abstractmethod
    def to_any(self) -> Any:
        """Serialize this detail to a ``google.protobuf.Any``."""

    @classmethod
    @abc.abstractmethod
    def from_any(cls, detail: Any) -> "ExtensionMultiDetail":
        """Reconstruct a detail from its ``google.protobuf.Any``."""

    @abc.abstractmethod
    def derive_schema(self, inputs: "list[stt.Type.Struct]") -> stt.NamedStruct:
        """The output schema given the input relations' types."""
