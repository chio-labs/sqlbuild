//! The characters header string scanning reads, as bytes or as characters.

/// One unit of header text: a UTF-8 byte or a character. Every delimiter is ASCII.
pub trait HeaderChar: Copy + PartialEq {
    fn ascii(byte: u8) -> Self;
}

impl HeaderChar for u8 {
    fn ascii(byte: u8) -> Self {
        byte
    }
}

impl HeaderChar for char {
    fn ascii(byte: u8) -> Self {
        char::from(byte)
    }
}
