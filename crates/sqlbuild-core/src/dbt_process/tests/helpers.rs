use crate::dbt_process::main::read_dbt_output_line::read_dbt_output_line;
use crate::dbt_process::models::DbtJsonProcess;

/// argv running `script` with `sh -c`.
pub(super) fn shell(script: &str) -> Vec<String> {
    vec!["sh".to_owned(), "-c".to_owned(), script.to_owned()]
}

/// Every line a streamed process writes, until it closes its output.
pub(super) fn collected_lines(process: &mut DbtJsonProcess) -> Vec<String> {
    std::iter::from_fn(|| read_dbt_output_line(&mut process.output).expect("readable")).collect()
}
