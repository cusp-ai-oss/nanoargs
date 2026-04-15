# Changelog

## 0.5.0

**Simplification pass — remove magic, fix path restrictions**:

- **Removed flag-style overrides** (`--field value` / `--field=value` shorthand). Use `--override '$.field=value'` instead. Unknown flags now error immediately (strict `parse_args`).
- **Removed `resolve()`**. Use `parse()` followed by Pydantic's `model_dump()` for raw data.
- **Removed path wildcards** (`$.*`, `$[*]`), `match()`, and `extract_paths()`.
- **Added `$[-1]` negative index support** (Python-style wrap-around; previously an artificial restriction).
- **Added single-quote bracket notation**: `$['key']` is now equivalent to `$["key"]`.
- **Added stdin support**: pass `-` as a config file to read YAML/JSON from stdin (`echo 'lr: 0.01' | myapp -`).
- Improved subcommand positional-before-command error message.

## 0.4.0

**Subcommand support via `Nested` base class (330 tests)**:

- Added `Nested` — a `BaseModel` subclass that turns its fields into subcommands. Fields typed as `T | None = None` where `T` is a `BaseModel` or pydantic dataclass become selectable subcommands.
- Each subcommand owns its own argv slice and runs through the full `load_and_merge` pipeline independently.
- Pre-command flags/overrides apply to parent `Nested` fields; post-command args go to the child.
- `NanoArgs.__init__` now accepts `prog: str | None = None` for customising the usage line.
- Child `NanoArgs` instances are cached at construction (no per-call allocation).
- `_build_arg_parser` now shows a subcommand-aware usage line and lists available commands.
- Fixed `Annotated[T, Field(...)] | None` not being detected as a subcommand field.
- Fixed `--help`/`-h` exit code (was erroneously exiting 2).
- `--print-config` before a command now gives a clear, actionable error message.
- Empty `Nested` class (no detectable fields) raises `ValueError` at construction.
- Child parser `prog` now includes the parent program name via `self.parser.prog`.
- Pydantic dataclasses are now accepted as subcommand field types in addition to `BaseModel`.
- Bug fixes for `Literal` display, `str | Path` display, `--print-schema`, and enum schema rendering (backported from separate PRs).

## 0.3.0

**Round 2 adversarial stress testing (29 new tests, 246 total)**:

- Fixed `!import` merging to deep-merge nested dicts instead of shallow replace (keys no longer silently lost)
- Fixed `!import` crash when merging type-mismatched structures (dict + list)
- Fixed empty `.json` file via `@` reference causing `JSONDecodeError` (now returns `None`)
- Fixed `@` reference on directory path causing `IsADirectoryError` (clear error message)
- Fixed `@` reference with whitespace after `@` not being stripped
- Added `@@` escape for literal `@`-prefixed strings in overrides
- Fixed flag-style `--learning-rate` generating unparseable `$.learning-rate` path (now uses bracket notation)
- Fixed `!override` crash when target is `None` (from empty import)
- Added warnings for override paths targeting unknown model fields
- Fixed `_replace` silently losing base keys (simplified to full replacement as intended)
- Fixed flag-style and `--override` ordering -- now interleaved by CLI position
- Fixed `Path.__add__` producing double Root nodes
- Fixed `--=value` (empty key) being silently dropped (now warns)
- Added auto-vivification of `None` and missing intermediate keys in `modify()`
- Added negative slice start/end support (`$[-3:]`, `$[:-1]`)
- Removed dead grammar rules (boolean, null, object, array, float, etc.)
- Added clear error messages for unsupported file formats (`.toml`, `.ini`, etc.)
- Fixed error message saying "no wildcards or slices" when only wildcards are prohibited
- Optimized `extract_paths` from O(n^2) to O(n) with mutable prefix list

## 0.2.0

**Bug fixes from adversarial stress testing (25 new tests)**:

- Fixed empty defaults `{}` being treated as `None` during override application
- Fixed mutable default contamination across multiple `parse()` calls
- Fixed `_deep_merge` not copying incoming values (shared reference corruption)
- Fixed `resolve_value` crash on strings invalid in both JSON and YAML
- Fixed YAML anchor/alias corruption when applying overrides
- Fixed `Property.to_string()` not escaping special characters (keys with dots, hyphens, etc. now round-trip correctly)
- Fixed aggressive YAML scalar coercion in CLI overrides (`"NO"` no longer becomes `False`, `"error: msg"` no longer becomes a dict)
- Fixed `extract_paths` crash on non-string dict keys
- Fixed tuple data not handled in path operations (`extract`, `modify`, `match`, `extract_paths`)
- Fixed whitespace silently ignored in path expressions
- Fixed global `yaml.Dumper` pollution on import
- Fixed enum and non-standard defaults silently dropped from merged output
- Converted recursive path operations to iterative (no more `RecursionError` on deep paths)
- Added circular reference detection in `extract_paths`
- Added warning when scalar config file replaces accumulated dict data
- Cached model defaults at init time (no repeated `default_factory` calls)
- Improved error messages for negative indices and single-quote bracket notation

## 0.1.0

- Initial release
- YAML configuration loading with imports
- JSONPath-like override syntax
- Pydantic model validation
- Rich CLI interface with beautiful schema output
