import json
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from deykit.contracts.json_value import (
    JsonDocument,
    JsonError,
    JsonLimits,
    bytes_hash,
    canonical_bytes,
    dump_json,
    parse_json,
    semantic_hash,
)

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures/hash-vectors.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["id"])
def test_frozen_golden_vectors(vector):
    value = parse_json(vector["input"])
    assert canonical_bytes(value) == vector["canonical"].encode("utf-8")
    assert semantic_hash(value) == vector["expected_sha256"]


def test_a01_wire_order_is_distinct_from_semantics():
    bodies = VECTORS["wireOrderExample"]
    a, b = bodies["bodyA"].encode(), bodies["bodyB"].encode()
    assert semantic_hash(parse_json(a)) == semantic_hash(parse_json(b))
    assert bytes_hash(a) != bytes_hash(b)
    assert semantic_hash(parse_json('["A","B"]')) != semantic_hash(parse_json('["B","A"]'))


def test_a02_exact_beyond_decimal_context_and_source_boundary():
    source = '{"big":9007199254740993,"n":0.123456789012345678901234567890123456789,"é":"😀"}'
    document = JsonDocument(source)
    with localcontext() as ctx:
        ctx.prec = 2
        selected = document.select(("n", "big", "é"))
        body = dump_json({"model": "authored", "state": selected.value})
        assert body == (
            '{"model":"authored","state":{"n":'
            "0.123456789012345678901234567890123456789,"
            '"big":9007199254740993,"é":"😀"}}'
        )
    # Browser/API wraps editor text as a JSON string, never as JS Number fields.
    browser_envelope = json.dumps({"source": document.source})
    assert json.loads(browser_envelope)["source"] == source
    assert document.source == source
    mutable = document.value
    mutable["big"] = 0
    assert document.value["big"] == Decimal("9007199254740993")


@pytest.mark.parametrize(
    "source,code",
    [
        ('{"a":1,"a":2}', "duplicate_key"),
        ('{"a":1,"\\u0061":2}', "duplicate_key"),
        ("NaN", "nonfinite_number"),
        ("Infinity", "nonfinite_number"),
        ("-Infinity", "nonfinite_number"),
        ('"\\ud800"', "invalid_unicode"),
        ('{"\\udfff":0}', "invalid_unicode"),
        (b'"\xff"', "invalid_utf8"),
        ("01", "invalid_json"),
        ('"\ud800"', "invalid_unicode"),
    ],
)
def test_a03_rejections(source, code):
    with pytest.raises(JsonError, match=code):
        parse_json(source)


def test_controls_unicode_keys_and_equivalent_spellings():
    assert canonical_bytes(parse_json('"\\u0000\\b\\t\\n\\f\\r/"')) == b'"\\u0000\\b\\t\\n\\f\\r/"'
    assert parse_json('"\\ud83d\\ude00"') == "😀"
    assert canonical_bytes(parse_json('{"😀":0,"\uffff":0}')) == '{"\uffff":0,"😀":0}'.encode()
    assert len({semantic_hash(parse_json(s)) for s in ["1", "1.0", "10e-1", "0.1e1"]}) == 1
    with pytest.raises(JsonError, match="invalid_json_type"):
        dump_json(0.1)


def test_limits_at_actual_boundaries():
    assert parse_json('"' + "é" * 524287 + '"') == "é" * 524287
    with pytest.raises(JsonError, match="json_resource_limit"):
        parse_json('"' + "é" * 524288 + '"')
    parse_json("[" * 64 + "0" + "]" * 64)
    with pytest.raises(JsonError, match="json_resource_limit"):
        parse_json("[" * 65 + "0" + "]" * 65)
    parse_json("9" * 4096)
    with pytest.raises(JsonError, match="json_resource_limit"):
        parse_json("9" * 4097)
    for accepted in ("1e10000", "1e-10000", "1e0000001"):
        parse_json(accepted)
    for rejected in ("1e10001", "1e-10001", "1e00000001"):
        with pytest.raises(JsonError, match="json_resource_limit"):
            parse_json(rejected)
    parse_json("[" + ",".join(["0"] * 99999) + "]")
    with pytest.raises(JsonError, match="json_resource_limit"):
        parse_json("[" + ",".join(["0"] * 100000) + "]")
    assert parse_json("[0]", JsonLimits(max_nodes=2)) == [Decimal(0)]


@pytest.mark.parametrize("source", ["10e10000", "0.1e-10000", "999e9999"])
def test_effective_exponent_limit_closes_parse_under_hashing(source):
    with pytest.raises(JsonError, match="json_resource_limit"):
        parse_json(source)


@pytest.mark.parametrize("source", ["10e9999", "0.1e-9999", "1e10000", "1e-10000"])
def test_accepted_exponent_boundaries_round_trip(source):
    document = JsonDocument(source)
    assert semantic_hash(parse_json(dump_json(document.value))) == document.content_hash


def test_source_at_byte_boundary_can_hash_select_and_emit_generated_wire():
    from deykit.contracts.json_value import DEFAULT_LIMITS, GENERATED_LIMITS

    # Many short numeric tokens grow in the required canonical form. Keep a second
    # field to bring the original object exactly to the user-source byte limit.
    numbers = ",".join(["1"] * 10000)
    prefix = '{"numbers":[' + numbers + '],"padding":"'
    suffix = '"}'
    source = prefix + "x" * (DEFAULT_LIMITS.max_bytes - len(prefix) - len(suffix)) + suffix
    document = JsonDocument(source)
    assert len(canonical_bytes(document.value)) == DEFAULT_LIMITS.max_bytes + 20000
    assert len(document.content_hash) == 64
    selected = document.select(("numbers", "padding"))
    assert len(selected.source.encode()) <= DEFAULT_LIMITS.max_bytes
    assert selected.content_hash == document.content_hash
    wire = dump_json({"state": selected.value})
    assert parse_json(wire, GENERATED_LIMITS)["state"] == document.value


def test_wire_numbers_are_context_and_spelling_independent():
    outputs = []
    for capitals in (0, 1):
        with localcontext() as ctx:
            ctx.capitals = capitals
            ctx.prec = 2
            outputs.append(dump_json(parse_json("[1.0,10e-1,1e100,0.0100,-1000000000000]")))
    assert outputs == ["[1,1,1e100,1e-2,-1e12]"] * 2


@pytest.mark.parametrize("number", ["12e3", "123e6", "12.3e-99", "1.23e100", "0.1", "1.23e-10000"])
def test_selection_does_not_expand_short_exponent_spelling_at_byte_limit(number):
    from deykit.contracts.json_value import DEFAULT_LIMITS

    prefix = '{"n":' + number + ',"s":"'
    source = prefix + "x" * (DEFAULT_LIMITS.max_bytes - len(prefix) - 2) + '"}'
    document = JsonDocument(source)
    selected = document.select(("n", "s"))
    assert len(selected.source) <= len(source)
    assert selected.content_hash == document.content_hash
