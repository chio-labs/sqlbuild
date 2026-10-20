<!-- generated-by: sqlbuild skills -->

# Published-layer Rules

> Keep each domain's published layer free of consumer-specific variants.

Online: https://sqlbuild.com/docs/concepts/rules/published-layer-rules/

A domain's published layer is its interface to the rest of the project. Under pressure to make
something work, it is tempting to add a consumer-specific variant next to an existing published
model:

```text
sales__int_clean__orders -> sales__mart__orders -> sales__mart__orders__finance -> finance__stg_v__orders
```

`sales__mart__orders__finance` reshapes a published model for one consumer in another domain. That
work belongs in the consumer's domain, or in the producing domain's intermediate layer. Two
built-in Rules catch it: `SQBRPROJECT107` by its name as soon as it is created, and `SQBRGRAPH103`
by its dependency even when the name looks uniform. Together they leave one fix: logic shared within
a domain belongs in its intermediate layer.

Both Rules read model names of the form `<domain>__<layer>__<entity>[__<qualifier>]`. Models whose
names do not follow that grammar are not checked. Both are errors and are selected with their
families (`SQBRGRAPH`, `SQBRPROJECT`) or `SQBR`.

## SQBRGRAPH103: no published reads within a domain

A model in a published layer must not read another published model of its own domain. The one
built-in allowance is a view of its own table: `<domain>__mart_v__<entity>[__<qualifier>]` may read
`<domain>__mart__<entity>`, or `<domain>__mart__<entity>__<qualifier>` with the same qualifier. Reading another domain's published models is the point of publishing
them and is allowed.

```text
error[SQBRGRAPH103]: sales__mart__orders__finance reads sales__mart__orders; published models must not read published models of their own domain
  --> models/sales/mart/sales__mart__orders__finance.sql:1:1
  = help: Move the shared logic into a sales__int_* model that both published models read, or move this model into the domain that consumes it. To move it into intermediate: sqb mv sales__mart__orders__finance models/sales/intermediate/enriched/sales__int_enriched__orders__finance.sql
```

## SQBRPROJECT107: one name shape per domain

Within one domain's published layer, every model name has the same number of segments: either all
`<domain>__<layer>__<entity>` or all `<domain>__<layer>__<entity>__<qualifier>`. The models that do
not fit the domain's majority shape are reported, with the remediation:

1. If a model with a qualifier adapts a model without one, move that logic into intermediate or into
   the consumer's domain.
2. If the domain really is split by qualifier, rename the models without one into the family, for
   example `sqb rename sales__mart__customers sales__mart__customers__core`.
3. If the qualifier is intentional and structural, allowlist it with a reason.

Allowlisted qualifiers are literal and do not count towards the shape: models that use them are left
out of the check. Each entry needs a reason, and an entry with a `domain` applies to that domain
only:

```toml
[rules.rule_options.SQBRPROJECT107]
allowed_qualifiers = [
  { qualifier = "csv_export", reason = "File export views of a published entity." },
  { domain = "sales", qualifier = "fra", reason = "Published once per country." },
]
```

## Published layers

Both Rules treat `mart` and `mart_v` as the published layers. Set `published_layers` on either Rule
to change that; each Rule reads its own option:

```toml
[rules.rule_options.SQBRGRAPH103]
published_layers = ["mart", "mart_v"]

[rules.rule_options.SQBRPROJECT107]
published_layers = ["mart", "mart_v"]
```

## Deviating

There are no inline suppressions. Turn a Rule off for the whole project with `[rules] ignore`, or
record one reviewed model as a `[[rules.rule_exceptions]]` entry with its path and a reason. See
[Findings and exceptions](findings-and-exceptions.md).
