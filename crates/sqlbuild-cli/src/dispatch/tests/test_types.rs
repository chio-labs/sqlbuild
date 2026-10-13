use crate::dispatch::models::{CommandFacts, Dispatch, InvocationPolicy};

pub(super) struct CommandDispatchTestCase {
    pub(super) description: &'static str,
    pub(super) facts: CommandFacts,
    pub(super) expected_dispatch: Dispatch,
}

pub(super) struct InvocationPolicyTestCase {
    pub(super) description: &'static str,
    pub(super) facts: CommandFacts,
    pub(super) expected_policy: InvocationPolicy,
}
