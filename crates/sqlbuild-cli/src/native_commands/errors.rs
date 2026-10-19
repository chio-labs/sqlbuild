//! Why `sqb` hands an invocation to Python after all.

/// What made the invocation need Python, found before any side effect.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PythonNeeded {
    /// The arguments are not text, or a converter or terminal fact needs the interpreter.
    Arguments,
    /// The command, or an option such as `--debug`, runs in Python.
    Command,
    /// The installed package, home directory or working directory is not known natively.
    Installation,
    /// The project holds Python the command imports, or files Python reports on.
    Project,
    /// The command failed before any side effect, and Python reports the failure.
    Failure,
}
