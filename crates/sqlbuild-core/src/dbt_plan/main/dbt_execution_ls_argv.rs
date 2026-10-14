//! The `dbt ls` command that counts what a dbt execution selects.

use crate::dbt_plan::constants::LS_EXCLUDED_FLAGS;

/// `<dbt> ls --output json` with the execution's arguments except flags `ls` rejects.
#[must_use]
pub fn dbt_execution_ls_argv(argv: &[String]) -> Option<Vec<String>> {
    let [executable, _command, args @ ..] = argv else {
        return None;
    };
    let mut converted: Vec<String> = vec![
        executable.clone(),
        "ls".to_owned(),
        "--output".to_owned(),
        "json".to_owned(),
    ];
    converted.extend(
        args.iter()
            .filter(|arg| !LS_EXCLUDED_FLAGS.contains(&arg.as_str()))
            .cloned(),
    );
    Some(converted)
}
