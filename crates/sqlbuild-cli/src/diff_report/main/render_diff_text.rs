//! The terminal diff summary.

use crate::diff_report::_helpers::findings::resolved_outcome;
use crate::diff_report::_helpers::layout::{Node, print_nodes};
use crate::diff_report::_helpers::numbers::grouped;
use crate::diff_report::_helpers::sections::{BOLD, MUTED, OBJECT, SectionContext, model_nodes};
use crate::diff_report::constants::{QUERY_INPUT_KIND, SUMMARY_WIDTH};
use crate::diff_report::models::{DiffDocumentOptions, DiffModelFacts, DiffTextOptions};

/// Render the summary panel, then every model's overview and sections.
#[must_use]
pub fn render_diff_text(
    models: &[DiffModelFacts],
    document: &DiffDocumentOptions,
    options: &DiffTextOptions,
) -> String {
    if models.is_empty() {
        return print_nodes(
            &[Node::plain("No models selected for diff.")],
            SUMMARY_WIDTH,
            options.use_color,
        );
    }
    let input_label: &str = if models
        .iter()
        .all(|model| model.input_kind == QUERY_INPUT_KIND)
    {
        "query pairs"
    } else {
        "models"
    };
    let mut nodes: Vec<Node> = vec![
        Node::Panel("SQLBuild Diff Summary".to_owned(), BOLD),
        Node::styled(
            format!("{} vs {}", document.from_label, document.to_label),
            OBJECT,
        ),
        Node::plain(format!(
            "selected {input_label}: {}",
            grouped(models.len() as i64)
        )),
        Node::plain(format!(
            "outcome: {}",
            resolved_outcome(models, document.outcome.as_deref())
        )),
        Node::plain(""),
    ];
    let context: SectionContext<'_> = SectionContext {
        from_label: &document.from_label,
        to_label: &document.to_label,
        text: options,
        examples: document.examples,
    };
    for (index, model) in models.iter().enumerate() {
        if index > 0 {
            nodes.push(Node::plain(""));
            nodes.push(Node::styled("─".repeat(SUMMARY_WIDTH), MUTED));
            nodes.push(Node::plain(""));
        }
        nodes.extend(model_nodes(model, &context));
    }
    print_nodes(&nodes, SUMMARY_WIDTH, options.use_color)
}
