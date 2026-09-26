//! Native authored positions, including macro-expansion passes.

use crate::semantic_validation::_helpers::diagnostics::column_pattern;
use crate::semantic_validation::_helpers::normalization::normalize;
use crate::semantic_validation::models::{BindingPositions, PositionInput};
use pyo3::exceptions::PyValueError;
use pyo3::{PyResult, pymethods};
use regex::Regex;
use std::collections::HashMap;
use std::sync::LazyLock;

const POPULAR_TOKEN_THRESHOLD: usize = 200;
static TOKENS: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| Regex::new(r"\w+|[^\w\s]").map_err(|error| error.to_string()));
type Mapping = (usize, usize, usize, usize);

#[pymethods]
impl BindingPositions {
    #[new]
    fn new(request: PositionInput) -> PyResult<Self> {
        let PositionInput {
            authored,
            query,
            expanded,
            cleaned,
            passes,
        } = request;
        let mapped = normalize(&expanded, "snowflake", &HashMap::new(), &HashMap::new());
        let offsets = match mapped {
            Ok(mapped) if mapped.sql == cleaned => mapped.offsets,
            _ if expanded == cleaned => (0..=expanded.chars().count()).collect(),
            _ => align_offsets(&expanded, &cleaned).map_err(PyValueError::new_err)?,
        };
        Ok(Self {
            query_start: authored
                .find(&query)
                .map(|offset| authored[..offset].chars().count()),
            lines: line_starts(&authored),
            cleaned_lines: line_starts(&cleaned),
            authored,
            offsets,
            passes,
        })
    }

    fn position(
        &self,
        start: Option<usize>,
        line: Option<usize>,
        column: Option<usize>,
        message: &str,
    ) -> PyResult<(Option<usize>, Option<usize>)> {
        if let Some(captures) = column_pattern()
            .map_err(PyValueError::new_err)?
            .captures(message)
        {
            let identifier = captures[1].rsplit('.').next().unwrap_or(&captures[1]);
            let mut occurrences = self
                .authored
                .match_indices(identifier)
                .filter(|(offset, _)| {
                    let before = self.authored[..*offset].chars().next_back();
                    let after = self.authored[*offset + identifier.len()..].chars().next();
                    !before.is_some_and(word) && !after.is_some_and(word)
                });
            if let Some((offset, _)) = occurrences.next()
                && occurrences.next().is_none()
            {
                return Ok(position(
                    &self.lines,
                    self.authored[..offset].chars().count(),
                ));
            }
        }
        let Some(query_start) = self.query_start else {
            return Ok((None, None));
        };
        let offset = start.or_else(|| {
            line.zip(column).map(|(line, column)| {
                self.cleaned_lines
                    .get(line.saturating_sub(1))
                    .copied()
                    .unwrap_or(0)
                    + column.saturating_sub(1)
            })
        });
        let Some(offset) = offset else {
            return Ok(position(&self.lines, query_start));
        };
        let mut mapped = self
            .offsets
            .get(offset)
            .copied()
            .unwrap_or_else(|| *self.offsets.last().unwrap_or(&0));
        for pass in self.passes.iter().rev() {
            let mut adjusted = mapped as isize;
            for &(source_start, source_end, output_start, output_end) in pass {
                if mapped < output_start {
                    break;
                }
                if mapped < output_end {
                    adjusted = source_start as isize;
                    break;
                }
                adjusted +=
                    (source_end - source_start) as isize - (output_end - output_start) as isize;
            }
            mapped = adjusted.max(0) as usize;
        }
        Ok(position(&self.lines, query_start + mapped))
    }
}

fn word(character: char) -> bool {
    character == '_' || character.is_alphanumeric()
}

fn line_starts(sql: &str) -> Vec<usize> {
    let mut starts = vec![0];
    starts.extend(
        sql.chars()
            .enumerate()
            .filter_map(|(index, ch)| (ch == '\n').then_some(index + 1)),
    );
    starts
}

fn position(lines: &[usize], offset: usize) -> (Option<usize>, Option<usize>) {
    let line = lines.partition_point(|start| *start <= offset).max(1);
    (Some(line), Some(offset - lines[line - 1] + 1))
}

fn align_offsets(original: &str, normalized: &str) -> Result<Vec<usize>, String> {
    let tokens = TOKENS.as_ref().map_err(Clone::clone)?;
    let a: Vec<_> = tokens.find_iter(original).collect();
    let b: Vec<_> = tokens.find_iter(normalized).collect();
    let av: Vec<_> = a
        .iter()
        .map(|token| token.as_str().to_lowercase())
        .collect();
    let bv: Vec<_> = b
        .iter()
        .map(|token| token.as_str().to_lowercase())
        .collect();
    let mut index: HashMap<&str, Vec<usize>> = HashMap::new();
    for (position, token) in bv.iter().enumerate() {
        index.entry(token).or_default().push(position);
    }
    if b.len() >= POPULAR_TOKEN_THRESHOLD {
        index.retain(|_, positions| positions.len() <= b.len() / 100 + 1);
    }
    let mut pending = vec![(0, a.len(), 0, b.len())];
    let mut blocks: Vec<(usize, usize, usize)> = Vec::new();
    while let Some((alo, ahi, blo, bhi)) = pending.pop() {
        let (mut ai, mut bi, mut size) = (alo, blo, 0);
        let mut previous: HashMap<usize, usize> = HashMap::new();
        for i in alo..ahi {
            let mut current: HashMap<usize, usize> = HashMap::new();
            for &j in index.get(av[i].as_str()).into_iter().flatten() {
                if j < blo {
                    continue;
                }
                if j >= bhi {
                    break;
                }
                let length = j
                    .checked_sub(1)
                    .and_then(|j| previous.get(&j))
                    .copied()
                    .unwrap_or(0)
                    + 1;
                current.insert(j, length);
                if length > size {
                    ai = i + 1 - length;
                    bi = j + 1 - length;
                    size = length;
                }
            }
            previous = current;
        }
        while ai > alo && bi > blo && av[ai - 1] == bv[bi - 1] {
            ai -= 1;
            bi -= 1;
            size += 1;
        }
        while ai + size < ahi && bi + size < bhi && av[ai + size] == bv[bi + size] {
            size += 1;
        }
        if size > 0 {
            blocks.push((ai, bi, size));
            if alo < ai && blo < bi {
                pending.push((alo, ai, blo, bi));
            }
            if ai + size < ahi && bi + size < bhi {
                pending.push((ai + size, ahi, bi + size, bhi));
            }
        }
    }
    blocks.sort();
    let ac = byte_char_map(original);
    let bc = byte_char_map(normalized);
    let mut mappings: Vec<Mapping> = Vec::new();
    for (ai, bi, size) in blocks {
        for i in 0..size {
            mappings.push((
                ac[a[ai + i].start()],
                ac[a[ai + i].end()],
                bc[b[bi + i].start()],
                bc[b[bi + i].end()],
            ));
        }
    }
    let mut offsets = Vec::with_capacity(normalized.chars().count() + 1);
    let original_len = original.chars().count();
    let mut index = 0;
    for offset in 0..=normalized.chars().count() {
        while index < mappings.len() && offset > mappings[index].3 {
            index += 1;
        }
        offsets.push(match mappings.get(index) {
            Some(&(start, end, target, _)) => {
                start + offset.saturating_sub(target).min(end - start)
            }
            None => original_len,
        });
    }
    Ok(offsets)
}

fn byte_char_map(sql: &str) -> Vec<usize> {
    let mut map = vec![0; sql.len() + 1];
    for (index, (byte, ch)) in sql.char_indices().enumerate() {
        map[byte..byte + ch.len_utf8()].fill(index);
        map[byte + ch.len_utf8()] = index + 1;
    }
    map
}
