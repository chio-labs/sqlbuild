# Unevaluated Rules

`sqb rules run` and compiler-integrated Rules report `rules-unevaluated` when a
selected Rule cannot evaluate a resource. The finding identifies the resource,
affected Rule and reason: parser rejection, parser complexity limit, unsupported
opaque syntax, or a native evaluation failure. SQL-test fixtures and audit SQL
are included. Missing evaluation evidence is not a passing result.

Unevaluated findings fail the command and appear in JSON diagnostics. Rules JSON
also includes `unevaluated_resources`, counting distinct resource paths. A model
with any unsuppressed unevaluated finding is excluded from `evaluated_models`.
The human summary reports both counts. Cached results preserve the failure.

One resource/cause produces one fault, even when multiple selected Rules depend
on that analysis. Its `affected_rules` JSON list contains the unsuppressed Rule
codes. The human output lists those codes alongside the shared reason. Different
causes on the same resource remain distinct faults without inflating the count
of unevaluated resources.

Explicit Rule ignores and exceptions apply to the affected Rule's original code,
before the public `rules-unevaluated` diagnostic is produced. Model SQL analysis
can be disabled with `MODEL (sql_analysis false)` or the corresponding path
default. These are explicit policy choices; parser failures never create implicit
ignores.
