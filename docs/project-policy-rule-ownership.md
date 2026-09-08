# SQL lint and Project Policy ownership

SQLBuild assigns deterministic checks by the evidence they require:

> SQL lint evaluates one plain SQL statement. Project Policy evaluates how SQLBuild resources are
> organised, configured, documented, tested, and connected.

Compiler checks remain mandatory artifact-correctness invariants. The formatter owns one canonical
presentation. A check is not Project Policy merely because it is strict or opinionated.

## Former Kata rule disposition

This ledger accounts for every rule in the replaced `SQBK` catalogue. Old identities are not aliases
for the new rules.

| Former code | Final owner | Final code | Reason |
| --- | --- | --- | --- |
| `SQBKS000` | SQL lint | `SQBL033` | Comment attachment is statement-local; the old first-inner-CTE-line restriction was deleted. |
| `SQBKS001` | SQL lint | `SQBL034` | Top-level CTE shape needs only parsed SQL. |
| `SQBKS002` | SQL lint | `SQBL035` | Terminal-select shape needs only parsed SQL. |
| `SQBKS101` | Project Policy | `SQBPS101` | Import CTEs depend on resolved SQLBuild references and sources. |
| `SQBKS201` | Project Policy | `SQBPS102` | The star allowance depends on identifying dependency-import CTEs and configured exceptions. |
| `SQBKS202` | SQL lint | `SQBL007` | Positional set-operation stars were already covered by native lint. |
| `SQBKS301` | SQL lint | `SQBL036` | Nested CTEs are visible in one parsed statement. |
| `SQBKS302` | SQL lint | `SQBL037` | Recursive CTEs are visible in one parsed statement. |
| `SQBKS401` | Project Policy | `SQBPS103` | The check compares model naming with resolved materialisation. |
| `SQBKS501` | Deleted | — | Judging whether a CTE name is descriptive is subjective. |
| `SQBKL001` | Project Policy | `SQBPG101` | Layer direction requires the compiled dependency graph. |
| `SQBKL101` | Project Policy | `SQBPG102` | Managed dependencies require SQLBuild reference/source ownership. |
| `SQBKR001` | Project Policy | `SQBPR101` | Model identity is a SQLBuild resource fact. |
| `SQBKR002` | Project Policy | `SQBPR102` | Folder ownership is repository context. |
| `SQBKR201` | Project Policy | `SQBPR103` | Source vocabulary is project configuration. |
| `SQBKR301` | Project Policy | `SQBPR104` | Referenced model identity comes from compilation. |
| `SQBKR401` | Project Policy | `SQBPC101` | Contract enforcement is MODEL metadata. |
| `SQBKR500`–`SQBKR503` | Project Policy | `SQBPR201`–`SQBPR204` | Domain and owner layout require repository paths and project-wide inventory. |
| `SQBKJ001` | SQL lint | `SQBL002` | Comma joins were already covered by native lint. |
| `SQBKJ002` | SQL lint | `SQBL038` | An explicit cross join is statement-local and suppressible with a reason. |
| `SQBKJ101` | SQL lint | `SQBL003` | Missing or unconditional join constraints were already covered by native lint. |
| `SQBKN001`–`SQBKN003` | Project Policy | `SQBPC102`–`SQBPC104` | These checks compare names with declared contract types. |
| `SQBKH001`–`SQBKH002` | Project Policy | `SQBPD101`–`SQBPD102` | Enum and constant use requires declarations and compiled substitutions. |
| `SQBKH101` | Project Policy | `SQBPD201` | Duplicate declarations require project-wide inventory. |
| `SQBKH201` | Project Policy | `SQBPD301` | Declaration placement requires repository ownership. |
| `SQBKH301`–`SQBKH305` | Project Policy | `SQBPD302`–`SQBPD306` | Declaration-container checks require paths and project-wide inventory. |
| `SQBKT001`–`SQBKT004` | Project Policy | `SQBPT101`–`SQBPT104` | Test roots, names, and ownership require compiler test resources. |
| `SQBKT101` | Project Policy | `SQBPT105` | Scenario description policy requires SCENARIO metadata. |
| `SQBKX001`–`SQBKX002` | Project Policy | `SQBPT201`–`SQBPT202` | Audit and test minima require compiled model evidence. |
| `SQBKX201` | Project Policy | `SQBPT301` | Custom-policy coverage requires the configured policy catalogue and test inventory. |

## Final Project Policy families

- `SQBPC`: contracts and declared column semantics.
- `SQBPD`: declarations and decision vocabulary.
- `SQBPG`: compiled dependency graph policy.
- `SQBPR`: repository naming and ownership layout.
- `SQBPS`: SQLBuild-aware model structure.
- `SQBPT`: SQL tests, audits, and custom-policy evidence.

Built-ins use `SQBP<family><three digits>`. Custom Project Policy rules use
`XSQBP<family><three digits>`. Custom statement-local lint rules use
`XSQBL<family><three digits>` and receive no model, path, graph, declaration, filesystem,
environment, process, network, or warehouse capabilities from their context.
