# SPDX-License-Identifier: Apache-2.0
"""Routines for loading and saving Substrait plans."""
import ctypes
import ctypes.util as ctutil
import enum
import substrait.gen.proto.plan_pb2 as plan_pb2
import sys


class PlanFileFormat(enum.Enum):
    BINARY = ctypes.c_int32(0)
    JSON = ctypes.c_int32(1)
    PROTOTEXT = ctypes.c_int32(2)
    TEXT = ctypes.c_int32(3)


class PlanFileException(Exception):
    pass


class SerializedPlan(ctypes.Structure):
    pass


SerializedPlan._fields_ = [
    ("buffer", ctypes.POINTER(ctypes.c_byte)),
    ("size", ctypes.c_uint32),
    ("errorMessage", ctypes.c_char_p),
]


# Load the C++ library
planloader_path = ctutil.find_library("planloader")
planloader_lib = ctypes.CDLL(planloader_path)
if planloader_lib is None:
    print('Failed to find planloader library')
    sys.exit(1)

# Declare the function signatures for the external functions.
external_load_substrait_plan = planloader_lib.load_substrait_plan
external_load_substrait_plan.argtypes = [ctypes.c_char_p]
external_load_substrait_plan.restype = ctypes.POINTER(SerializedPlan)

external_free_substrait_plan = planloader_lib.free_substrait_plan
external_free_substrait_plan.argtypes = [ctypes.POINTER(SerializedPlan)]
external_free_substrait_plan.restype = None

external_save_substrait_plan = planloader_lib.save_substrait_plan
external_save_substrait_plan.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32]
external_save_substrait_plan.restype = ctypes.c_char_p


def load_substrait_plan(filename: str) -> plan_pb2.Plan:
    """
    Loads a Substrait plan (in any format) from disk.

    Returns:
        A Plan protobuf object if successful.
    Raises:
        PlanFileException if an except occurs while converting or reading from disk.
    """
    result = external_load_substrait_plan(filename.encode('UTF-8'))
    if result.contents.errorMessage:
        raise PlanFileException(result.contents.errorMessage)
    data = ctypes.string_at(result.contents.buffer, result.contents.size)
    plan = plan_pb2.Plan()
    plan.ParseFromString(data)
    external_free_substrait_plan(result)
    return plan


def save_substrait_plan(plan: plan_pb2.Plan, filename: str, file_format: PlanFileFormat):
    """
    Saves the given plan to disk in the specified file format.

    Raises:
        PlanFileException if an except occurs while converting or writing to disk.
    """
    data = plan.SerializeToString()
    err = external_save_substrait_plan(data, len(data), filename.encode('UTF-8'), file_format.value)
    if err:
        raise PlanFileException(err)
