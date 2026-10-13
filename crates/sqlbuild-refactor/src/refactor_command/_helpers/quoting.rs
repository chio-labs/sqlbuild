//! Command lines quoted for the shell of the platform they are printed on.

/// Python's `shlex.quote`.
fn shell_quote(text: &str) -> String {
    if text.is_empty() {
        return "''".to_owned();
    }
    let safe: bool = text
        .chars()
        .all(|character| character.is_ascii_alphanumeric() || "_@%+=:,./-".contains(character));
    if safe {
        return text.to_owned();
    }
    format!("'{}'", text.replace('\'', "'\"'\"'"))
}

/// Python's `subprocess.list2cmdline` for one argument.
fn windows_quote(argument: &str) -> String {
    let mut quoted: String = String::new();
    let needs_quotes: bool = argument.is_empty() || argument.contains([' ', '\t']);
    if needs_quotes {
        quoted.push('"');
    }
    let mut backslashes: usize = 0;
    for character in argument.chars() {
        match character {
            '\\' => backslashes += 1,
            '"' => {
                quoted.push_str(&"\\".repeat(backslashes * 2));
                backslashes = 0;
                quoted.push_str("\\\"");
            }
            _ => {
                quoted.push_str(&"\\".repeat(backslashes));
                backslashes = 0;
                quoted.push(character);
            }
        }
    }
    quoted.push_str(&"\\".repeat(backslashes));
    if needs_quotes {
        quoted.push_str(&"\\".repeat(backslashes));
        quoted.push('"');
    }
    quoted
}

/// `shlex.join`, or `subprocess.list2cmdline` on Windows.
pub(crate) fn command_line(arguments: &[String], windows: bool) -> String {
    arguments
        .iter()
        .map(|argument| {
            if windows {
                windows_quote(argument)
            } else {
                shell_quote(argument)
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}
