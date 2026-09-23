<!-- generated-by: sqlbuild skills -->

# Configuration and selection

> Select built-in and custom Rules by exact code or family prefix.

Online: https://docs.sqlbuild.com/concepts/rules/configuration-and-selection

Configure built-in and custom Rules together:

```toml
[rules]
select = ["SQBRSQL", "SQBRGRAPH", "XSQBRARCH"]
ignore = ["SQBRSQL004"]
```

An empty `select` disables configurable Rules. It does not disable mandatory compiler correctness.

## Codes and families

Built-in codes use `SQBR<FAMILY><three digits>`, such as `SQBRSQL004`, `SQBRMODEL101`, and
`SQBRGRAPH101`. Custom codes use `XSQBR<optional uppercase family><three digits>`, such as
`XSQBRARCH001`.

A family is always the code with its final three digits removed:

```text
SQBRSQL004    → SQBRSQL
XSQBRARCH001  → XSQBRARCH
XSQBR001      → XSQBR
```

Exact codes select one Rule. Prefixes select every matching Rule. `ignore` uses the same matching
semantics and takes precedence over `select`.

Use the catalogue to inspect available codes and metadata:

```bash
sqb rules list
sqb rules show SQBRSQL004
```

## Rule options

Custom Rules can declare typed options. Configure them by exact code:

```toml
[rules.rule_options.XSQBRNAME001]
required_prefix = "order"
```

Unknown Rule codes, option names, and invalid option values fail configuration.

## Focused selection

Run one exact Rule or family while developing or adopting it:

```bash
sqb rules run SQBRSQL004
sqb rules run SQBRSQL
sqb rules run XSQBRARCH --select customer_orders
```

Focused execution constructs the compiler facts needed by the selected Rules. It does not replace
the complete configured enforcement performed by `sqb compile`.

  See every `sqb rules` command and exit code.
