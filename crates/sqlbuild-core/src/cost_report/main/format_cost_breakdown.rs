//! The human breakdown of one run's cost, shared by build output and `sqb cost`.

use crate::cli_text::models::CliStyle;
use crate::cost_report::_helpers::breakdown::{rate_note, run_line, styled_status, trailer};
use crate::cost_report::_helpers::decimal_text::fixed;
use crate::cost_report::_helpers::tables::{resource_rows, usd};
use crate::cost_report::constants::{COMPLETE_STATUS, CREDIT_PLACES};
use crate::cost_report::models::{BreakdownOptions, CostRun};

/// `format_cost_breakdown`: totals, status, the resource table and the run's notes.
#[must_use]
pub fn format_cost_breakdown(run: &CostRun, options: BreakdownOptions) -> String {
    let style: CliStyle = CliStyle {
        use_color: options.use_color,
    };
    let cost = &run.cost;
    let heading: String = style.title("Cost");
    let status: String = styled_status(style, &cost.status);
    if cost.resources.is_empty() && cost.status != COMPLETE_STATUS {
        let mut lines: Vec<String> = vec![format!("{heading}  {status}")];
        lines.extend(run_line(style, run, options.show_run_id));
        lines.extend(
            cost.message
                .iter()
                .filter(|message| !message.is_empty())
                .map(|message| style.muted(message)),
        );
        lines.extend(
            cost.limitations
                .iter()
                .map(|limitation| style.warning(limitation)),
        );
        lines.push(style.muted(&format!(
            "Run `sqb cost {}` to inspect this run later.",
            run.run_id
        )));
        return lines.join("\n");
    }
    let mut lines: Vec<String> = vec![format!(
        "{heading}  {} estimated  |  {}  |  {}",
        style.value(&usd(&cost.estimated_usd)),
        style.value(&format!(
            "{} attributed credits",
            fixed(&cost.estimated_compute_credits, CREDIT_PLACES)
        )),
        rate_note(style, cost),
    )];
    if cost.status != COMPLETE_STATUS {
        lines.push(status);
    }
    lines.extend(run_line(style, run, options.show_run_id));
    let shown: usize = options.limit.map_or(cost.resources.len(), |limit| {
        limit.min(cost.resources.len())
    });
    if shown > 0 {
        lines.push(String::new());
        lines.extend(resource_rows(
            style,
            &cost.resources[..shown],
            cost,
            options.terminal_width,
        ));
    }
    lines.extend(trailer(style, run, options.limit));
    lines.join("\n")
}
