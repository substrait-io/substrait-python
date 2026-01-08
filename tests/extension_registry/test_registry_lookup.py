from substrait.builders.type import decimal, i8, i16
from substrait.gen.proto.type_pb2 import Type


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
