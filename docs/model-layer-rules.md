# Model layer rules

SQLBuild model layers describe semantic responsibility, not the highest layer among a model's
dependencies. A model keeps its role when it imports a published interface.

Model identities use exactly one authoritative layer:

```text
<domain>__<layer>__<subject>[__<source>]
```

Supported layers and canonical folders are:

| Layer | Folder | Logical schema |
| --- | --- | --- |
| `stg`, `stg_v` | `staging` | `staging` |
| `int_clean` | `intermediate/clean` | `intermediate` |
| `int_enriched`, `int_v` | `intermediate/enriched` | `intermediate` |
| `mart`, `mart_v` | `mart` | `mart` |

`mart` and `mart_v` are published interfaces. Staging and intermediate layers are internal. The
internal dependency order is `stg`/`stg_v` → `int_clean` → `int_enriched`/`int_v`; dependencies on
published marts are outside that rank check.

Schemas belong in central path defaults, not individual `MODEL()` declarations. View
materialization requires the matching `_v` layer, and `_v` appears only in the canonical layer
segment.

Temporary internal dependency debt uses exact central exceptions:

```toml
[[rules.graph_edge_exceptions]]
consumer = "orders__stg__daily_orders"
dependency = "orders__int_clean__customer_orders"
reason = "Remove after the shared normalization is moved upstream."
```

An exception matches one consumer/dependency edge. Wildcards are unsupported, and an entry that no
longer suppresses an internal inversion is reported as stale.
