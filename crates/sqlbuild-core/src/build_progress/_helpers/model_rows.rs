//! The rows nested under a finished model row.

use crate::build_progress::_helpers::audits::{AuditDisplayEntry, aggregate_audit_results};
use crate::build_progress::_helpers::rows::{TopLevelRow, log_block, sql_block, top_level_line};
use crate::build_progress::_helpers::text::{
    abbreviated_rows, audit_outcome_display, counter_text, execution_status_display,
    format_duration, pad, skip_detail, test_outcome_display, truncate_name,
};
use crate::build_progress::constants::{
    BATCH_INDENT, FAILED, HOOK_MAX_LABEL_WIDTH, HOOK_MIN_LABEL_WIDTH, HOOK_PHASE_WIDTH,
    HOOK_TYPE_WIDTH, PASS, SKIPPED, TYPE_WIDTH,
};
use crate::build_progress::models::{
    HookResultText, LifecycleEventText, ModelResultText, ModelRowFacts, ProgressLayout,
    TestResultText,
};
use crate::cli_text::models::CliStyle;
use crate::plan_display::main::format_no_input_rows::format_no_input_rows;
use crate::plan_display::main::format_waiting_on_empty_inputs::format_waiting_on_empty_inputs;
use crate::progress::main::format_expectation_name::format_expectation_name;

/// The indent and name width of rows nested under the model row.
pub(crate) struct SubRows {
    pub(crate) pad: String,
    pub(crate) name_width: usize,
    pub(crate) style: CliStyle,
}

pub(crate) fn streaming_batch_summary(model: &ModelResultText) -> Option<String> {
    let batch_count: i64 = model.batch_count?;
    let label: &str = if batch_count == 1 { "batch" } else { "batches" };
    let mut count_text: String = format!("{batch_count} {label}");
    if let Some(size) = &model.batch_size {
        count_text = format!("{count_text} ({size})");
    }
    let mut parts: Vec<String> = vec![count_text];
    if let Some((start, end)) = &model.cursor_range
        && model.empty_cursor_inputs.is_empty()
    {
        parts.push(format!("range {start} \u{2192} {end}"));
    }
    if let Some(rows) = model.rows_affected {
        parts.push(abbreviated_rows(rows));
    }
    if !model.empty_cursor_inputs.is_empty() && !model.waiting_on_empty_inputs {
        parts.push(format_no_input_rows(&model.empty_cursor_inputs));
    }
    if model.recovery_batch_count != 0 {
        parts.push(format!("{} recovery", model.recovery_batch_count));
    }
    if model.synthetic_completion_count != 0 {
        parts.push(format!(
            "{} synthetic coverage",
            model.synthetic_completion_count
        ));
    }
    if let Some(state) = &model.replay_requirement_state {
        parts.push(format!("replay {state}"));
    }
    Some(format!("{BATCH_INDENT}{}", parts.join("    ")))
}

pub(crate) fn empty_cursor_inputs(model: &ModelResultText) -> Option<String> {
    if model.empty_cursor_inputs.is_empty() || model.waiting_on_empty_inputs {
        return None;
    }
    Some(format!(
        "{BATCH_INDENT}{}",
        format_no_input_rows(&model.empty_cursor_inputs)
    ))
}

fn hook_label_width(hooks: &[HookResultText]) -> usize {
    let Some(longest) = hooks.iter().map(|hook| hook.label.chars().count()).max() else {
        return HOOK_MIN_LABEL_WIDTH;
    };
    HOOK_MIN_LABEL_WIDTH.max(longest.min(HOOK_MAX_LABEL_WIDTH))
}

pub(crate) fn hook_rows(hooks: &[HookResultText], pre_hook: bool, sub: &SubRows) -> String {
    let width: usize = hook_label_width(hooks);
    let label: &str = if pre_hook { "pre_hook" } else { "post_hook" };
    let mut text: String = String::new();
    for hook in hooks.iter().filter(|hook| hook.pre_hook == pre_hook) {
        let detail: String = if hook.status == SKIPPED {
            skip_detail(&hook.skip)
        } else {
            String::new()
        };
        text.push_str(&format!(
            "{}{}{}{} {}{detail}\n",
            sub.pad,
            sub.style.muted(&pad(label, HOOK_PHASE_WIDTH)),
            sub.style.muted(&pad(&hook.hook_type, HOOK_TYPE_WIDTH)),
            pad(&truncate_name(&hook.label, width), width),
            sub.style.status(&execution_status_display(&hook.status))
        ));
    }
    text
}

pub(crate) fn test_rows(tests: &[TestResultText], sub: &SubRows) -> String {
    let style: CliStyle = sub.style;
    let mut text: String = String::new();
    for test in tests {
        text.push_str(&format!(
            "{}{}{} {}\n",
            sub.pad,
            style.muted(&pad("test", TYPE_WIDTH)),
            pad(&test.label, sub.name_width),
            style.status(test_outcome_display(&test.outcome))
        ));
        for step in &test.steps {
            text.push_str(&format!(
                "{}  {}{} {}{}\n",
                sub.pad,
                style.muted(&pad("expect", TYPE_WIDTH - 2)),
                pad(&format_expectation_name(&step.model_name), sub.name_width),
                style.status(test_outcome_display(&step.outcome)),
                step.detail
            ));
        }
    }
    text
}

pub(crate) fn audit_row(entry: &AuditDisplayEntry, sub: &SubRows) -> String {
    let mut detail: String = String::new();
    if entry.reused {
        detail = "  proof reused".to_owned();
    }
    if entry.outcome != PASS && entry.total_row_count > 0 {
        let label: &str = if entry.total_row_count == 1 {
            "row"
        } else {
            "rows"
        };
        detail = format!("  {} {label}", entry.total_row_count);
    }
    if entry.batch_total > 1 {
        detail = format!("  {}/{}{detail}", entry.batch_pass, entry.batch_total);
    }
    format!(
        "{}{}{} {}{detail}\n",
        sub.pad,
        sub.style.muted(&pad(entry.label, TYPE_WIDTH)),
        pad(
            &truncate_name(&entry.display_name, sub.name_width),
            sub.name_width
        ),
        sub.style.status(&audit_outcome_display(entry.outcome))
    )
}

/// The model row itself, with its annotation, phase or skip detail.
pub(crate) fn model_line(
    (model, facts): (&ModelResultText, &ModelRowFacts),
    counter: usize,
    layout: ProgressLayout,
    style: CliStyle,
) -> String {
    let mut name: String = model.name.clone();
    if !facts.annotation.is_empty() {
        name = format!("{name}  ({})", facts.annotation);
    }
    let mut duration: String = format_duration(model.duration_ms);
    let mut detail: String = String::new();
    if model.status == FAILED
        && let Some(phase) = &model.failed_phase
    {
        detail = format!("  {phase}");
    } else if model.status == SKIPPED {
        duration = String::new();
        detail = skip_detail(&model.skip);
    }
    top_level_line(
        &TopLevelRow {
            counter: &counter_text(counter, layout.total),
            resource_type: &facts.display_type,
            name: &truncate_name(&name, layout.name_width),
            status: &execution_status_display(&model.status),
            duration: &duration,
            detail: &detail,
        },
        layout,
        style,
    )
}

/// Lifecycle SQL and log blocks, falling back to the planned DDL.
pub(crate) fn verbose_blocks(
    model: &ModelResultText,
    facts: &ModelRowFacts,
    style: CliStyle,
) -> String {
    let fallback: Vec<LifecycleEventText> = facts
        .logical_ddl
        .iter()
        .map(|ddl| LifecycleEventText::Sql(ddl.clone()))
        .collect();
    let events: &[LifecycleEventText] = if model.events.is_empty() {
        &fallback
    } else {
        &model.events
    };
    events
        .iter()
        .map(|event| match event {
            LifecycleEventText::Sql(sql) => sql_block(sql, style),
            LifecycleEventText::Log(message) => log_block(message, style),
        })
        .collect()
}

/// The batch summary or empty-input note, and the waiting-on-empty-inputs warning.
pub(crate) fn batch_lines(model: &ModelResultText, style: CliStyle) -> String {
    let mut text: String = String::new();
    if let Some(line) = streaming_batch_summary(model).or_else(|| empty_cursor_inputs(model)) {
        text.push_str(&format!("{}\n", style.muted(&line)));
    }
    if model.waiting_on_empty_inputs && !model.empty_cursor_inputs.is_empty() {
        let line: String = format!(
            "{BATCH_INDENT}{}",
            format_waiting_on_empty_inputs(&model.empty_cursor_inputs)
        );
        text.push_str(&format!("{}\n", style.warning(&line)));
    }
    text
}

/// Pre-hooks, tests, audits with their verbose SQL, then post-hooks.
pub(crate) fn nested_rows(
    model: &ModelResultText,
    tests: &[TestResultText],
    sub: &SubRows,
    verbose: bool,
) -> String {
    let mut text: String = hook_rows(&model.hooks, true, sub);
    text.push_str(&test_rows(tests, sub));
    for entry in aggregate_audit_results(&model.audits) {
        text.push_str(&audit_row(&entry, sub));
        if verbose && let Some(sql) = &entry.executed_sql {
            text.push_str(&sql_block(sql, sub.style));
        }
    }
    text.push_str(&hook_rows(&model.hooks, false, sub));
    text
}
