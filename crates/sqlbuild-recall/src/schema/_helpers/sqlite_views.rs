//! The bodies of the supported views in SQLite.

use crate::schema::constants::OUTPUT_TAIL_RECORDS;

/// The current time as stored timestamps spell it.
const NOW: &str = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')";

const STATEMENTS: &str = "WITH facts AS (
    SELECT *
    FROM recall_events
    WHERE statement_id IS NOT NULL AND event_type LIKE 'statement!_%' ESCAPE '!'
),
firsts AS (
    SELECT invocation_id, statement_id, run_id, resource_id, resource_attempt_id, operation_id,
        intent, statement_kind, purpose, sql_digest,
        ROW_NUMBER() OVER (
            PARTITION BY statement_id ORDER BY invocation_sequence, occurred_at, event_id
        ) AS position
    FROM facts
),
started AS (
    SELECT statement_id, MIN(occurred_at) AS started_at
    FROM facts WHERE event_type = 'statement_started' GROUP BY statement_id
),
submitted AS (
    SELECT statement_id, MIN(occurred_at) AS submitted_at
    FROM facts WHERE event_type = 'statement_submitted' GROUP BY statement_id
),
query_ids AS (
    SELECT statement_id, MAX(query_id) AS query_id FROM facts GROUP BY statement_id
),
terminals AS (
    SELECT statement_id, event_type, occurred_at, query_id, error_type, error_code, duration_ms,
        row_count, affected_rows,
        ROW_NUMBER() OVER (
            PARTITION BY statement_id
            ORDER BY invocation_sequence DESC, occurred_at DESC, event_id DESC
        ) AS position
    FROM facts
    WHERE event_type IN ('statement_completed', 'statement_failed')
),
resources AS (
    SELECT invocation_id, resource_id, MIN(resource_name) AS resource_name,
        MIN(resource_kind) AS resource_kind
    FROM recall_events
    WHERE resource_id IS NOT NULL AND resource_name IS NOT NULL
    GROUP BY invocation_id, resource_id
)
SELECT
    firsts.invocation_id,
    firsts.statement_id,
    firsts.run_id,
    firsts.resource_id,
    resources.resource_name,
    resources.resource_kind,
    firsts.resource_attempt_id,
    firsts.operation_id,
    firsts.intent,
    firsts.statement_kind,
    firsts.purpose,
    COALESCE(terminals.query_id, query_ids.query_id) AS query_id,
    started.started_at,
    submitted.submitted_at,
    terminals.occurred_at AS ended_at,
    CASE terminals.event_type
        WHEN 'statement_completed' THEN 'completed'
        WHEN 'statement_failed' THEN 'failed'
        ELSE 'no_terminal'
    END AS outcome,
    terminals.error_type,
    terminals.error_code,
    terminals.duration_ms,
    terminals.row_count,
    terminals.affected_rows,
    firsts.sql_digest,
    EXISTS (
        SELECT 1 FROM recall_artifacts AS artifact
        WHERE artifact.digest = 'sha256:' || firsts.sql_digest
    ) AS sql_available
FROM firsts
LEFT JOIN started ON started.statement_id = firsts.statement_id
LEFT JOIN submitted ON submitted.statement_id = firsts.statement_id
LEFT JOIN query_ids ON query_ids.statement_id = firsts.statement_id
LEFT JOIN terminals
    ON terminals.statement_id = firsts.statement_id AND terminals.position = 1
LEFT JOIN resources
    ON resources.invocation_id = firsts.invocation_id
    AND resources.resource_id = firsts.resource_id
WHERE firsts.position = 1";

const AUDIT_RESULTS: &str = "SELECT
    invocation_id,
    invocation_started_at,
    event_id,
    occurred_at,
    run_id,
    resource_id,
    resource_attempt_id,
    json_extract(payload, '$.audit_name') AS audit_name,
    json_extract(payload, '$.audit_definition_name') AS audit_definition_name,
    CASE WHEN json_extract(payload, '$.target_name') IS NULL THEN NULL ELSE
        COALESCE(json_extract(payload, '$.target_database') || '.', '')
        || COALESCE(json_extract(payload, '$.target_schema') || '.', '')
        || json_extract(payload, '$.target_name')
    END AS target_relation,
    json_extract(payload, '$.attached_target_kind') AS attached_target_kind,
    json_extract(payload, '$.attached_target_name') AS attached_target_name,
    json_extract(payload, '$.attached_column_name') AS \"column\",
    outcome,
    json_extract(payload, '$.severity') AS severity,
    json_extract(payload, '$.violation_count') AS violation_count,
    json_extract(payload, '$.measured_value') AS measured_value,
    json_extract(payload, '$.evaluation_mode') AS evaluation_mode,
    json_extract(payload, '$.execution_error') AS execution_error,
    sql_digest,
    json_extract(payload, '$.sample_digest') AS sample_digest
FROM recall_events
WHERE event_type = 'audit_completed'";

const OUTPUT_INVOCATIONS: &str = "WITH received AS (
    SELECT invocation_id,
        MIN(invocation_started_at) AS invocation_started_at,
        COUNT(*) AS chunks,
        SUM(byte_count) AS bytes,
        SUM(CASE WHEN stream = 'stdout' THEN byte_count ELSE 0 END) AS stdout_bytes,
        SUM(CASE WHEN stream = 'stderr' THEN byte_count ELSE 0 END) AS stderr_bytes,
        MAX(sequence) AS max_sequence,
        SUM(dropped_before) AS queue_drops,
        SUM(COALESCE(omitted_sequences, 1)) AS spans,
        SUM(COALESCE(omitted_bytes, 0)) AS truncated_bytes
    FROM recall_output
    GROUP BY invocation_id
),
delivery AS (
    SELECT * FROM recall_delivery WHERE stream = 'output'
),
ids AS (
    SELECT invocation_id, invocation_started_at FROM received
    UNION SELECT invocation_id, invocation_started_at FROM delivery
),
counted AS (
    SELECT
        ids.invocation_id,
        ids.invocation_started_at,
        COALESCE(received.chunks, 0) AS chunks,
        COALESCE(received.bytes, 0) AS bytes,
        COALESCE(received.stdout_bytes, 0) AS stdout_bytes,
        COALESCE(received.stderr_bytes, 0) AS stderr_bytes,
        COALESCE(received.truncated_bytes, 0) AS truncated_bytes,
        received.max_sequence,
        MAX(
            COALESCE(received.max_sequence + 1 - received.spans, 0),
            COALESCE(delivery.accepted, 0) - COALESCE(received.chunks, 0)
        ) AS missing_sequences,
        MAX(COALESCE(received.queue_drops, 0), COALESCE(delivery.dropped, 0)) AS reported_drops,
        COALESCE(delivery.filtered, 0) AS filtered,
        COALESCE(delivery.failed, 0) AS failed,
        COALESCE(context.recall_filter_active, 0) AS filter_active,
        COALESCE(delivery.flush_complete, 0) AS flush_complete,
        delivery.invocation_id IS NOT NULL AS delivery_reported,
        COALESCE(delivery.delivered, 0) AS delivered
    FROM ids
    LEFT JOIN received ON received.invocation_id = ids.invocation_id
    LEFT JOIN delivery ON delivery.invocation_id = ids.invocation_id
    LEFT JOIN recall_invocations AS context ON context.invocation_id = ids.invocation_id
)
SELECT
    invocation_id,
    invocation_started_at,
    chunks,
    bytes,
    stdout_bytes,
    stderr_bytes,
    truncated_bytes,
    max_sequence,
    missing_sequences,
    reported_drops,
    filtered,
    failed,
    filter_active,
    flush_complete,
    CASE
        WHEN missing_sequences = 0 AND truncated_bytes > 0 THEN 'truncated'
        WHEN missing_sequences = 0 THEN NULL
        WHEN filtered >= missing_sequences THEN 'filtered'
        WHEN filtered + reported_drops + failed >= missing_sequences THEN 'dropped'
        ELSE 'unexplained'
    END AS gap_reason,
    CASE
        WHEN delivery_reported AND flush_complete = 1 AND missing_sequences = 0
            AND reported_drops = 0 AND filtered = 0 AND failed = 0 AND truncated_bytes = 0
            AND chunks >= delivered
        THEN 1 ELSE 0
    END AS complete
FROM counted";

const OUTPUT_TRANSCRIPTS: &str = "SELECT
    invocation_id,
    MIN(invocation_started_at) AS invocation_started_at,
    CAST(COALESCE(
        group_concat(CASE WHEN stream = 'stdout' THEN data END, x'' ORDER BY sequence), x''
    ) AS BLOB) AS stdout,
    CAST(COALESCE(
        group_concat(CASE WHEN stream = 'stderr' THEN data END, x'' ORDER BY sequence), x''
    ) AS BLOB) AS stderr,
    CAST(COALESCE(group_concat(data, x'' ORDER BY sequence), x'') AS BLOB) AS combined
FROM recall_output
GROUP BY invocation_id";

const EVENTS: &str = "SELECT * FROM recall_events";

const DIAGNOSTICS: &str = "SELECT * FROM recall_diagnostics";

const ARTIFACTS: &str = "SELECT
    refs.invocation_id,
    refs.invocation_started_at,
    refs.digest,
    refs.ref_id,
    refs.role,
    refs.statement_id,
    refs.resource_id,
    artifact.kind,
    artifact.media_type,
    artifact.size,
    artifact.digest IS NOT NULL AS available,
    CASE WHEN artifact.digest IS NULL THEN 'expired_or_not_captured' END AS unavailable_reason,
    CASE WHEN artifact.media_type LIKE 'text/%' THEN CAST(artifact.content AS TEXT) END AS text,
    artifact.content
FROM recall_artifact_refs AS refs
LEFT JOIN recall_artifacts AS artifact ON artifact.digest = refs.digest";

const CONFLICTS: &str = "SELECT * FROM recall_conflicts";

fn invocations() -> String {
    format!(
        "WITH ids AS (
    SELECT invocation_id, MIN(invocation_started_at) AS invocation_started_at
    FROM (
        SELECT invocation_id, invocation_started_at FROM recall_invocations
        UNION ALL SELECT invocation_id, invocation_started_at FROM recall_heartbeats
        UNION ALL SELECT invocation_id, invocation_started_at FROM recall_events
            WHERE event_type IN ('invocation_started', 'invocation_completed', 'invocation_failed')
    )
    GROUP BY invocation_id
),
started AS (
    SELECT invocation_id, MIN(occurred_at) AS started_at, MIN(command) AS command
    FROM recall_events
    WHERE event_type = 'invocation_started'
    GROUP BY invocation_id
),
terminals AS (
    SELECT invocation_id, event_type, occurred_at, exit_code, duration_ms, error_type, error_code,
        ROW_NUMBER() OVER (
            PARTITION BY invocation_id
            ORDER BY invocation_sequence DESC, occurred_at DESC, event_id DESC
        ) AS position
    FROM recall_events
    WHERE event_type IN ('invocation_completed', 'invocation_failed')
),
beats AS (
    SELECT invocation_id, MAX(beat_at) AS last_heartbeat_at, MAX(stale_at) AS stale_at,
        MIN(command) AS command, MIN(subcommand) AS subcommand
    FROM recall_heartbeats
    GROUP BY invocation_id
),
projected AS (
    SELECT
        ids.invocation_id,
        ids.invocation_started_at,
        COALESCE(started.started_at, ids.invocation_started_at) AS started_at,
        CASE
            WHEN terminals.event_type = 'invocation_completed' THEN 'completed'
            WHEN terminals.event_type = 'invocation_failed' THEN 'failed'
            WHEN beats.stale_at IS NULL THEN 'unknown'
            WHEN beats.stale_at >= {NOW} THEN 'running'
            ELSE 'abandoned'
        END AS status,
        terminals.event_type AS terminal_event,
        terminals.occurred_at AS terminal_at,
        terminals.duration_ms AS terminal_duration_ms,
        terminals.exit_code,
        terminals.error_type,
        terminals.error_code,
        COALESCE(context.command, started.command, beats.command) AS command,
        COALESCE(context.subcommand, beats.subcommand) AS subcommand,
        context.target,
        context.adapter,
        context.project_name,
        context.selection,
        context.exclusion,
        context.sqlbuild_version,
        context.git_revision,
        context.git_dirty,
        context.host_token,
        context.pid,
        context.external_context,
        context.recall_filter_active,
        beats.last_heartbeat_at
    FROM ids
    LEFT JOIN recall_invocations AS context ON context.invocation_id = ids.invocation_id
    LEFT JOIN started ON started.invocation_id = ids.invocation_id
    LEFT JOIN terminals
        ON terminals.invocation_id = ids.invocation_id AND terminals.position = 1
    LEFT JOIN beats ON beats.invocation_id = ids.invocation_id
)
SELECT
    invocation_id,
    invocation_started_at,
    started_at,
    status,
    CASE
        WHEN terminal_event IS NOT NULL THEN terminal_at
        WHEN status = 'abandoned' THEN last_heartbeat_at
    END AS ended_at,
    CASE
        WHEN terminal_event IS NOT NULL THEN terminal_duration_ms
        WHEN status = 'abandoned' THEN ROUND(
            (unixepoch(last_heartbeat_at, 'subsec') - unixepoch(started_at, 'subsec')) * 1000.0, 3
        )
    END AS duration_ms,
    exit_code,
    error_type,
    error_code,
    command,
    subcommand,
    target,
    adapter,
    project_name,
    selection,
    exclusion,
    sqlbuild_version,
    git_revision,
    git_dirty,
    host_token,
    pid,
    external_context,
    recall_filter_active,
    last_heartbeat_at
FROM projected"
    )
}

fn output_tail() -> String {
    format!(
        "SELECT invocation_id, invocation_started_at, sequence, stream, occurred_at, byte_count,
    CAST(data AS TEXT) AS text
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY invocation_id ORDER BY sequence DESC) AS position
    FROM recall_output
)
WHERE position <= {OUTPUT_TAIL_RECORDS}"
    )
}

/// Each supported view's name and SQLite body, in creation order.
pub(crate) fn sqlite_view_bodies() -> Vec<(&'static str, String)> {
    vec![
        ("invocations", invocations()),
        ("statements", STATEMENTS.to_owned()),
        ("audit_results", AUDIT_RESULTS.to_owned()),
        ("output_invocations", OUTPUT_INVOCATIONS.to_owned()),
        ("output_tail", output_tail()),
        ("output_transcripts", OUTPUT_TRANSCRIPTS.to_owned()),
        ("events", EVENTS.to_owned()),
        ("diagnostics", DIAGNOSTICS.to_owned()),
        ("artifacts", ARTIFACTS.to_owned()),
        ("conflicts", CONFLICTS.to_owned()),
    ]
}
