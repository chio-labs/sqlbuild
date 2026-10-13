//! `inspect.cleandoc` as `ast.get_docstring` applies it.

const TAB_SIZE: usize = 8;

/// `doc.expandtabs()`: tabs to the next multiple of eight columns, restarting at each line break.
fn expand_tabs(doc: &str) -> String {
    let mut expanded: String = String::with_capacity(doc.len());
    let mut column: usize = 0;
    for character in doc.chars() {
        match character {
            '\t' => {
                let width: usize = TAB_SIZE - column % TAB_SIZE;
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

/// `inspect.cleandoc` of Python 3.13 and later, which strips only spaces from indentation.
pub(crate) fn clean_docstring(doc: &str) -> String {
    let expanded: String = expand_tabs(doc);
    let mut lines: Vec<String> = expanded.split('\n').map(str::to_owned).collect();
    let margin: Option<usize> = lines
        .iter()
        .skip(1)
        .filter_map(|line| {
            let content: usize = line.trim_start_matches(' ').chars().count();
            (content > 0).then(|| line.chars().count() - content)
        })
        .min();
    if let Some(first) = lines.first_mut() {
        *first = first.trim_start_matches(' ').to_owned();
    }
    if let Some(margin) = margin {
        for line in lines.iter_mut().skip(1) {
            *line = line.chars().skip(margin).collect();
        }
    }
    while lines.last().is_some_and(String::is_empty) {
        lines.pop();
    }
    let leading: usize = lines.iter().take_while(|line| line.is_empty()).count();
    lines.drain(..leading);
    lines.join("\n")
}
