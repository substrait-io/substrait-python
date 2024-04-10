import json
import base64
from substrait.proto import Plan

# This types are represented as base64 in JSON
# we could autodetect them from the protocol definition,
# but it seems to complicate code for little benefit
# given that they are very few.
BASE64_LITERALS = {"decimal", }


def load_json(filename):
    """Load a Substrait Plan from a json file"""
    with open(filename) as f:
        json_plan = json.load(f, object_hook=_adapt_json_object)
    return Plan(**json_plan)


def parse_json(text):
    """Generate a Substrait Plan from its JSON definition"""
    json_plan = json.loads(text, object_hook=_adapt_json_object)
    return Plan(**json_plan)


def _adapt_json_object(jsonobj):
    """Adapt loaded JSON objects to match Substrait Proto

    The JSON format has little discrepancies from what the
    actual protocol defines, we have to adapt the loaded objects
    to resolve this differences
    """
    jsonobj = {_camel_to_undertick(k): v for k,v in jsonobj.items()}
    _fix_fetch(jsonobj)
    if "literal" in jsonobj:
        jsonobj["literal"] = _decode_literal(jsonobj["literal"])
    return jsonobj


def _camel_to_undertick(text):
    """Convert a string from CamelCase to under_tick_format"""
    def undertick_generator(text):
        for char in text:
            if char.isupper():
                yield "_"
            yield char.lower()
    return "".join(undertick_generator(text))


def _decode_literal(literal):
    """Decode literals stored as BASE64 strings"""
    literal_type = set(literal.keys()) & BASE64_LITERALS
    if literal_type:
        literal_type = literal_type.pop()
        literal_def = literal[literal_type]
        literal_value = literal_def.pop("value")
        return {literal_type: dict(**literal_def, value=base64.b64decode(literal_value))}
    return literal


def _fix_fetch(jsonobj):
    """Fix offset and count in fetch definitions.

    For some reason substrait producers are generating
    fetch with offset and count being strings,
    while their defintion in the proto is as int64.

    We apply a workaround to retain compatibility with
    producers that generated them as strings.
    """
    if "fetch" in jsonobj:
        fetch = jsonobj["fetch"]
        if "offset" in fetch:
            fetch["offset"] = int(fetch["offset"])
        if "count" in fetch:
            fetch["count"] = int(fetch["count"])
        jsonobj["fetch"] = fetch
