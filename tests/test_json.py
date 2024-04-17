import os
import pathlib
import tempfile
import json

from substrait.proto import Plan
from substrait.json import load_json, parse_json, dump_json, write_json

import pytest


JSON_FIXTURES = (
    pathlib.Path(os.path.dirname(__file__))
    / ".."
    / "third_party"
    / "substrait-cpp"
    / "src"
    / "substrait"
    / "textplan"
    / "data"
)
JSON_TEST_FILE = sorted(JSON_FIXTURES.glob("*.json"))
JSON_TEST_FILENAMES = [path.name for path in JSON_TEST_FILE]


@pytest.mark.parametrize("jsonfile", JSON_TEST_FILE, ids=JSON_TEST_FILENAMES)
def test_json_load(jsonfile):
    with open(jsonfile) as f:
        jsondata = _strip_json_comments(f)
        parsed_plan = parse_json(jsondata)

        # Save to a temporary file so we can test load_json
        # on content stripped of comments.
        with tempfile.TemporaryDirectory() as tmpdir:
            # We use a TemporaryDirectory as on Windows NamedTemporaryFile
            # doesn't allow for easy reopening of the file.
            with open(pathlib.Path(tmpdir) / "jsonfile.json", "w+") as stripped_file:
                stripped_file.write(jsondata)
            loaded_plan = load_json(stripped_file.name)

    # The Plan constructor itself will throw an exception
    # in case there is anything wrong in parsing the JSON
    # so we can take for granted that if the plan was created
    # it is a valid plan in terms of protobuf definition.
    assert type(loaded_plan) is Plan

    # Ensure that when loading from file or from string
    # the outcome is the same
    assert parsed_plan == loaded_plan


@pytest.mark.parametrize("jsonfile", JSON_TEST_FILE, ids=JSON_TEST_FILENAMES)
def test_json_roundtrip(jsonfile):
    with open(jsonfile) as f:
        jsondata = _strip_json_comments(f)

    parsed_plan = parse_json(jsondata)
    assert parse_json(dump_json(parsed_plan)) == parsed_plan

    # Test with write/load
    with tempfile.TemporaryDirectory() as tmpdir:
        filename = pathlib.Path(tmpdir) / "jsonfile.json"
        write_json(parsed_plan, filename)
        assert load_json(filename) == parsed_plan


def _strip_json_comments(jsonfile):
    # The JSON files in the cpp testsuite are prefixed with
    # a comment containing the SQL that matches the json plan.
    # As Python JSON parser doesn't support comments,
    # we have to strip them to make the content readable
    return "\n".join(l for l in jsonfile.readlines() if l[0] != "#")
