from google.protobuf import json_format

from substrait.proto import Plan


def load_json(filename):
    """Load a Substrait Plan from a json file"""
    with open(filename, encoding="utf-8") as f:
        return parse_json(f.read())


def parse_json(text):
    """Generate a Substrait Plan from its JSON definition"""
    return json_format.Parse(text=text, message=Plan())


def write_json(plan, filename):
    """Write a Substrait Plan to a json file"""
    with open(filename, "w+") as f:
        f.write(dump_json(plan))


def dump_json(plan):
    """Dump a Substrait Plan to a string in JSON format"""
    return json_format.MessageToJson(plan)
