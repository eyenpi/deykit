from decimal import localcontext

import pytest

from deykit.contracts.json_value import JsonError
from deykit.contracts.schema import compile_schema, validate_json


def test_exact_integer_and_multiple_of_under_tiny_context():
    with localcontext() as ctx:
        ctx.prec = 2
        assert not validate_json('{"type":"integer"}', "9007199254740993.0")
        assert validate_json('{"type":"integer"}', "9007199254740993.1")
        assert validate_json('{"type":"integer"}', "true")
        assert not validate_json(
            '{"type":"number","multipleOf":0.0000000000000000001}', "0.1234567890123456789"
        )
        assert validate_json('{"multipleOf":0.0000000000000000002}', "0.1234567890123456789")
        assert not validate_json('{"multipleOf":0.1}', "0.3")
        assert validate_json('{"maximum":9007199254740992}', "9007199254740993")


@pytest.mark.parametrize(
    "schema,code",
    [
        ('{"type":"made-up"}', "invalid_schema"),
        ('{"required":"x"}', "invalid_schema"),
        ('{"multipleOf":0}', "invalid_schema"),
        ('{"$ref":"https://example.com/schema"}', "remote_schema_reference"),
        ('{"$defs":{"x":{"$dynamicRef":"file:///etc/passwd"}}}', "remote_schema_reference"),
        ('{"$ref":"other.json"}', "remote_schema_reference"),
        ('{"$schema":"http://json-schema.org/draft-07/schema#"}', "unsupported_schema_dialect"),
    ],
)
def test_schema_rejections_without_network(schema, code):
    with pytest.raises(JsonError, match=code):
        compile_schema(schema)


def test_local_reference_and_missing_local_reference():
    schema = '{"$defs":{"n":{"type":"integer"}},"$ref":"#/$defs/n"}'
    assert not validate_json(schema, "1.0")
    assert validate_json(schema, '"1"')
    with pytest.raises(JsonError, match="unresolved_schema_reference"):
        validate_json('{"$ref":"#/$defs/missing"}', "1")
    with pytest.raises(JsonError, match="schema_resource_limit"):
        validate_json('{"$ref":"#"}', "1")


def test_reference_words_inside_user_data_are_not_schema_references():
    schema = '{"type":"object","properties":{"$ref":{"type":"string"}},"const":{"$ref":"a value"}}'
    assert not validate_json(schema, '{"$ref":"a value"}')


def test_same_dialect_nested_schema_retains_exact_numbers():
    dialect = '"$schema":"https://json-schema.org/draft/2020-12/schema",'
    inline = '{"properties":{"n":{' + dialect + '"type":"integer"}}}'
    assert not validate_json(inline, '{"n":1.0}')
    assert validate_json(inline, '{"n":1.1}')
    referenced = '{"$defs":{"n":{' + dialect + '"multipleOf":0.1}},"$ref":"#/$defs/n"}'
    with localcontext() as ctx:
        ctx.prec = 2
        assert not validate_json(referenced, "123456789012345678901234567890.1")
        assert validate_json(referenced, "123456789012345678901234567890.11")


def test_schema_data_can_contain_reference_and_identifier_fields():
    assert not validate_json('{"properties":{"$id":{"type":"string"}}}', '{"$id":"x"}')
    assert not validate_json('{"const":{"$id":"data"}}', '{"$id":"data"}')
    assert not validate_json(
        '{"enum":[{"$ref":"https://example.com/data"}]}', '{"$ref":"https://example.com/data"}'
    )


def test_reference_target_outside_schema_positions_is_explicitly_rejected():
    source = (
        '{"x-schema":{"$schema":"https://json-schema.org/draft/2020-12/schema",'
        '"type":"integer"},"$ref":"#/x-schema"}'
    )
    with pytest.raises(JsonError, match="unresolved_schema_reference"):
        compile_schema(source)
    assert not validate_json('{"$defs":{"n":{"$anchor":"n","type":"integer"}},"$ref":"#n"}', "1")
