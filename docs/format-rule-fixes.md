# Compiler-verified Rule fixes

`sqb format` remains a layout-only command. Use `sqb format --fix` to apply
meaning-preserving Rule edits before layout formatting. `--fix --check` reports
proposed changes without writing files; `--fix --diff` prints their diff.

Edits are planned in memory and repeated to a fixed point. Overlapping edits are
reconsidered on the next pass. Every pass recompiles the candidate project and
compares output columns (including types and nullability), dependencies, and
column lineage against the original compilation. Missing proof or any difference
produces `format-fix-verification-failed`; affected files retain their original
contents. A cycle or the 128-pass work limit also fails without publishing edits.
Accepted files are replaced atomically, preserving their permissions and newline
style.

## Semantic decisions

| Rule | Decision | Reason |
| --- | --- | --- |
| SQBRSQL001 NULL comparison | Refused | Replacing `= NULL` with `IS NULL` changes SQL three-valued logic. |
| SQBRSQL002 implicit cartesian join | Apply eligible native edit | A comma-separated product becomes an explicit CROSS JOIN; the native engine excludes mixed join precedence. |
| SQBRSQL003 conditionless join | Apply eligible native edit in Snowflake | Snowflake defines an unqualified JOIN without ON/USING as a cartesian product. Outer, natural and other specialized joins are excluded. Other dialects are refused because the original syntax may be invalid. |
| SQBRSQL005 unused CTE | Apply eligible native edit | Unreachable SELECT CTEs do not contribute rows. The native engine excludes mutation statements and comments; dependency or lineage changes fail verification. |
| SQBRSQL006 redundant DISTINCT | Apply eligible native edit | The native engine proves projected expressions and grouping expressions coincide. |
| SQBRSQL008 bare UNION | Apply eligible native edit | UNION DISTINCT explicitly preserves the existing duplicate elimination, only in supported dialects. |
| SQBRSQL013 parenthesized DISTINCT | Refused | Removing parentheses can change operator precedence without changing output types or lineage; the native edit does not carry a precedence proof. |
| SQBRSQL030 boolean CASE simplification | Refused | The proposed COALESCE boolean rewrite is not proven portable to all supported dialects. |

Edits intersecting macro or intrinsic expansions, including equal-length
expansions inside otherwise authored boundaries, are refused. Non-model bodies
are reported as refused because model recompilation cannot prove their output
contract. Findings without a proposed safe edit are reported as unavailable.

Human output lists each applied, refused and unavailable fix and its reason.
JSON output includes a `rule_fixes` array with `file`, `line`, `code`, `status` and
`reason`. In check mode, `applied` describes the verified proposed edit. Progress
goes to stderr. Refused or unavailable fixes still require manual remediation;
they are not evidence that the Rule passed.
