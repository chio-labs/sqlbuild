//! The interpreter a Python console script starts, read from its `#!` line or shell trampoline.

use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};

use crate::host::constants::{
    RELOCATABLE_DIRECTORY, SCRIPT_HEAD_BYTES, SHELL_SHEBANG, TRAMPOLINE_PREFIX, TRAMPOLINE_SUFFIX,
};

fn script_head(script: &Path) -> Result<String, String> {
    let mut head: Vec<u8> = Vec::new();
    File::open(script)
        .and_then(|file| file.take(SCRIPT_HEAD_BYTES).read_to_end(&mut head))
        .map_err(|error| format!("cannot read {}: {error}", script.display()))?;
    String::from_utf8(head).map_err(|_| format!("{} does not start with text", script.display()))
}

/// A shell word written as one plain, single-quoted or simple double-quoted token.
fn shell_word(token: &str) -> Option<&str> {
    let unquoted = if let Some(inner) = token
        .strip_prefix('\'')
        .and_then(|rest| rest.strip_suffix('\''))
    {
        (!inner.contains('\'')).then_some(inner)?
    } else if let Some(inner) = token
        .strip_prefix('"')
        .and_then(|rest| rest.strip_suffix('"'))
    {
        (!inner.contains(['"', '$', '`', '\\'])).then_some(inner)?
    } else {
        let plain = !token.contains(|character: char| {
            character.is_whitespace() || "'\"$`\\;&|<>(){}*?[]#~".contains(character)
        });
        plain.then_some(token)?
    };
    (!unquoted.is_empty()).then_some(unquoted)
}

/// The interpreter a `/bin/sh` trampoline's second line runs.
fn trampoline_interpreter(script: &Path, line: &str) -> Result<PathBuf, String> {
    let unrecognised = || {
        format!(
            "the shell trampoline in {} is not recognised",
            script.display()
        )
    };
    let command: &str = line
        .strip_prefix(TRAMPOLINE_PREFIX)
        .and_then(|rest| rest.strip_suffix(TRAMPOLINE_SUFFIX))
        .ok_or_else(unrecognised)?;
    if let Some(name) = command.strip_prefix(RELOCATABLE_DIRECTORY) {
        let name: &str = shell_word(name)
            .filter(|name| !name.contains('/'))
            .ok_or_else(unrecognised)?;
        let resolved: PathBuf = std::fs::canonicalize(script)
            .map_err(|error| format!("cannot resolve {}: {error}", script.display()))?;
        let directory: &Path = resolved.parent().ok_or_else(unrecognised)?;
        return Ok(directory.join(name));
    }
    let interpreter = PathBuf::from(shell_word(command).ok_or_else(unrecognised)?);
    if interpreter.is_absolute() {
        Ok(interpreter)
    } else {
        Err(unrecognised())
    }
}

/// The interpreter the console script at `script` runs, exactly as the kernel or shell starts it.
pub(crate) fn script_interpreter(script: &Path) -> Result<PathBuf, String> {
    let head: String = script_head(script)?;
    let mut lines = head.lines();
    let first: &str = lines.next().unwrap_or_default().trim_end();
    if first == SHELL_SHEBANG {
        return trampoline_interpreter(script, lines.next().unwrap_or_default().trim_end());
    }
    let Some(command) = first.strip_prefix("#!") else {
        return Err(format!("{} has no #! line", script.display()));
    };
    let command: &str = command.trim();
    if command.contains(char::is_whitespace) {
        return Err(format!(
            "the #! line of {} passes arguments to its interpreter",
            script.display()
        ));
    }
    let interpreter = PathBuf::from(command);
    if interpreter.is_absolute() {
        Ok(interpreter)
    } else {
        Err(format!(
            "the #! line of {} names a relative interpreter",
            script.display()
        ))
    }
}
