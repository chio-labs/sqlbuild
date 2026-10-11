//! The `ENV:` names target templates read, as `re.findall(r"ENV:([^\s(),'\"}]+)")` finds them.

use sqlbuild_core::text::main::is_python_space::is_python_space;

use crate::assembly::project::constants::{ENVIRONMENT_NAME_TERMINATORS, ENVIRONMENT_READ_PREFIX};

/// Every distinct `ENV:` name across `values`, in first-seen order.
pub fn environment_template_names(values: &[Option<String>]) -> Vec<String> {
    let mut names: Vec<String> = Vec::new();
    for value in values.iter().flatten() {
        let mut position = 0;
        while let Some(found) = value[position..].find(ENVIRONMENT_READ_PREFIX) {
            let start = position + found + ENVIRONMENT_READ_PREFIX.len();
            let length: usize = value[start..]
                .chars()
                .take_while(|character| {
                    !is_python_space(*character)
                        && !ENVIRONMENT_NAME_TERMINATORS.contains(character)
                })
                .map(char::len_utf8)
                .sum();
            if length == 0 {
                position += found + 1;
                continue;
            }
            let name = &value[start..start + length];
            if !names.iter().any(|existing| existing == name) {
                names.push(name.to_owned());
            }
            position = start + length;
        }
    }
    names
}
