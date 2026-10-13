//! The subset of Rich's console layout the diff summary uses: text, groups, tables and columns.

use sqlbuild_core::text::main::cell_len::cell_len;

use crate::diff_report::_helpers::text_cells::wrap_line;

/// Text attributes and one standard foreground color, as Rich renders them.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct Style {
    pub(crate) bold: bool,
    pub(crate) dim: bool,
    pub(crate) italic: bool,
    /// The SGR foreground code, such as 36 for cyan; zero for none.
    pub(crate) color: u8,
}

impl Style {
    pub(crate) const PLAIN: Self = Self {
        bold: false,
        dim: false,
        italic: false,
        color: 0,
    };

    /// This style with `other`'s attributes and color layered on top.
    pub(crate) fn with(self, other: Self) -> Self {
        Self {
            bold: self.bold || other.bold,
            dim: self.dim || other.dim,
            italic: self.italic || other.italic,
            color: if other.color == 0 {
                self.color
            } else {
                other.color
            },
        }
    }

    fn sgr(self) -> String {
        let mut codes: Vec<String> = Vec::new();
        for (enabled, code) in [(self.bold, "1"), (self.dim, "2"), (self.italic, "3")] {
            if enabled {
                codes.push(code.to_owned());
            }
        }
        if self.color != 0 {
            codes.push(self.color.to_string());
        }
        codes.join(";")
    }
}

#[derive(Clone, Debug)]
pub(crate) struct Segment {
    text: String,
    style: Style,
}

pub(crate) type Line = Vec<Segment>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Justify {
    Left,
    Center,
    Right,
}

/// Box-drawing characters per line kind, each as left, horizontal, divider and right.
#[derive(Clone, Copy, Debug)]
pub(crate) struct BoxChars {
    pub(crate) top: [char; 4],
    pub(crate) row: [char; 4],
    pub(crate) separator: [char; 4],
    pub(crate) bottom: [char; 4],
}

#[derive(Clone, Debug)]
pub(crate) struct Column {
    pub(crate) justify: Justify,
    pub(crate) style: Style,
    /// Maximum content cells; longer content folds.
    pub(crate) max_width: Option<usize>,
}

#[derive(Clone, Debug)]
pub(crate) struct Table {
    pub(crate) columns: Vec<Column>,
    pub(crate) rows: Vec<Vec<Node>>,
    /// Whether a section separator follows each row.
    pub(crate) section_after: Vec<bool>,
    pub(crate) borders: Option<BoxChars>,
    /// Left and right cell padding.
    pub(crate) padding: (usize, usize),
    pub(crate) collapse_padding: bool,
    pub(crate) pad_edge: bool,
}

#[derive(Clone, Debug)]
pub(crate) enum Node {
    Text(String, Style),
    Group(Vec<Node>),
    Table(Table),
    Columns(Vec<Node>),
    /// A heavy-bordered panel spanning the width with one centered title line.
    Panel(String, Style),
}

/// How a table cell justifies and overflows its text.
#[derive(Clone, Copy, Debug)]
struct CellLayout {
    justify: Justify,
    fold: bool,
}

impl Node {
    pub(crate) fn plain(text: impl Into<String>) -> Self {
        Self::Text(text.into(), Style::PLAIN)
    }

    pub(crate) fn styled(text: impl Into<String>, style: Style) -> Self {
        Self::Text(text.into(), style)
    }
}

impl Table {
    /// `Table.grid`: no borders, collapsed padding and no edge padding.
    pub(crate) fn grid(columns: Vec<Column>, right_padding: usize) -> Self {
        Self {
            columns,
            rows: Vec::new(),
            section_after: Vec::new(),
            borders: None,
            padding: (right_padding, right_padding),
            collapse_padding: true,
            pad_edge: false,
        }
    }

    pub(crate) fn add_row(&mut self, cells: Vec<Node>) {
        self.rows.push(cells);
        self.section_after.push(false);
    }

    pub(crate) fn add_section(&mut self) {
        if let Some(last) = self.section_after.last_mut() {
            *last = true;
        }
    }
}

pub(crate) fn column(justify: Justify, style: Style) -> Column {
    Column {
        justify,
        style,
        max_width: None,
    }
}

fn text_lines(text: &str) -> Vec<&str> {
    text.split('\n').collect()
}

fn segment(text: String, style: Style) -> Segment {
    Segment { text, style }
}

fn line_cells(line: &Line) -> usize {
    line.iter().map(|part| cell_len(&part.text)).sum()
}

/// `Measurement.get(...).maximum` of one node within `max_width` cells.
fn measure(node: &Node, max_width: usize) -> usize {
    let natural: usize = match node {
        Node::Text(text, _) => text_lines(text)
            .into_iter()
            .map(cell_len)
            .max()
            .unwrap_or(0),
        Node::Group(children) => children
            .iter()
            .map(|child| measure(child, max_width))
            .max()
            .unwrap_or(0),
        Node::Table(table) => {
            let extra: usize = table_extra_width(table);
            column_widths(table, max_width.saturating_sub(extra))
                .iter()
                .sum::<usize>()
                + extra
                + if table.rows.is_empty() { max_width } else { 0 }
        }
        Node::Columns(_) | Node::Panel(..) => max_width,
    };
    natural.min(max_width)
}

fn table_extra_width(table: &Table) -> usize {
    table.borders.map_or(0, |_| table.columns.len() + 1)
}

/// The left and right padding of one cell column.
fn cell_padding(table: &Table, index: usize) -> (usize, usize) {
    let (mut left, mut right) = table.padding;
    if table.collapse_padding && index > 0 {
        left = left.saturating_sub(right);
    }
    if !table.pad_edge {
        if index == 0 {
            left = 0;
        }
        if index + 1 == table.columns.len() {
            right = 0;
        }
    }
    (left, right)
}

fn column_maximum(table: &Table, index: usize, max_width: usize) -> usize {
    let (left, right) = cell_padding(table, index);
    let padding: usize = left + right;
    let mut widest: Option<usize> = None;
    for row in &table.rows {
        if let Some(cell) = row.get(index) {
            let width: usize = measure(cell, max_width.saturating_sub(padding)) + padding;
            widest = Some(widest.map_or(width, |current| current.max(width)));
        }
    }
    let mut maximum: usize = widest.unwrap_or(max_width).min(max_width);
    if let Some(limit) = table.columns[index].max_width {
        let (configured_left, configured_right) = table.padding;
        let configured: usize = if table.collapse_padding && index > 0 {
            configured_left.saturating_sub(configured_right) + configured_right
        } else {
            configured_left + configured_right
        };
        maximum = maximum.min(limit + configured);
    }
    maximum
}

fn ratio_reduce(
    total: usize,
    ratios: &[usize],
    maximums: &[usize],
    values: &[usize],
) -> Vec<usize> {
    let ratios: Vec<usize> = ratios
        .iter()
        .zip(maximums)
        .map(|(ratio, maximum)| if *maximum > 0 { *ratio } else { 0 })
        .collect();
    let mut total_ratio: usize = ratios.iter().sum();
    if total_ratio == 0 {
        return values.to_vec();
    }
    let mut remaining: usize = total;
    let mut result: Vec<usize> = Vec::with_capacity(values.len());
    for ((ratio, maximum), value) in ratios.iter().zip(maximums).zip(values) {
        if *ratio > 0 && total_ratio > 0 {
            let share: f64 = (*ratio as f64) * (remaining as f64) / (total_ratio as f64);
            let distributed: usize = (*maximum).min(share.round_ties_even() as usize);
            result.push(value.saturating_sub(distributed));
            remaining = remaining.saturating_sub(distributed);
            total_ratio -= ratio;
        } else {
            result.push(*value);
        }
    }
    result
}

fn collapse_widths(mut widths: Vec<usize>, max_width: usize) -> Vec<usize> {
    let mut total: usize = widths.iter().sum();
    while total > 0 && total > max_width {
        let excess: usize = total - max_width;
        let widest: usize = widths.iter().copied().max().unwrap_or(0);
        let second: usize = widths
            .iter()
            .copied()
            .filter(|width| *width != widest)
            .max()
            .unwrap_or(0);
        let difference: usize = widest - second;
        if difference == 0 {
            break;
        }
        let ratios: Vec<usize> = widths
            .iter()
            .map(|width| usize::from(*width == widest))
            .collect();
        let maximums: Vec<usize> = vec![excess.min(difference); widths.len()];
        widths = ratio_reduce(excess, &ratios, &maximums, &widths);
        total = widths.iter().sum();
    }
    widths
}

/// `Table._calculate_column_widths` for a table that does not expand.
fn column_widths(table: &Table, max_width: usize) -> Vec<usize> {
    let mut widths: Vec<usize> = (0..table.columns.len())
        .map(|index| column_maximum(table, index, max_width).max(1))
        .collect();
    if widths.iter().sum::<usize>() > max_width {
        widths = collapse_widths(widths, max_width);
        let total: usize = widths.iter().sum();
        if total > max_width {
            let ones: Vec<usize> = vec![1; widths.len()];
            widths = ratio_reduce(total - max_width, &ones, &widths.clone(), &widths);
        }
        widths = widths
            .iter()
            .enumerate()
            .map(|(index, width)| column_maximum(table, index, *width))
            .collect();
    }
    widths
}

fn justified(text: String, width: usize, justify: Justify) -> String {
    let content: String = match justify {
        Justify::Left => text,
        Justify::Center | Justify::Right => text.trim_end().to_owned(),
    };
    let used: usize = cell_len(&content);
    let free: usize = width.saturating_sub(used);
    match justify {
        Justify::Left => content + &" ".repeat(free),
        Justify::Center => " ".repeat(free / 2) + &content + &" ".repeat(free - free / 2),
        Justify::Right => " ".repeat(free) + &content,
    }
}

/// Render a node into lines at most `width` cells wide.
fn render(node: &Node, width: usize, layout: Option<CellLayout>, base: Style) -> Vec<Line> {
    match node {
        Node::Text(text, style) => {
            let combined: Style = base.with(*style);
            let fold: bool = layout.is_none_or(|cell| cell.fold);
            let mut lines: Vec<Line> = Vec::new();
            for source in text_lines(text) {
                for piece in wrap_line(source, width, fold) {
                    let piece: String = match layout {
                        Some(cell) => justified(piece, width, cell.justify),
                        None => piece,
                    };
                    lines.push(vec![segment(piece, combined)]);
                }
            }
            lines
        }
        Node::Group(children) => children
            .iter()
            .flat_map(|child| render(child, width, layout, base))
            .collect(),
        Node::Table(table) => render_table(table, width),
        Node::Panel(title, style) => {
            let inner: usize = width.saturating_sub(4);
            vec![
                border_line(['┏', '━', '━', '┓'], &[width.saturating_sub(2)]),
                vec![
                    segment("┃ ".to_owned(), Style::PLAIN),
                    segment(justified(title.clone(), inner, Justify::Center), *style),
                    segment(" ┃".to_owned(), Style::PLAIN),
                ],
                border_line(['┗', '━', '━', '┛'], &[width.saturating_sub(2)]),
            ]
        }
        Node::Columns(items) => render_table(&columns_grid(items, width), width),
    }
}

/// The grid `Columns` lays its items out in.
fn columns_grid(items: &[Node], max_width: usize) -> Table {
    let widths: Vec<usize> = items.iter().map(|item| measure(item, max_width)).collect();
    let mut count: usize = items.len().max(1);
    while count > 1 {
        let mut column_widths: Vec<usize> = Vec::new();
        let mut overflow: bool = false;
        for (position, width) in widths.iter().enumerate() {
            let column_index: usize = position % count;
            if column_widths.len() <= column_index {
                column_widths.push(0);
            }
            column_widths[column_index] = column_widths[column_index].max(*width);
            if column_widths.iter().sum::<usize>() > max_width {
                count = column_widths.len() - 1;
                overflow = true;
                break;
            }
        }
        if !overflow {
            break;
        }
    }
    let mut grid: Table = Table::grid(vec![column(Justify::Left, Style::PLAIN); count], 0);
    for chunk in items.chunks(count) {
        let mut cells: Vec<Node> = chunk.to_vec();
        cells.resize(count, Node::plain(""));
        grid.add_row(cells);
    }
    grid
}

fn border_line(chars: [char; 4], widths: &[usize]) -> Line {
    let [left, horizontal, divider, right] = chars;
    let mut text: String = left.to_string();
    for (index, width) in widths.iter().enumerate() {
        if index > 0 {
            text.push(divider);
        }
        text.push_str(&horizontal.to_string().repeat(*width));
    }
    text.push(right);
    vec![segment(text, Style::PLAIN)]
}

fn render_cell(table: &Table, index: usize, cell: &Node, width: usize) -> Vec<Line> {
    let spec: &Column = &table.columns[index];
    let (left, right) = cell_padding(table, index);
    let content_width: usize = width.saturating_sub(left + right);
    let mut lines: Vec<Line> = Vec::new();
    let layout: CellLayout = CellLayout {
        justify: spec.justify,
        fold: spec.max_width.is_some(),
    };
    for mut line in render(cell, content_width, Some(layout), spec.style) {
        let used: usize = line_cells(&line);
        let mut padded: Line = Vec::new();
        if left > 0 {
            padded.push(segment(" ".repeat(left), spec.style));
        }
        padded.append(&mut line);
        if used < content_width {
            padded.push(segment(" ".repeat(content_width - used), spec.style));
        }
        if right > 0 {
            padded.push(segment(" ".repeat(right), spec.style));
        }
        lines.push(padded);
    }
    lines
}

fn render_table(table: &Table, max_width: usize) -> Vec<Line> {
    let extra: usize = table_extra_width(table);
    let widths: Vec<usize> = column_widths(table, max_width.saturating_sub(extra));
    let mut lines: Vec<Line> = Vec::new();
    if let Some(chars) = table.borders {
        lines.push(border_line(chars.top, &widths));
    }
    for (row_index, row) in table.rows.iter().enumerate() {
        let empty: Node = Node::plain("");
        let cells: Vec<Vec<Line>> = widths
            .iter()
            .enumerate()
            .map(|(index, width)| {
                render_cell(table, index, row.get(index).unwrap_or(&empty), *width)
            })
            .collect();
        let height: usize = cells.iter().map(Vec::len).max().unwrap_or(0);
        for line_index in 0..height {
            let mut line: Line = Vec::new();
            if let Some(chars) = table.borders {
                line.push(segment(chars.row[0].to_string(), Style::PLAIN));
            }
            for (index, cell) in cells.iter().enumerate() {
                if let (true, Some(chars)) = (index > 0, table.borders) {
                    line.push(segment(chars.row[2].to_string(), Style::PLAIN));
                }
                match cell.get(line_index) {
                    Some(content) => line.extend(content.iter().cloned()),
                    None => line.push(segment(
                        " ".repeat(widths[index]),
                        table.columns[index].style,
                    )),
                }
            }
            if let Some(chars) = table.borders {
                line.push(segment(chars.row[3].to_string(), Style::PLAIN));
            }
            lines.push(line);
        }
        let separated: bool = table.section_after[row_index] && row_index + 1 < table.rows.len();
        if let (true, Some(chars)) = (separated, table.borders) {
            lines.push(border_line(chars.separator, &widths));
        }
    }
    if let Some(chars) = table.borders {
        lines.push(border_line(chars.bottom, &widths));
    }
    lines
}

/// Render top-level nodes as `Console.print` calls do, one after another.
pub(crate) fn print_nodes(nodes: &[Node], width: usize, use_color: bool) -> String {
    let mut output: String = String::new();
    for node in nodes {
        for line in render(node, width, None, Style::PLAIN) {
            for part in line {
                if part.text.is_empty() {
                    continue;
                }
                if use_color && part.style != Style::PLAIN {
                    output.push_str(&format!("\x1b[{}m{}\x1b[0m", part.style.sgr(), part.text));
                } else {
                    output.push_str(&part.text);
                }
            }
            output.push('\n');
        }
    }
    output.trim_end().to_owned()
}
