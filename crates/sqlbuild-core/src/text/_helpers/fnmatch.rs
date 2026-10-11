//! `fnmatch._translate` pieces, read the way `re` reads the translated character sets.

/// One translated pattern piece; every piece except `Star` matches exactly one character.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Piece {
    Star,
    Any,
    Literal(char),
    Set {
        negated: bool,
        members: Vec<(char, char)>,
    },
    /// Python's `(?!)` for a set whose every range was empty.
    Never,
}

impl Piece {
    /// Whether this one-character piece matches the code point `character`, surrogates included.
    pub(crate) fn matches(&self, character: u32) -> bool {
        match self {
            Self::Star | Self::Any => true,
            Self::Literal(literal) => u32::from(*literal) == character,
            Self::Set { negated, members } => {
                let member: bool = members.iter().any(|(low, high)| {
                    u32::from(*low) <= character && character <= u32::from(*high)
                });
                member != *negated
            }
            Self::Never => false,
        }
    }
}

/// One translated set member: a literal character or the hyphen joining a range.
#[derive(Clone, Copy, PartialEq, Eq)]
enum SetAtom {
    Character(char),
    RangeHyphen,
}

/// The pieces of `pattern`, with consecutive stars collapsed.
pub(crate) fn translate(pattern: &[char]) -> Vec<Piece> {
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
    let length: usize = pattern.len();
    let mut end: usize = start;
    if end < length && pattern[end] == '!' {
        end += 1;
    }
    if end < length && pattern[end] == ']' {
        end += 1;
    }
    while end < length && pattern[end] != ']' {
        end += 1;
    }
    if end >= length {
        return (Piece::Literal('['), start);
    }
    let chunks: Vec<Vec<char>> = if pattern[start..end].contains(&'-') {
        hyphen_chunks(pattern, start, end)
    } else {
        vec![pattern[start..end].to_vec()]
    };
    (set_piece(&chunks), end + 1)
}

/// Python's chunks of a set holding hyphens, after it drops empty ranges.
fn hyphen_chunks(pattern: &[char], start: usize, end: usize) -> Vec<Vec<char>> {
    let mut chunks: Vec<Vec<char>> = Vec::new();
    let mut chunk_start: usize = start;
    let mut search: usize = if pattern[start] == '!' {
        start + 2
    } else {
        start + 1
    };
    while let Some(found) = (search..end).find(|&position| pattern[position] == '-') {
        chunks.push(pattern[chunk_start..found].to_vec());
        chunk_start = found + 1;
        search = found + 3;
    }
    let last: Vec<char> = pattern[chunk_start..end].to_vec();
    match (last.is_empty(), chunks.last_mut()) {
        (true, Some(previous)) => previous.push('-'),
        _ => chunks.push(last),
    }
    let mut position: usize = chunks.len().saturating_sub(1);
    while position > 0 {
        let (left, right) = chunks.split_at_mut(position);
        let previous: &mut Vec<char> = &mut left[position - 1];
        if let (Some(&high), Some(&low)) = (previous.last(), right[0].first())
            && high > low
        {
            previous.pop();
            previous.extend(right[0].iter().skip(1));
            chunks.remove(position);
        }
        position -= 1;
    }
    chunks
}

/// The piece `re` reads from the chunks joined by range hyphens.
fn set_piece(chunks: &[Vec<char>]) -> Piece {
    let mut atoms: Vec<SetAtom> = Vec::new();
    for (position, chunk) in chunks.iter().enumerate() {
        if position > 0 {
            atoms.push(SetAtom::RangeHyphen);
        }
        atoms.extend(chunk.iter().map(|character| SetAtom::Character(*character)));
    }
    match atoms.as_slice() {
        [] => return Piece::Never,
        [SetAtom::Character('!')] => return Piece::Any,
        _ => {}
    }
    let negated: bool = atoms[0] == SetAtom::Character('!');
    let mut members: Vec<(char, char)> = Vec::new();
    let mut index: usize = usize::from(negated);
    while index < atoms.len() {
        let low: char = atom_character(atoms[index]);
        match (atoms.get(index + 1), atoms.get(index + 2)) {
            (Some(SetAtom::RangeHyphen), Some(high)) => {
                members.push((low, atom_character(*high)));
                index += 3;
            }
            _ => {
                members.push((low, low));
                index += 1;
            }
        }
    }
    Piece::Set { negated, members }
}

/// A set atom's character; a hyphen `re` cannot join into a range is literal.
fn atom_character(atom: SetAtom) -> char {
    match atom {
        SetAtom::Character(character) => character,
        SetAtom::RangeHyphen => '-',
    }
}

/// Whether the code points of `name` match `pattern`, as `re.match` of `fnmatch.translate` does.
pub(crate) fn code_points_match(name: &[u32], pattern: &str) -> bool {
    let pieces: Vec<Piece> = translate(&pattern.chars().collect::<Vec<char>>());
    if pieces.contains(&Piece::Never) {
        return false;
    }
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
