from substrait.type_pb2 import Type

from substrait.builders.type import decimal, i8, i16


def test_non_existing_urn(registry):
    assert (
        registry.lookup_function(
            urn="non_existent",
            function_name="add",
            signature=[i8(nullable=False), i8(nullable=False)],
        )
        is None
    )


def test_non_existing_function(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="sub",
            signature=[i8(nullable=False), i8(nullable=False)],
        )
        is None
    )


def test_non_existing_function_signature(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="add",
            signature=[i8(nullable=False)],
        )
        is None
    )


def test_exact_match(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i8(nullable=False), i8(nullable=False)],
    )[1] == Type(i8=Type.I8(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i8(nullable=False), i8(nullable=False), bool()],
    )[1] == Type(i16=Type.I16(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match_fails_with_constraits(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="add",
            signature=[i8(nullable=False), i16(nullable=False), i16(nullable=False)],
        )
        is None
    )


def test_wildcard_match_with_constraits(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i16(nullable=False), i16(nullable=False), i8(nullable=False)],
    )[1] == i8(nullable=False)


def test_variadic(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_fn",
        signature=[i8(nullable=False), i8(nullable=False), i8(nullable=False)],
    )[1] == i8(nullable=False)


def test_variadic_any(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_fn_variadic_any",
        signature=[i16(nullable=False), i16(nullable=False), i16(nullable=False)],
    )[1] == i16(nullable=False)


def test_variadic_fails_min_constraint(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_fn",
            signature=[i8(nullable=False)],
        )
        is None
    )


def test_decimal_happy_path(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal",
        signature=[decimal(8, 10, nullable=False), decimal(6, 8, nullable=False)],
    )[1] == decimal(7, 11, nullable=False)


def test_decimal_violates_constraint(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_decimal",
            signature=[decimal(8, 10, nullable=False), decimal(10, 12, nullable=False)],
        )
        is None
    )


def test_decimal_happy_path_discrete(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal_discrete",
        signature=[decimal(8, 10, nullable=True), decimal(6, 8, nullable=False)],
    )[1] == decimal(7, 11, nullable=True)


def test_enum_with_valid_option(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_enum",
        signature=["FLIP", i8(nullable=False)],
    )[1] == i8(nullable=False)


def test_enum_with_nonexistent_option(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_enum",
            signature=["NONEXISTENT", i8(nullable=False)],
        )
        is None
    )


def test_function_with_nullable_args(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i8(nullable=True), i8(nullable=False)],
    )[1] == i8(nullable=True)


def test_function_with_declared_output_nullability(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add_declared",
        signature=[i8(nullable=False), i8(nullable=False)],
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add_discrete",
        signature=[i8(nullable=True), i8(nullable=False)],
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability_nonexisting(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="add_discrete",
            signature=[i8(nullable=False), i8(nullable=False)],
        )
        is None
    )


# ``add`` exists both in the test extension and in the default
# functions_arithmetic, so it exercises resolution across several URNs.
_ARITHMETIC = "extension:io.substrait:functions_arithmetic"
_TEST = "extension:test:functions"


def test_find_function_single_urn_matches_lookup(registry):
    signature = [i8(nullable=False), i8(nullable=False)]
    match = registry.find_function("add", signature, [_TEST])
    assert match is not None
    assert match[0].urn == _TEST
    assert match == registry.lookup_function(_TEST, "add", signature)


def test_find_function_respects_candidate_urn_order(registry):
    signature = [i8(nullable=False), i8(nullable=False)]
    # The winning extension is the first candidate URN that has a matching
    # overload; ``entry.urn`` recovers it.
    assert registry.find_function("add", signature, [_ARITHMETIC, _TEST])[0].urn == (
        _ARITHMETIC
    )
    assert registry.find_function("add", signature, [_TEST, _ARITHMETIC])[0].urn == (
        _TEST
    )


def test_find_function_no_matching_overload_returns_none(registry):
    # ``add`` has no single-argument overload in any extension.
    assert registry.find_function("add", [i8(nullable=False)], [_ARITHMETIC]) is None


def test_find_function_searches_all_urns_when_unspecified(registry):
    signature = [i8(nullable=False), i8(nullable=False)]
    match = registry.find_function("add", signature)
    assert match is not None
    assert match == registry.list_functions_across_urns("add", signature)[0]
