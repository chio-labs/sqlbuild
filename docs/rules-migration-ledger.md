# Rules migration ledger

SQLBuild assigns deterministic checks by the evidence they require:

> SQL rules evaluate one plain SQL statement. Project-aware rules evaluate how SQLBuild resources are
> organised, configured, documented, tested, and connected.

Compiler checks remain mandatory artifact-correctness invariants. The formatter owns one canonical
presentation. A check is not project-aware rules merely because it is strict or opinionated.

## Former Kata rule disposition

This ledger accounts for every rule in the replaced `SQBK` catalogue. Old identities are not aliases
for the new rules.

| Former code | Final owner | Final code | Reason |
| --- | --- | --- | --- |
| `SQBKS000` | SQL Rules | `SQBRSQL033` | Comment attachment is statement-local; the old first-inner-CTE-line restriction was deleted. |
| `SQBKS001` | SQL Rules | `SQBRSQL034` | Top-level CTE shape needs only parsed SQL. |
| `SQBKS002` | SQL Rules | `SQBRSQL035` | Terminal-select shape needs only parsed SQL. |
| `SQBKS101` | project-aware rules | `SQBRMODEL101` | Import CTEs depend on resolved SQLBuild references and sources. |
| `SQBKS201` | project-aware rules | `SQBRMODEL102` | The star allowance depends on identifying dependency-import CTEs and configured exceptions. |
| `SQBKS202` | SQL Rules | `SQBRSQL007` | Positional set-operation stars were already covered by native lint. |
| `SQBKS301` | SQL Rules | `SQBRSQL036` | Nested CTEs are visible in one parsed statement. |
| `SQBKS302` | SQL Rules | `SQBRSQL037` | Recursive CTEs are visible in one parsed statement. |
| `SQBKS401` | project-aware rules | `SQBRMODEL103` | The check compares model naming with resolved materialisation. |
| `SQBKS501` | Deleted | — | Judging whether a CTE name is descriptive is subjective. |
| `SQBKL001` | project-aware rules | `SQBRGRAPH101` | Layer direction requires the compiled dependency graph. |
| `SQBKL101` | project-aware rules | `SQBRGRAPH102` | Managed dependencies require SQLBuild reference/source ownership. |
| `SQBKR001` | project-aware rules | `SQBRPROJECT101` | Model identity is a SQLBuild resource fact. |
| `SQBKR002` | project-aware rules | `SQBRPROJECT102` | Folder ownership is repository context. |
| `SQBKR201` | project-aware rules | `SQBRPROJECT103` | Source vocabulary is project configuration. |
| `SQBKR301` | project-aware rules | `SQBRPROJECT104` | Referenced model identity comes from compilation. |
| `SQBKR401` | project-aware rules | `SQBRCONTRACT101` | Contract enforcement is MODEL metadata. |
| `SQBKR500`–`SQBKR503` | project-aware rules | `SQBRPROJECT201`–`SQBRPROJECT204` | Domain and owner layout require repository paths and project-wide inventory. |
| `SQBKJ001` | SQL Rules | `SQBRSQL002` | Comma joins were already covered by native lint. |
| `SQBKJ002` | SQL Rules | `SQBRSQL038` | An explicit cross join is statement-local and suppressible with a reason. |
| `SQBKJ101` | SQL Rules | `SQBRSQL003` | Missing or unconditional join constraints were already covered by native lint. |
| `SQBKN001`–`SQBKN003` | project-aware rules | `SQBRCONTRACT102`–`SQBRCONTRACT104` | These checks compare names with declared contract types. |
| `SQBKH001`–`SQBKH002` | project-aware rules | `SQBRDECLARATION101`–`SQBRDECLARATION102` | Enum and constant use requires declarations and compiled substitutions. |
| `SQBKH101` | project-aware rules | `SQBRDECLARATION201` | Duplicate declarations require project-wide inventory. |
| `SQBKH201` | project-aware rules | `SQBRDECLARATION301` | Declaration placement requires repository ownership. |
| `SQBKH301`–`SQBKH305` | project-aware rules | `SQBRDECLARATION302`–`SQBRDECLARATION306` | Declaration-container checks require paths and project-wide inventory. |
| `SQBKT001`–`SQBKT004` | project-aware rules | `SQBRTEST101`–`SQBRTEST104` | Test roots, names, and ownership require compiler test resources. |
| `SQBKT101` | project-aware rules | `SQBRTEST105` | Scenario description rules require SCENARIO metadata. |
| `SQBKX001`–`SQBKX002` | project-aware rules | `SQBRTEST201`–`SQBRTEST202` | Audit and test minima require compiled model evidence. |
| `SQBKX201` | project-aware rules | `SQBRTEST301` | Custom-rule coverage requires the configured Rules catalogue and test inventory. |

## Rules families

- `SQBRCONTRACT`: contracts and declared column semantics.
- `SQBRDECLARATION`: declarations and decision vocabulary.
- `SQBRGRAPH`: compiled dependency graph rules.
- `SQBRPROJECT`: repository naming and ownership layout.
- `SQBRMODEL`: SQLBuild-aware model structure.
- `SQBRTEST`: SQL tests, audits, and custom-rule evidence.

Current built-ins use `SQBR<FAMILY><three digits>`. Current custom rules use
`XSQBR<optional family><three digits>`. Former `SQBL001`–`SQBL038` codes map directly to
`SQBRSQL001`–`SQBRSQL038`. Former `SQBP` families map to the complete family words above. Former
`XSQBL...` and `XSQBP...` custom codes must be reassigned to globally unique `XSQBR...` codes.
The former identifiers are migration evidence only and are not accepted as aliases.
