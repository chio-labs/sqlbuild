use crate::dispatch::models::{CommandFacts, Dispatch, DispatchFailure, Route};

/// Facts of `command` and `subcommand` with every flag off and every required value present.
pub(super) fn facts(command: &str, subcommand: Option<&str>) -> CommandFacts {
    CommandFacts {
        command: Some(command.to_owned()),
        subcommand: subcommand.map(str::to_owned),
        refactor_target: true,
        from_target: true,
        contract_ready: true,
        ..CommandFacts::default()
    }
}

/// The dispatch that runs `route` with no pending failure.
pub(super) fn runs(route: &'static Route) -> Dispatch {
    Dispatch::Run(route, None)
}

/// A user failure with `message`, `code` and no help.
pub(super) fn failure(message: &str, code: &'static str) -> DispatchFailure {
    DispatchFailure {
        message: message.to_owned(),
        code,
        help: None,
    }
}
