<!-- generated-by: sqlbuild skills -->

# sqb format

> Apply canonical SQLBuild SQL formatting.

Online: https://sqlbuild.com/docs/cli/format/

Formats SQL files using SQLBuild's canonical, dialect-aware representation.

```bash
sqb format [flags]
```

| Flag | Description |
|------|-------------|
| `--check` | Fail when formatting changes are needed without writing |
| `--diff` | Print the proposed diff without writing |
| `--json` | Print structured results |
| `--select`, `-s` | Format selected models |
| `--select-file` | Read selectors from a file |
| `--exclude` | Exclude models from the selected scope |

```bash
sqb format
sqb format --check
sqb format --diff --select tag:marts
```

Formatting owns presentation and source rewriting. Compiler-integrated diagnostics belong to
configured [Rules](../concepts/rules.md), which never mutate source.

## Line width and descriptions

Long model and scenario descriptions are reflowed deterministically. Ordinary authored line breaks
are normalized as spaces, while blank lines preserve paragraph boundaries. Configure the maximum
physical line width in `sqlbuild_project.toml` (the default is `100`):

```toml
[format]
line_width = 100
```

## What formatting preserves

Formatting preserves authored cast types, postfix casts, quoted literals, variant paths, typed
lambda parameters, and supported SQL function spellings while applying canonical layout. SQLBuild
calls keep their authored spelling, including zero-argument cursor and empty-fixture intrinsics.
CTE-producing macros remain authored calls rather than expanded project SQL, with each call on its
own CTE-list line and leading comments attached to the node they describe.

## Unsafe bodies

`sqb format` reports a file-specific `format-unsafe` fault whenever a SQL body cannot be safely
formatted, including parser, comment-attachment, interpolation-restoration, and idempotence
failures. The entire original file is kept (including its headers and fixtures), the reason
appears in human and JSON output, and both formatting and `sqb format --check` exit nonzero. A
declined body is never counted as canonical.
