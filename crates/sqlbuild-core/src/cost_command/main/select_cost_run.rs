//! The persisted run a selector names.

use crate::cost_command::errors::CostCommandError;

/// The index of the exact run id, else of the one run id the selector prefixes.
pub fn select_cost_run(run_ids: &[String], selector: &str) -> Result<usize, CostCommandError> {
    if let Some(index) = run_ids.iter().position(|run_id| run_id == selector) {
        return Ok(index);
    }
    let matches: Vec<usize> = run_ids
        .iter()
        .enumerate()
        .filter(|(_, run_id)| run_id.starts_with(selector))
        .map(|(index, _)| index)
        .collect();
    match matches.as_slice() {
        [] => Err(CostCommandError::new(
            "C705",
            format!("No cost run matches '{selector}'"),
        )),
        [only] => Ok(*only),
        _ => Err(CostCommandError::new(
            "C706",
            format!(
                "Cost run prefix '{selector}' is ambiguous; matches: {}",
                matches
                    .iter()
                    .map(|index| run_ids[*index].as_str())
                    .collect::<Vec<&str>>()
                    .join(", ")
            ),
        )),
    }
}
