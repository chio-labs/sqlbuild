<!-- generated-by: sqlbuild skills -->

# Overview

> Limit enums, constants, and macros to the parts of a project that use them.

Online: https://docs.sqlbuild.com/concepts/declaration-scopes

Most projects can keep enums, constants, and macros in their ordinary top-level directories. Those
declarations are available throughout the project.

When an enum, constant, or macro should be available only within one folder or its child folders,
you can keep it near the SQL that uses it. SQLBuild uses the declaration directory's location to
decide which files can access it. No TOML configuration is required.

| Where the declaration lives | Who can use it |
|-------------------------------------|--------------------|
| Top-level `macros/`, `constants/`, or `enums/` | The whole project |
| Nested `_sqlbuild/macros/`, `_sqlbuild/constants/`, or `_sqlbuild/enums/` | Files in the owner folder and folders below it |
| Nested `_sqlbuild/_macros/`, `_sqlbuild/_constants/`, or `_sqlbuild/_enums/` | Files directly in the owner folder only |
| An underscored constant or enum inside `MODEL()` | That model and its inline SQL hooks only |

Macro declarations are Python files (`.py`). Constant and enum declarations are SQL files
(`.sql`).

## Example

The annotation beside each directory shows where its contents are available:

```text
models/
├── constants/                 published throughout models/
│   └── warehouse.sql
└── commerce/
    ├── _sqlbuild/
    │   ├── macros/            published throughout commerce/
    │   │   └── currency.py
    │   └── _enums/            exact commerce/ directory only
    │       └── grain.sql
    ├── orders.sql              sees warehouse, currency, and grain
    ├── finance/
    │   ├── _sqlbuild/
    │   │   └── macros/        published throughout finance/
    │   │       └── tax.py
    │   └── revenue.sql         sees warehouse, currency, and tax
    └── fulfillment/
        └── shipments.sql       sees warehouse and currency
```

The folder containing `_sqlbuild/` is the declaration owner. An unprefixed role applies to that
owner and everything below it. An underscored role applies only to files directly in the owner.
Legacy declaration roles directly below an owner remain supported.

`_sqlbuild/` is reserved for the six declaration-role directories shown above. Other direct files or
folders are rejected. It must also sit below a concrete owner directory. A project-root
`_sqlbuild/` or authored-root path such as `models/_sqlbuild/` is invalid; declarations at that
boundary belong in the project-wide `macros/`, `enums/`, or `constants/` roots.

| Resource | Visible from the example tree | Not visible |
|----------|-------------------------------|-------------|
| `orders.sql` | Warehouse constant, commerce macro, commerce-folder-only enum | Finance macro |
| `finance/revenue.sql` | Warehouse constant, commerce macro, finance macro | Commerce-folder-only enum |
| `fulfillment/shipments.sql` | Warehouse constant, commerce macro | Commerce-folder-only enum, finance macro |

Declarations do not flow upward or sideways into sibling directories.

## Terms used in text output

The CLI's text output uses short labels for the same four rules:

| Canonical label | Plain-language meaning |
|-----------------|------------------------|
| `project` | Available throughout the project |
| `descendant-public` | Available in this folder and folders below it |
| `exact-owner-private` | Available directly in this folder only |
| `model-private` | Available to one model only |

Here, an **owner folder** is simply the folder directly containing a model, test, hook, function, or
other authored resource. The [Scope Explorer](declaration-scopes/explorer.md) shows the owner
folder, its parents, and project-wide declarations separately.

JSON keeps the underlying enum values for integrations. Its `scope` field uses `global`,
`inherited`, `local`, or `private`, while derived `visibility` values use underscores, such as
`descendant_public` and `exact_owner_private`. Consumers should use the fields documented in the
versioned JSON schema rather than parsing text labels.

## Choose a location

| Where the value is needed | Placement |
|---------------------------|-----------|
| One model only | In that model's `MODEL()` header |
| Files directly in one folder | In an underscored role under the owner's `_sqlbuild/` folder |
| Files across one folder tree | In an unprefixed role under the nearest shared owner's `_sqlbuild/` folder |
| Different resource trees, such as models and tests | In a top-level declaration role |

SQLBuild computes the lowest common owner of every declaration's runtime consumers. A project-wide
declaration is valid only when no narrower supported owner contains all consumers. This keeps the
top-level roles as a genuine project API instead of a neutral dumping ground.

## Explore the feature

    See which declarations a model, test, hook, or function can use.
    Choose the narrowest folder that contains every real use.
    Ask SQLBuild what a file can use and preview how moving it would change that answer.

Learn the features themselves in [Enums](enums.md), [Constants](constants.md), and
[Writing Macros](macros.md). See [Interpolation](interpolation.md) for project,
environment, and runtime context values, which are separate from declarations.
