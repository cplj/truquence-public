"""Action Contract v0: strict loading, schema validation and exact-byte SHA-256."""
import hashlib
import json
import os
from pathlib import Path
import stat

MAX_INPUT_BYTES = 1024 * 1024
MAX_ITEMS = 1000
MAX_NODES = 20000
MAX_DEPTH = 64


class InputLimitError(ValueError):
    pass


def read_bytes(path):
    """Bound allocation before hashing/decoding, including files that grow."""
    if not stat.S_ISREG(Path(path).stat().st_mode):
        raise ValueError("regular input file required")
    with Path(path).open("rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("regular input file required")
        if info.st_size > MAX_INPUT_BYTES:
            raise InputLimitError("INPUT_LIMIT_EXCEEDED: maximum 1048576 bytes per file")
        raw = handle.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise InputLimitError("INPUT_LIMIT_EXCEEDED: maximum 1048576 bytes per file")
    return raw


def check_limits(value):
    nodes = 0

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            raise InputLimitError("INPUT_LIMIT_EXCEEDED: JSON depth or node count")
        if isinstance(item, (dict, list)):
            if len(item) > MAX_ITEMS:
                raise InputLimitError("INPUT_LIMIT_EXCEEDED: maximum 1000 members per container")
            for child in item.values() if isinstance(item, dict) else item:
                visit(child, depth + 1)
    visit(value, 0)
    return value

SCHEMA = Path(__file__).resolve().parent / "schema/action_contract.schema.json"
if not SCHEMA.exists():
    SCHEMA = Path(__file__).resolve().parents[1] / "schema/action_contract.schema.json"


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite JSON number: " + value)


def decode(raw):
    if len(raw) > MAX_INPUT_BYTES:
        raise InputLimitError("INPUT_LIMIT_EXCEEDED: maximum 1048576 bytes per file")
    return check_limits(json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                                   parse_constant=_constant))


def hash(path):
    """SHA-256 of exact file bytes, including whitespace; never a signature."""
    return hashlib.sha256(read_bytes(path)).hexdigest()


def _validate(value, schema, path):
    # Only the keywords used by our fixed v0 schema are implemented.
    types = {"object": dict, "array": list, "string": str,
             "boolean": bool, "integer": int}
    if "type" in schema and type(value) is not types[schema["type"]]:
        raise ValueError(path + ": expected " + schema["type"])
    if "const" in schema and value != schema["const"]:
        raise ValueError(path + ": wrong constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(path + ": unsupported value")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            raise ValueError(path + ": missing " + ", ".join(sorted(missing)))
        if schema.get("additionalProperties") is False and value.keys() - properties.keys():
            raise ValueError(path + ": unexpected fields")
        if len(value) < schema.get("minProperties", 0):
            raise ValueError(path + ": empty object")
        for key, sub in properties.items():
            if key in value:
                _validate(value[key], sub, path + "." + key)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(path + ": empty array")
        for index, item in enumerate(value):
            _validate(item, schema["items"], path + "[" + str(index) + "]")
        if schema.get("uniqueItems") and len(set(value)) != len(value):
            raise ValueError(path + ": duplicate items")
    if isinstance(value, str) and len(value.strip()) < schema.get("minLength", 0):
        raise ValueError(path + ": empty string")
    if type(value) is int and value < schema.get("minimum", value):
        raise ValueError(path + ": below minimum")


def validate(contract):
    """Return the validated contract; raise ValueError for invalid v0 input."""
    # Round-trip also rejects non-JSON Python values and non-finite numbers.
    check_limits(contract)
    decode(json.dumps(contract, allow_nan=False).encode("utf-8"))
    _validate(contract, decode(SCHEMA.read_bytes()), "contract")
    ids = [item["x-id"] for item in contract["x-tasks"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate action ID")
    for action in contract["x-tasks"]:
        if action["x-tool"] not in action["x-scope"] or action["x-tool"] not in action["x-allowed_actions"]:
            raise ValueError("action tool must be in its delegation scope and allowed actions")
    return contract


def load(path):
    return validate(decode(read_bytes(path)))
