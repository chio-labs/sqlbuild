use crate::command_connection::errors::CommandConnectionError;

pub(super) fn message(result: Result<(), CommandConnectionError>) -> Option<String> {
    result.err().map(|error| error.message().to_owned())
}
