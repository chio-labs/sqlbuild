//! Shell-style wildcard matching: `*`, `?` and `[...]` sets with `!` negation and ranges.

/// One pattern piece; every piece except `Star` matches exactly one character.
#[derive(Clone, Debug, PartialEq, Eq)]
enum Piece {
    Star,
    Any,
    Literal(char),
    Set {
        negated: bool,
        members: Vec<(char, char)>,
    },
}

impl Piece {
    fn matches(&self, character: char) -> bool {
        match self {
            Self::Star | Self::Any => true,
            Self::Literal(literal) => *literal == character,
            Self::Set { negated, members } => {
                members
                    .iter()
                    .any(|(low, high)| (*low..=*high).contains(&character))
                    != *negated
            }
        }
    }
}

/// The pieces of `pattern`, with consecutive stars collapsed.
fn pieces(pattern: &[char]) -> Vec<Piece> {
    let mut pieces: Vec<Piece> = Vec::new();
    let mut index: usize = 0;
    while index < pattern.len() {
        let character: char = pattern[index];
        index += 1;
        match character {
            '*' if pieces.last() == Some(&Piece::Star) => {}
            '*' => pieces.push(Piece::Star),
            '?' => pieces.push(Piece::Any),
            '[' => {
                let (piece, next) = set(pattern, index);
                pieces.push(piece);
                index = next;
            }
            _ => pieces.push(Piece::Literal(character)),
        }
    }
    pieces
}

/// The set starting after `[` at `start`, and the index after it; an unclosed `[` is literal.
fn set(pattern: &[char], start: usize) -> (Piece, usize) {
    let negated: bool = pattern.get(start) == Some(&'!');
    let first: usize = start + usize::from(negated);
    let Some(end) = (first + 1..pattern.len()).find(|&index| pattern[index] == ']') else {
        return (Piece::Literal('['), start);
    };
    let body: &[char] = &pattern[first..end];
    let mut members: Vec<(char, char)> = Vec::new();
    let mut index: usize = 0;
    while index < body.len() {
        match body.get(index + 1..index + 3) {
            Some(['-', high]) => {
                members.push((body[index], *high));
                index += 3;
            }
            _ => {
                members.push((body[index], body[index]));
                index += 1;
            }
        }
    }
    (Piece::Set { negated, members }, end + 1)
}

/// Whether all of `name` matches `pattern`.
pub(crate) fn wildcard_match(name: &str, pattern: &str) -> bool {
    let pieces: Vec<Piece> = pieces(&pattern.chars().collect::<Vec<char>>());
    let name: Vec<char> = name.chars().collect();
    let (mut piece, mut character) = (0_usize, 0_usize);
    let mut resume: Option<(usize, usize)> = None;
    while character < name.len() {
        match pieces.get(piece) {
            Some(Piece::Star) => {
                resume = Some((piece, character));
                piece += 1;
            }
            Some(single) if single.matches(name[character]) => {
                piece += 1;
                character += 1;
            }
            _ => match resume {
                Some((star, consumed)) => {
                    piece = star + 1;
                    character = consumed + 1;
                    resume = Some((star, consumed + 1));
                }
                None => return false,
            },
        }
    }
    pieces[piece..]
        .iter()
        .all(|remaining| *remaining == Piece::Star)
}
