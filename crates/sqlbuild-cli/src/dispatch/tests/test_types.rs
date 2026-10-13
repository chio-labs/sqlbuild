use crate::dispatch::models::{CommandFacts, Dispatch};

pub(super) struct CommandDispatchTestCase {
    pub(super) description: &'static str,
    pub(super) facts: CommandFacts,
    pub(super) expected_dispatch: Dispatch,
}
