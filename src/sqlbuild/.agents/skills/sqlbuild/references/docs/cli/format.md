<!-- generated-by: sqlbuild skills -->

# format

> Apply canonical SQLBuild SQL formatting.

Online: https://docs.sqlbuild.com/cli/format

# sqb format

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
