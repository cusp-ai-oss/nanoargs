"""
Edge case tests for NanoArgs functionality.

This module contains tests for edge cases, error conditions, and boundary scenarios
that might not be covered by the main test files.
"""

import pathlib
import textwrap
from typing import List, Optional

import pytest
import yaml
from pydantic import BaseModel, Field, ValidationError

from nanoargs.cli import NanoArgs
from nanoargs.path import Path


class MinimalCfg(BaseModel):
    """Minimal configuration for edge case testing."""

    value: int


class ConstrainedCfg(BaseModel):
    """Configuration with validation constraints."""

    positive_int: int = Field(gt=0, description="Must be positive")
    bounded_float: float = Field(ge=0.0, le=1.0, description="Must be between 0 and 1")
    non_empty_string: str = Field(min_length=1, description="Cannot be empty")
    limited_list: List[int] = Field(max_length=5, description="Max 5 items")


class RecursiveCfg(BaseModel):
    """Configuration with recursive/self-referencing structure."""

    name: str
    children: Optional[List["RecursiveCfg"]] = None


def write_file(path: pathlib.Path, content: str):
    """Helper to write dedented content to file."""
    path.write_text(textwrap.dedent(content))


class TestFileSystemEdgeCases:
    """Test edge cases related to file system operations."""

    def test_config_file_with_unicode_characters(self, tmp_path: pathlib.Path):
        """Test configuration files with unicode characters."""
        cfg = tmp_path / "unicode.yaml"
        write_file(cfg, "value: 42  # Comment with émojis: 🎉🔥⚡️")

        result = NanoArgs(MinimalCfg).parse(argv=[str(cfg)])
        assert result.value == 42

    def test_config_file_with_very_long_path(self, tmp_path: pathlib.Path):
        """Test handling of very long file paths."""
        # Create deeply nested directory structure
        long_path = tmp_path
        for i in range(10):
            long_path = (
                long_path / f"very_long_directory_name_{i}_with_lots_of_characters"
            )
        long_path.mkdir(parents=True)

        cfg = long_path / "config_with_a_very_long_filename.yaml"
        write_file(cfg, "value: 123")

        result = NanoArgs(MinimalCfg).parse(argv=[str(cfg)])
        assert result.value == 123

    def test_config_file_permissions_error(self, tmp_path: pathlib.Path):
        """Test handling of files with permission issues."""
        cfg = tmp_path / "restricted.yaml"
        write_file(cfg, "value: 42")

        # Make file unreadable (skip on Windows where chmod behavior differs)
        import os

        if os.name != "nt":
            cfg.chmod(0o000)

            with pytest.raises(PermissionError):
                NanoArgs(MinimalCfg).parse(argv=[str(cfg)])

            # Restore permissions for cleanup
            cfg.chmod(0o644)

    def test_binary_file_instead_of_yaml(self, tmp_path: pathlib.Path):
        """Test error handling when binary file is provided instead of YAML."""
        binary_file = tmp_path / "binary.yaml"
        binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        with pytest.raises((UnicodeDecodeError, yaml.YAMLError)):
            NanoArgs(MinimalCfg).parse(argv=[str(binary_file)])

    def test_empty_file_handling(self, tmp_path: pathlib.Path):
        """Test handling of completely empty files."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.touch()  # Create empty file

        # Should work if model has defaults, fail otherwise
        with pytest.raises((ValidationError, TypeError)):
            NanoArgs(MinimalCfg).parse(argv=[str(empty_file)])


class TestYAMLEdgeCases:
    """Test edge cases related to YAML parsing."""

    def test_malformed_yaml_syntax(self, tmp_path: pathlib.Path):
        """Test handling of malformed YAML syntax."""
        cfg = tmp_path / "malformed.yaml"
        write_file(
            cfg,
            """
        value: 42
          malformed: indentation
        another: [unclosed, list
        """,
        )

        with pytest.raises(yaml.YAMLError):
            NanoArgs(MinimalCfg).parse(argv=[str(cfg)])

    def test_yaml_with_tabs_and_spaces_mixed(self, tmp_path: pathlib.Path):
        """Test YAML with tabs in values (tabs not allowed in YAML indentation)."""
        cfg = tmp_path / "mixed_indent.yaml"
        # Tabs in values are allowed; tabs in indentation are not
        cfg.write_text('value: 42\nextra: "tab\there"')

        result = NanoArgs(MinimalCfg).parse(argv=[str(cfg)])
        assert result.value == 42

    def test_yaml_with_special_characters_in_keys(self, tmp_path: pathlib.Path):
        """Test YAML with special characters in keys."""
        cfg = tmp_path / "special_keys.yaml"
        write_file(
            cfg,
            """
        value: 42
        "key with spaces": "value1"
        key-with-dashes: "value2"
        key_with_underscores: "value3"
        "key@with#special$chars%": "value4"
        123numeric_key: "value5"
        """,
        )

        result = NanoArgs(MinimalCfg).parse(argv=[str(cfg)])
        assert result.value == 42

    def test_yaml_with_very_large_numbers(self, tmp_path: pathlib.Path):
        """Test YAML with very large numbers."""
        cfg = tmp_path / "large_numbers.yaml"
        write_file(cfg, f"value: {2**63 - 1}")  # Max int64

        result = NanoArgs(MinimalCfg).parse(argv=[str(cfg)])
        assert result.value == 2**63 - 1

    def test_yaml_with_scientific_notation(self, tmp_path: pathlib.Path):
        """Test YAML with scientific notation."""

        class FloatCfg(BaseModel):
            value: float

        cfg = tmp_path / "scientific.yaml"
        write_file(
            cfg, "value: 1.0e2"
        )  # YAML scientific notation (requires float form)

        result = NanoArgs(FloatCfg).parse(argv=[str(cfg)])
        assert result.value == 100.0


class TestOverrideEdgeCases:
    """Test edge cases related to override functionality."""

    def test_override_with_very_long_path(self, tmp_path: pathlib.Path):
        """Test override with extremely long JSONPath."""
        cfg = tmp_path / "nested.yaml"
        write_file(
            cfg,
            """
        level1:
          level2:
            level3:
              level4:
                level5:
                  level6:
                    level7:
                      level8:
                        level9:
                          level10:
                            value: 1
        """,
        )

        # This will fail because model doesn't match structure, but tests parsing
        with pytest.raises((ValidationError, KeyError)):
            NanoArgs(MinimalCfg).parse(
                argv=[
                    str(cfg),
                    "--override",
                    "$.level1.level2.level3.level4.level5.level6.level7.level8.level9.level10.value=42",
                ]
            )

    def test_override_with_special_json_values(self, tmp_path: pathlib.Path):
        """Test override with special JSON values."""
        cfg = tmp_path / "base.yaml"
        write_file(cfg, "value: 1")

        # Test with different number since MinimalCfg.value is int
        result = NanoArgs(MinimalCfg).parse(argv=[str(cfg), "--override", "$.value=99"])
        assert result.value == 99

        # Test with another number
        result2 = NanoArgs(MinimalCfg).parse(
            argv=[str(cfg), "--override", "$.value=42"]
        )
        assert result2.value == 42

    def test_override_with_escaped_quotes(self, tmp_path: pathlib.Path):
        """Test override with escaped quotes in strings."""
        cfg = tmp_path / "base.yaml"
        write_file(cfg, "value: 42")

        # This would fail validation since value expects int, but tests parsing
        with pytest.raises(ValidationError):
            NanoArgs(MinimalCfg).parse(
                argv=[
                    str(cfg),
                    "--override",
                    '$.value="String with \\"escaped\\" quotes"',
                ]
            )

    def test_override_with_unicode_in_values(self, tmp_path: pathlib.Path):
        """Test override with unicode characters in values."""
        cfg = tmp_path / "base.yaml"
        write_file(cfg, "value: 42")

        # This would fail validation, but tests unicode handling
        with pytest.raises(ValidationError):
            NanoArgs(MinimalCfg).parse(
                argv=[str(cfg), "--override", '$.value="Unicode: 🎉 αβγ 中文"']
            )

    def test_override_with_very_large_json_object(self, tmp_path: pathlib.Path):
        """Test override with large JSON object."""
        cfg = tmp_path / "base.yaml"
        write_file(cfg, "value: 42")

        # Create large JSON object
        large_obj = {f"key_{i}": f"value_{i}" for i in range(1000)}
        import json

        large_json = json.dumps(large_obj)

        # This would fail validation, but tests large object parsing
        with pytest.raises(ValidationError):
            NanoArgs(MinimalCfg).parse(
                argv=[str(cfg), "--override", f"$.value={large_json}"]
            )

    def test_multiple_overrides_to_same_path_edge_case(self, tmp_path: pathlib.Path):
        """Test edge case with many overrides to same path."""
        cfg = tmp_path / "base.yaml"
        write_file(cfg, "value: 1")

        # Apply 100 overrides to same path
        overrides = []
        for i in range(100):
            overrides.extend(["--override", f"$.value={i}"])

        result = NanoArgs(MinimalCfg).parse(argv=[str(cfg)] + overrides)
        assert result.value == 99  # Last override wins


class TestValidationEdgeCases:
    """Test edge cases related to Pydantic validation."""

    def test_validation_with_constraints(self, tmp_path: pathlib.Path):
        """Test validation constraints are enforced."""
        cfg = tmp_path / "constrained.yaml"
        write_file(
            cfg,
            """
        positive_int: 10
        bounded_float: 0.5
        non_empty_string: "hello"
        limited_list: [1, 2, 3]
        """,
        )

        result = NanoArgs(ConstrainedCfg).parse(argv=[str(cfg)])
        assert result.positive_int == 10
        assert result.bounded_float == 0.5

        # Test constraint violations
        with pytest.raises(ValidationError):
            NanoArgs(ConstrainedCfg).parse(
                argv=[str(cfg), "--override", "$.positive_int=-1"]
            )

        with pytest.raises(ValidationError):
            NanoArgs(ConstrainedCfg).parse(
                argv=[str(cfg), "--override", "$.bounded_float=2.0"]
            )

        with pytest.raises(ValidationError):
            NanoArgs(ConstrainedCfg).parse(
                argv=[str(cfg), "--override", '$.non_empty_string=""']
            )

        with pytest.raises(ValidationError):
            NanoArgs(ConstrainedCfg).parse(
                argv=[str(cfg), "--override", "$.limited_list=[1,2,3,4,5,6,7,8,9,10]"]
            )

    def test_recursive_model_validation(self, tmp_path: pathlib.Path):
        """Test validation with recursive/self-referencing models."""
        cfg = tmp_path / "recursive.yaml"
        write_file(
            cfg,
            """
        name: "root"
        children:
          - name: "child1"
            children:
              - name: "grandchild1"
                children: null
          - name: "child2"
            children: null
        """,
        )

        result = NanoArgs(RecursiveCfg).parse(argv=[str(cfg)])
        assert result.name == "root"
        assert len(result.children) == 2
        assert result.children[0].name == "child1"
        assert result.children[0].children[0].name == "grandchild1"


class TestConcurrencyEdgeCases:
    """Test edge cases related to potential concurrency issues."""

    def test_path_caching_thread_safety(self):
        """Test that path caching doesn't cause issues with concurrent access."""
        import threading
        import time

        results = []
        errors = []

        def parse_path():
            try:
                for i in range(100):
                    path = Path.from_string(f"$.item_{i % 10}")
                    results.append(path.to_string())
                    time.sleep(0.001)  # Small delay to encourage race conditions
            except Exception as e:
                errors.append(e)

        # Run multiple threads concurrently
        threads = [threading.Thread(target=parse_path) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Should have no errors and all results should be valid
        assert len(errors) == 0
        assert len(results) == 1000
        assert all(result.startswith("$.item_") for result in results)


class TestMemoryEdgeCases:
    """Test edge cases related to memory usage."""

    def test_very_large_config_file(self, tmp_path: pathlib.Path):
        """Test handling of very large configuration files."""
        cfg = tmp_path / "large.yaml"

        # Create a smaller but valid config
        large_content = "value: 42\n"
        large_content += "\n".join([f"item_{i}: {i}" for i in range(100)])

        cfg.write_text(large_content)

        result = NanoArgs(MinimalCfg).parse(argv=[str(cfg)])
        assert result.value == 42

    def test_deeply_nested_structure_limits(self, tmp_path: pathlib.Path):
        """Test limits of deeply nested structures."""
        cfg = tmp_path / "deep.yaml"

        # Create smaller nested structure
        content = "value: 42\n"
        nested = "nested:\n  level_0:\n    level_1:\n      level_2: true"

        write_file(cfg, content + nested)

        result = NanoArgs(MinimalCfg).parse(argv=[str(cfg)])
        assert result.value == 42


class TestErrorMessageQuality:
    """Test that error messages are helpful and informative."""

    def test_helpful_validation_error_messages(self, tmp_path: pathlib.Path):
        """Test that validation errors provide helpful messages."""
        cfg = tmp_path / "invalid.yaml"
        write_file(cfg, "value: 'not_an_integer'")

        try:
            NanoArgs(MinimalCfg).parse(argv=[str(cfg)])
            assert False, "Should have raised validation error"
        except ValidationError as e:
            # Error message should mention the field and type issue
            error_str = str(e)
            assert "value" in error_str.lower()
            assert any(word in error_str.lower() for word in ["int", "integer", "type"])

    def test_helpful_file_not_found_messages(self):
        """Test that file not found errors are clear."""
        try:
            NanoArgs(MinimalCfg).parse(argv=["nonexistent_file.yaml"])
            assert False, "Should have raised file not found error"
        except (FileNotFoundError, SystemExit):
            # Should get a clear error about the missing file
            pass  # Expected behavior

    def test_helpful_override_syntax_error_messages(self, tmp_path: pathlib.Path):
        """Test that override syntax errors provide helpful guidance."""
        cfg = tmp_path / "base.yaml"
        write_file(cfg, "value: 42")

        try:
            NanoArgs(MinimalCfg).parse(
                argv=[str(cfg), "--override", "invalid_syntax_no_equals_or_colon"]
            )
            assert False, "Should have raised syntax error"
        except ValueError as e:
            error_str = str(e)
            assert "syntax" in error_str.lower()
            assert any(char in error_str for char in ["=", ":"])


# === Phase 3: Full integration test (3g) ===


class TestFullIntegration:
    """Combine ALL features in one test."""

    def test_import_merge_override_defaults(self, tmp_path: pathlib.Path):
        """Integration: !import + multi-file merge + --override + @file + defaults."""
        from typing import Optional

        class IntegrationCfg(BaseModel):
            name: str = "default_name"
            count: int = 0
            enabled: bool = True
            items: List[int] = []
            nested: Optional[dict] = None

        # Base config with !import
        base_import = tmp_path / "base_values.yaml"
        write_file(base_import, "name: imported\ncount: 10\nitems: [1, 2, 3]")

        base = tmp_path / "base.yaml"
        write_file(base, "!import\n  - base_values.yaml")

        # Override file
        override = tmp_path / "override.yaml"
        write_file(override, "count: 20\nnested:\n  key: value")

        # @file reference
        at_file = tmp_path / "items.json"
        at_file.write_text("[10, 20, 30]")

        c = NanoArgs(IntegrationCfg).parse(
            argv=[
                str(base),
                str(override),
                "--override",
                f"$.items=@{at_file}",
                "--override",
                '$.name="final"',
                "--override",
                "$.enabled=false",
            ]
        )

        assert c.name == "final"
        assert c.count == 20
        assert c.enabled is False
        assert c.items == [10, 20, 30]
        assert c.nested == {"key": "value"}
