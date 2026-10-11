//! Why an effective configuration cannot be resolved.

/// A precedence failure, carrying the authored name it is about.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum EffectiveConfigError<K> {
    /// The selected target is defined in neither config file.
    UnknownTarget(K),
    /// A target selects a connection defined in neither config file.
    UnknownConnection(K),
    /// A target selects no connection while several named connections exist.
    AmbiguousConnection { target: K, names: Vec<K> },
}

/// One piece of a failure message: fixed text or an authored name, kept exact.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MessagePart<'a, K> {
    Text(&'static str),
    Name(&'a K),
}

impl<K> EffectiveConfigError<K> {
    /// The pieces of the message Python's `SpecConfigError` or `CompileInputError` carries.
    pub fn message_parts(&self) -> Vec<MessagePart<'_, K>> {
        use MessagePart::{Name, Text};
        match self {
            Self::UnknownTarget(name) => vec![Text("Unknown target '"), Name(name), Text("'")],
            Self::UnknownConnection(name) => vec![
                Text("Unknown connection '"),
                Name(name),
                Text("' selected by target. Define [connections."),
                Name(name),
                Text("] in sqlbuild_project.toml or sqlbuild_local.toml."),
            ],
            Self::AmbiguousConnection { target, names } => {
                let mut parts = vec![
                    Text("targets."),
                    Name(target),
                    Text(" does not set connection and several named connections are defined ("),
                ];
                for (position, name) in names.iter().enumerate() {
                    if position > 0 {
                        parts.push(Text(", "));
                    }
                    parts.push(Name(name));
                }
                parts.extend([
                    Text("); set connection = \"<name>\" on [targets."),
                    Name(target),
                    Text("] in sqlbuild_project.toml or sqlbuild_local.toml"),
                ]);
                parts
            }
        }
    }
}

impl<K: AsRef<str>> EffectiveConfigError<K> {
    /// The message text, for names that are valid text.
    pub fn message(&self) -> String {
        self.message_parts()
            .into_iter()
            .map(|part| match part {
                MessagePart::Text(text) => text,
                MessagePart::Name(name) => name.as_ref(),
            })
            .collect()
    }
}
