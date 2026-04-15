import pytest

from nanoargs.path import NumericIndex, Path, Property, Root, SliceIndex


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("$.foo[2].bar", "$.foo[2].bar"),
    ],
)
def test_path_roundtrip(expr, expected):
    assert Path.from_string(expr).to_string() == expected


def test_extract_basic():
    data = {"foo": [{"bar": 10}, {"bar": 20}, {"bar": 30}]}
    assert Path.from_string("$.foo[1].bar").extract(data) == 20


def test_extract_slice():
    data = {"arr": [0, 1, 2, 3, 4, 5]}
    assert Path.from_string("$.arr[1:4]").extract(data) == (1, 2, 3)


def test_modify_numeric_index():
    data = {"x": [10, 11, 12]}
    Path.from_string("$.x[1]").modify(data, 99)
    assert data["x"][1] == 99


def test_modify_numeric_index_alt():
    data = {"items": [1, 2, 3]}
    path = Path((Root(), Property("items"), NumericIndex(1)))
    path.modify(data, 99)
    assert data["items"][1] == 99


def test_modify_slice_mismatch_length():
    data = {"x": [0, 1, 2, 3]}
    with pytest.raises(ValueError):
        Path.from_string("$.x[0:2]").modify(data, [9])


@pytest.mark.parametrize(
    "expr,exc",
    [
        ("$.a.missing", KeyError),
        ("$.a[2]", IndexError),
    ],
)
def test_error_conditions(expr, exc):
    data = {"a": {}} if "missing" in expr else {"a": [1]}
    with pytest.raises(exc):
        Path.from_string(expr).extract(data)


def test_path_construction_from_components():
    """Test creating paths from individual components."""
    path = Path((Root(), Property("items"), NumericIndex(2), Property("value")))
    assert path.to_string() == "$.items[2].value"


def test_path_head_and_tail():
    """Test path head and tail operations."""
    path = Path.from_string("$.a.b[0].c")

    assert isinstance(path.head, Root)
    assert path.tail.to_string() == ".a.b[0].c"

    tail = path.tail
    assert isinstance(tail.head, Property)
    assert tail.head.name == "a"
    assert tail.tail.to_string() == ".b[0].c"


def test_path_is_empty():
    """Test empty path detection."""
    empty_path = Path(())
    assert empty_path.is_empty
    assert len(empty_path) == 0

    non_empty = Path.from_string("$.a")
    assert not non_empty.is_empty
    assert len(non_empty) == 2  # Root + Property


def test_path_indexing_and_slicing():
    """Test path indexing and slicing operations."""
    path = Path.from_string("$.a.b[0].c")

    # Test individual element access
    assert isinstance(path[0], Root)
    assert isinstance(path[1], Property)
    assert isinstance(path[1], Property) and path[1].name == "a"
    assert isinstance(path[2], Property)
    assert isinstance(path[2], Property) and path[2].name == "b"
    assert isinstance(path[3], NumericIndex)
    assert isinstance(path[3], NumericIndex) and path[3].value == 0

    # Test slicing
    slice_path = path[1:3]
    assert slice_path.to_string() == ".a.b"


def test_path_concatenation():
    """Test path concatenation operations."""
    path1 = Path.from_string("$.a.b")
    path2 = Path.from_string("$.c[0]")

    # D4: __add__ should strip Root from other to avoid double Root
    combined = path1 + path2
    assert combined.to_string() == "$.a.b.c[0]"


@pytest.mark.parametrize(
    "path_str,expected_chunks",
    [
        ("$", 1),
        ("$.name", 2),
        ("$.items[0]", 3),
        ("$.data.nested[1].value", 5),
        ("$.arr[1:5:2]", 3),
    ],
)
def test_path_length_parsing(path_str, expected_chunks):
    """Test that paths are parsed into correct number of chunks."""
    path = Path.from_string(path_str)
    assert len(path) == expected_chunks


def test_slice_index_component():
    """Test SliceIndex component functionality."""
    # Test various slice configurations
    slice_all = SliceIndex(None, None, None)
    assert slice_all.to_string() == "[:]"

    slice_start = SliceIndex(1, None, None)
    assert slice_start.to_string() == "[1:]"

    slice_end = SliceIndex(None, 5, None)
    assert slice_end.to_string() == "[:5]"

    slice_step = SliceIndex(1, 5, 2)
    assert slice_step.to_string() == "[1:5:2]"


def test_extract_with_slices():
    """Test extraction with various slice patterns."""
    data = {"numbers": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]}

    # Test step slicing
    result = Path.from_string("$.numbers[1:8:2]").extract(data)
    assert result == (1, 3, 5, 7)

    # Test reverse step
    result = Path.from_string("$.numbers[8:1:-2]").extract(data)
    assert result == (8, 6, 4, 2)

    # Test open-ended slices
    result = Path.from_string("$.numbers[7:]").extract(data)
    assert result == (7, 8, 9)

    result = Path.from_string("$.numbers[:3]").extract(data)
    assert result == (0, 1, 2)


def test_modify_with_nested_structures():
    """Test modification of deeply nested structures."""
    data = {
        "config": {
            "databases": [
                {"name": "primary", "port": 5432},
                {"name": "secondary", "port": 5433},
            ]
        }
    }

    # Modify nested value
    Path.from_string("$.config.databases[1].port").modify(data, 3306)
    assert data["config"]["databases"][1]["port"] == 3306

    # Original structure should be preserved
    assert data["config"]["databases"][0]["port"] == 5432
    assert data["config"]["databases"][0]["name"] == "primary"


def test_modify_slice_operations():
    """Test modification using slice operations."""
    data = {"values": [1, 2, 3, 4, 5]}

    # Replace middle elements
    Path.from_string("$.values[1:4]").modify(data, [10, 20, 30])
    assert data["values"] == [1, 10, 20, 30, 5]

    # Test slice length validation
    data2 = {"values": [1, 2, 3, 4, 5]}
    with pytest.raises(ValueError, match="Cannot set slice.*length"):
        Path.from_string("$.values[1:4]").modify(data2, [10, 20])  # Wrong length


def test_empty_path_operations():
    """Test operations on empty paths."""
    empty_path = Path(())
    data = {"test": "value"}

    # Extract from empty path should return data as-is
    assert empty_path.extract(data) == data

    # Modify with empty path should return the new value
    result = empty_path.modify(data, "new_value")
    assert result == "new_value"


def test_path_caching():
    """Test that path parsing is properly cached."""
    path1 = Path.from_string("$.complex.path[0].nested")
    path2 = Path.from_string("$.complex.path[0].nested")

    # Should return the same cached instance
    assert path1 is path2

    # Different paths should be different instances
    path3 = Path.from_string("$.different.path")
    assert path1 is not path3


def test_slice_start_only():
    """[5:] should parse as start=5, end=None (not start=None, end=5)."""
    path = Path.from_string("$.arr[5:]")
    chunk = path.chunks[2]
    assert isinstance(chunk, SliceIndex)
    assert chunk.start == 5
    assert chunk.end is None
    assert chunk.step is None


def test_slice_end_only():
    """[:5] should parse as start=None, end=5."""
    path = Path.from_string("$.arr[:5]")
    chunk = path.chunks[2]
    assert isinstance(chunk, SliceIndex)
    assert chunk.start is None
    assert chunk.end == 5
    assert chunk.step is None


def test_slice_empty():
    """[:] should parse as start=None, end=None."""
    path = Path.from_string("$.arr[:]")
    chunk = path.chunks[2]
    assert isinstance(chunk, SliceIndex)
    assert chunk.start is None
    assert chunk.end is None
    assert chunk.step is None


def test_slice_step_zero_raises():
    """Slice with step=0 should raise ValueError."""
    with pytest.raises(ValueError, match="step cannot be zero"):
        Path.from_string("$[0:5:0]")


def test_string_unescape():
    """Bracket accessor should properly unescape JSON strings."""
    path = Path.from_string('$["key\\"name"]')
    chunk = path.chunks[1]
    assert isinstance(chunk, Property)
    assert chunk.name == 'key"name'


def test_lark_error_wrapped():
    """Invalid path syntax should produce a helpful ValueError, not raw Lark error."""
    with pytest.raises(ValueError, match="Invalid path syntax"):
        Path.from_string("$.learning-rate")


# === Adversarial stress test fixes ===


def test_property_to_string_escapes_special_chars():
    """Property.to_string() should use bracket notation for non-identifier names (D3).

    Names containing dots, hyphens, spaces, quotes, or starting with digits
    must be emitted as $["name"] to round-trip correctly.
    """
    # Hyphenated key
    p1 = Property("a-b")
    s1 = p1.to_string()
    roundtripped1 = Path.from_string("$" + s1)
    assert roundtripped1.chunks[1] == p1

    # Dotted key — must NOT parse as two separate properties
    p2 = Property("a.b")
    s2 = p2.to_string()
    roundtripped2 = Path.from_string("$" + s2)
    assert len(roundtripped2.chunks) == 2  # Root + 1 Property, NOT Root + 2 Properties
    assert roundtripped2.chunks[1] == p2

    # Empty string key
    p3 = Property("")
    s3 = p3.to_string()
    roundtripped3 = Path.from_string("$" + s3)
    assert roundtripped3.chunks[1] == p3

    # Key with quote
    p4 = Property('key"quote')
    s4 = p4.to_string()
    roundtripped4 = Path.from_string("$" + s4)
    assert roundtripped4.chunks[1] == p4

    # Key that starts with digit
    p5 = Property("123abc")
    s5 = p5.to_string()
    roundtripped5 = Path.from_string("$" + s5)
    assert roundtripped5.chunks[1] == p5

    # Wildcard as literal key — must NOT parse as PropertyWildcard
    p6 = Property("*")
    s6 = p6.to_string()
    roundtripped6 = Path.from_string("$" + s6)
    assert isinstance(roundtripped6.chunks[1], Property)
    assert roundtripped6.chunks[1].name == "*"


def test_modify_tuple_element():
    """C3: Path.modify should handle tuple data (convert to list for mutation).

    Model defaults may produce tuples. Overriding an element like $.items[0]=99
    should work, not crash with TypeError.
    """
    data = {"items": (1, 2, 3)}
    path = Path.from_string("$.items[0]")
    result = path.modify(data, 99)
    assert result["items"][0] == 99
    assert result["items"][1] == 2
    assert result["items"][2] == 3


def test_extract_tuple_elements():
    """C3: Path.extract should handle tuple data like lists."""
    data = {"items": (10, 20, 30)}
    path = Path.from_string("$.items[1]")
    assert path.extract(data) == 20


def test_whitespace_in_path_rejected():
    """E1: Whitespace should not be silently ignored in paths.

    '$ . a' should NOT silently parse as '$.a'. Paths with stray whitespace
    are likely user errors and should raise ValueError.
    """
    with pytest.raises(ValueError):
        Path.from_string(" $ . a [ 0 ] ")
    # But whitespace inside brackets is fine (e.g. in string values)
    with pytest.raises(ValueError):
        Path.from_string("$ .a")


def test_deep_path_no_recursion_error():
    """C4: Deep paths should not cause RecursionError.

    extract/modify/match are now iterative, so paths with 1000+ components
    should work without hitting Python's recursion limit.
    """
    import sys

    depth = sys.getrecursionlimit() + 100  # exceed default limit

    # Build deeply nested data: {"a": {"a": {"a": ... 42 ...}}}
    data: dict | int = 42
    for _ in range(depth):
        data = {"a": data}

    # Build the path: $.a.a.a...a (depth times)
    chunks = (Root(),) + tuple(Property("a") for _ in range(depth))
    deep_path = Path(chunks)

    # extract should work without RecursionError
    assert deep_path.extract(data) == 42

    # modify should work without RecursionError
    result = deep_path.modify(data, 99)
    assert deep_path.extract(result) == 99


# === Round 2 tests ===


def test_path_add_strips_double_root():
    """D4: Path.__add__ should strip Root from other to avoid double Root."""
    p1 = Path.from_string("$.a")
    p2 = Path.from_string("$.b")
    combined = p1 + p2
    # Should be $.a.b, not $.a$.b
    assert combined.to_string() == "$.a.b"

    # Verify it's valid and extractable
    data = {"a": {"b": 42}}
    assert combined.extract(data) == 42


def test_path_add_empty_self():
    """D4: Adding to empty path should preserve Root from other."""
    empty = Path(())
    p = Path.from_string("$.a")
    combined = empty + p
    assert combined.to_string() == "$.a"


def test_negative_slice_start():
    """E7: Negative slice start should be supported."""
    path = Path.from_string("$.arr[-3:]")
    chunk = path.chunks[2]
    assert isinstance(chunk, SliceIndex)
    assert chunk.start == -3
    assert chunk.end is None


def test_negative_slice_end():
    """E7: Negative slice end should be supported."""
    path = Path.from_string("$.arr[:-1]")
    chunk = path.chunks[2]
    assert isinstance(chunk, SliceIndex)
    assert chunk.start is None
    assert chunk.end == -1


def test_negative_slice_extract():
    """E7: Negative slice should work in extraction."""
    data = {"arr": [0, 1, 2, 3, 4]}
    result = Path.from_string("$.arr[-3:]").extract(data)
    assert result == (2, 3, 4)


def test_grammar_no_dead_rules():
    """E6: Grammar should not contain dead rules (object, array, boolean, null, float)."""
    from nanoargs.path import PATH_GRAMMAR

    for dead_rule in ["object:", "array:", "boolean:", "null:", "float:"]:
        assert dead_rule not in PATH_GRAMMAR, (
            f"Dead rule {dead_rule!r} still in grammar"
        )


def test_modify_autovivify_none_intermediate():
    """C6: modify should auto-vivify None → {} for intermediate properties."""
    data = {"model": None}
    result = Path.from_string("$.model.layers").modify(data, 24)
    assert result["model"]["layers"] == 24


def test_modify_autovivify_none_deep():
    """C6: modify should auto-vivify None → {} for deeply nested None."""
    data = {"a": None}
    result = Path.from_string("$.a.b.c").modify(data, 42)
    assert result["a"]["b"]["c"] == 42


def test_modify_autovivify_missing_intermediate():
    """C6: modify should auto-vivify missing intermediate keys."""
    data = {"a": {}}
    result = Path.from_string("$.a.b.c").modify(data, 42)
    assert result["a"]["b"]["c"] == 42


def test_negative_index_extract():
    assert Path.from_string("$[-1]").extract([10, 20, 30]) == 30
    assert Path.from_string("$[-2]").extract([10, 20, 30]) == 20


def test_negative_index_modify():
    result = Path.from_string("$[-1]").modify([1, 2, 3], 99)
    assert result == [1, 2, 99]


def test_negative_index_out_of_bounds():
    with pytest.raises(IndexError):
        Path.from_string("$[-4]").extract([1, 2, 3])


def test_single_quoted_key_extract():
    assert Path.from_string("$['key']").extract({"key": 42}) == 42


def test_single_quoted_key_with_spaces():
    assert Path.from_string("$['my key']").extract({"my key": 7}) == 7
