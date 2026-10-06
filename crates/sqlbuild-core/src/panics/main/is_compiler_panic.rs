use crate::constants::PANIC_MESSAGE;

pub fn is_compiler_panic(message: &str) -> bool {
    message == PANIC_MESSAGE
}
