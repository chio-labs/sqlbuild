//! Python's `fnmatch.fnmatchcase`.

use crate::text::_helpers::fnmatch::{Piece, translate};

/// Whether `name` matches the shell-style `pattern`, case-sensitively and across newlines.
#[must_use]
pub fn python_fnmatchcase(name: &str, pattern: &str) -> bool {
    let pieces: Vec<Piece> = translate(&pattern.chars().collect::<Vec<char>>());
    if pieces.contains(&Piece::Never) {
        return false;
    }
    let characters: Vec<char> = name.chars().collect();
    let (mut piece, mut character) = (0_usize, 0_usize);
    let mut resume: Option<(usize, usize)> = None;
    while character < characters.len() {
        match pieces.get(piece) {
            Some(Piece::Star) => {
                resume = Some((piece, character));
                piece += 1;
            }
            Some(single) if single.matches(characters[character]) => {
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
