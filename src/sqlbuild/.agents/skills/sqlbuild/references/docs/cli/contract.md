<!-- generated-by: sqlbuild skills -->

# contract

> Compare or generate repository contracts from physical warehouse schemas.

Online: https://docs.sqlbuild.com/cli/contract

# sqb contract

Existing-schema comparison is explicitly online and read-only with respect to the warehouse.

## diff

```bash
sqb contract diff --from <target> [flags]
```

Reports declaration differences. Exit code `0` means agreement and `1` means differences exist.

## generate

```bash
sqb contract generate --from <target> [flags]
```

Prints proposed declaration updates. Add `--write` to change repository files and `--overwrite` to
replace conflicts rather than preserving authored declarations.

## Flags

| Flag | Commands | Description |
|------|----------|-------------|
| `--from` | both | Target namespace to inspect (required) |
| `--json` | both | Print structured findings |
| `--select`, `-s` | both | Inspect selected models or sources |
| `--select-file` | both | Read selectors from a file |
| `--exclude` | both | Exclude resources from the selected scope |
| `--vars` | both | Override project variables |
| `--write` | generate | Apply generated repository changes |
| `--overwrite` | generate | Replace conflicting declarations; requires `--write` |

See [Contracts](../concepts/models/contracts.md#adopting-an-existing-schema) for ownership and safety
guarantees.
