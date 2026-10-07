//! Line helpers behind the `inspect.cleandoc` port.

const TAB_SIZE: usize = 8;

/// `str.expandtabs()`: a tab advances to the next multiple of eight columns.
pub(crate) fn expand_tabs(text: &str) -> String {
    let mut expanded: String = String::with_capacity(text.len());
    let mut column: usize = 0;
    for character in text.chars() {
        match character {
            '\t' => {
                let width = TAB_SIZE - column % TAB_SIZE;
                expanded.extend(std::iter::repeat_n(' ', width));
                column += width;
            }
            '\n' | '\r' => {
                expanded.push(character);
                column = 0;
            }
            _ => {
                expanded.push(character);
                column += 1;
            }
        }
    }
    expanded
}

/// `line[count:]` in code points.
pub(crate) fn skip_chars(line: &str, count: usize) -> &str {
    line.char_indices()
        .nth(count)
        .map_or("", |(index, _)| &line[index..])
}
