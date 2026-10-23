//! The import edits and refusals of one Python file.

use ruff_python_ast::visitor::{Visitor, walk_expr, walk_stmt};
use ruff_python_ast::{Alias, Expr, ExprCall, ModModule, Stmt, StmtImport, StmtImportFrom};
use ruff_text_size::Ranged;

use crate::import_rewrites::_helpers::module_paths::{
    dotted, dotted_parts, package_parts, resolve_relative, spell_from_target,
};
use crate::import_rewrites::constants::{
    DYNAMIC_IMPORT_FUNCTIONS, FROM_KEYWORD, MODULE_SEPARATOR, STAR_IMPORT_NAME,
};
use crate::import_rewrites::models::{ImportEdit, ImportRefusal, PythonSource};
use crate::import_rewrites::types::{ModuleMoves, PackageBindings};
use crate::module_parse::main::parse_python_module::parse_python_module;

/// One file's text, path, packages before and after any move of the file, and module moves.
pub(crate) struct ImportFile<'a> {
    pub(crate) path: &'a str,
    pub(crate) contents: &'a str,
    /// The package relative imports start from, where the file is now.
    pub(crate) package: Vec<String>,
    /// The package relative imports start from, where the file will be.
    pub(crate) new_package: Vec<String>,
    /// Each moved module's dotted parts, before and after.
    pub(crate) moves: &'a ModuleMoves,
    /// The names each project package's `__init__.py` binds, by package parts.
    pub(crate) package_bindings: &'a PackageBindings,
}

/// The edits and refusals of every import in `source`, which moves to `destination` if any.
pub(crate) fn source_rewrites(
    source: &PythonSource,
    destination: Option<&str>,
    (moves, bindings): (&ModuleMoves, &PackageBindings),
) -> (Vec<ImportEdit>, Vec<ImportRefusal>) {
    let Ok(module) = parse_python_module(&source.contents) else {
        let refusals: Vec<ImportRefusal> = moves
            .keys()
            .find(|old| source.contents.contains(&dotted(old)))
            .map(|old| ImportRefusal {
                path: source.path.clone(),
                line: 1,
                column: 1,
                reason: format!(
                    "names {} but is not valid Python, so its imports cannot be rewritten; fix \
                     the file first",
                    dotted(old)
                ),
            })
            .into_iter()
            .collect();
        return (Vec::new(), refusals);
    };
    let file = ImportFile {
        path: &source.path,
        contents: &source.contents,
        package: package_parts(&source.path),
        new_package: package_parts(destination.unwrap_or(&source.path)),
        moves,
        package_bindings: bindings,
    };
    file_rewrites(&file, &module)
}

/// The edits and refusals of every import in `module`, in source order.
fn file_rewrites(
    file: &ImportFile<'_>,
    module: &ModModule,
) -> (Vec<ImportEdit>, Vec<ImportRefusal>) {
    let mut collector = Collector {
        file,
        edits: Vec::new(),
        refusals: Vec::new(),
    };
    for statement in &module.body {
        collector.visit_stmt(statement);
    }
    (collector.edits, collector.refusals)
}

struct Collector<'a, 'b> {
    file: &'b ImportFile<'a>,
    edits: Vec<ImportEdit>,
    refusals: Vec<ImportRefusal>,
}

impl<'c> Visitor<'c> for Collector<'_, '_> {
    fn visit_stmt(&mut self, statement: &'c Stmt) {
        match statement {
            Stmt::Import(import) => self.import(import),
            Stmt::ImportFrom(import) => self.import_from(import),
            _ => {}
        }
        walk_stmt(self, statement);
    }

    fn visit_expr(&mut self, expression: &'c Expr) {
        if let Expr::Call(call) = expression {
            self.dynamic_import(call);
        }
        walk_expr(self, expression);
    }
}

impl Collector<'_, '_> {
    fn refuse(&mut self, offset: usize, reason: String) {
        let before: &str = self.file.contents.get(..offset).unwrap_or_default();
        let line_start: usize = before.rfind('\n').map_or(0, |index| index + 1);
        self.refusals.push(ImportRefusal {
            path: self.file.path.to_owned(),
            line: before.matches('\n').count() + 1,
            column: before[line_start..].chars().count() + 1,
            reason,
        });
    }

    fn edit(&mut self, (start, end): (usize, usize), replacement: String) {
        self.edits.push(ImportEdit {
            path: self.file.path.to_owned(),
            start,
            end,
            replacement,
        });
    }

    /// `import a.b.c as name` follows a moved module; without `as` the dotted name is refused.
    fn import(&mut self, import: &StmtImport) {
        for alias in &import.names {
            let parts: Vec<String> = dotted_parts(alias.name.as_str());
            let Some(moved) = self.file.moves.get(&parts) else {
                continue;
            };
            let start: usize = alias.name.range().start().to_usize();
            if alias.asname.is_none() {
                self.refuse(
                    start,
                    format!(
                        "imports {} without an alias, and code that reads the dotted name \
                         cannot be rewritten; import it with `as` or `from` first",
                        dotted(&parts)
                    ),
                );
                continue;
            }
            if !self.matches_source(alias, &parts) {
                self.refuse(start, unusual_spelling(&parts));
                continue;
            }
            self.edit((start, alias.name.range().end().to_usize()), dotted(moved));
        }
    }

    fn matches_source(&self, alias: &Alias, parts: &[String]) -> bool {
        let range = alias.name.range();
        self.file
            .contents
            .get(range.start().to_usize()..range.end().to_usize())
            == Some(dotted(parts).as_str())
    }

    /// `from <module> import names` reads from the moved module, or its new package, after moves.
    fn import_from(&mut self, import: &StmtImportFrom) {
        let level: usize = import.level as usize;
        let module: Vec<String> = import
            .module
            .as_ref()
            .map_or_else(Vec::new, |module| dotted_parts(module.as_str()));
        let Some(base) = resolve_relative(&self.file.package, level, &module) else {
            return;
        };
        let start: usize = import.range().start().to_usize();
        let Some(new_base) = self.new_base(import, &base, start) else {
            return;
        };
        let moved_file: bool = self.file.package != self.file.new_package;
        if new_base == base && (level == 0 || !moved_file) {
            return;
        }
        let spelled: String = spell_from_target(&self.file.new_package, &new_base, level);
        let original: String = format!(
            "{}{}",
            MODULE_SEPARATOR.to_string().repeat(level),
            dotted(&module)
        );
        if spelled == original {
            return;
        }
        let Some(span) = self.module_span(import) else {
            self.refuse(start, unusual_spelling(&base));
            return;
        };
        self.edit(span, spelled);
    }

    /// The module the statement must read from after the moves, or `None` when it is refused.
    fn new_base(
        &mut self,
        import: &StmtImportFrom,
        base: &[String],
        start: usize,
    ) -> Option<Vec<String>> {
        if let Some(moved) = self.file.moves.get(base) {
            return Some(moved.clone());
        }
        let star: bool = import
            .names
            .iter()
            .any(|alias| alias.name.as_str() == STAR_IMPORT_NAME);
        if star {
            if let Some((old, _)) = self
                .file
                .moves
                .iter()
                .find(|(old, _)| old.split_last().is_some_and(|(_, parent)| parent == base))
            {
                self.refuse(
                    start,
                    format!(
                        "star-imports the package of {}, which moves; import the names it \
                         needs explicitly first",
                        dotted(old)
                    ),
                );
                return None;
            }
            return Some(base.to_vec());
        }
        let mut moved: Vec<(&Alias, &Vec<String>)> = Vec::new();
        for alias in &import.names {
            let mut parts: Vec<String> = base.to_vec();
            parts.push(alias.name.as_str().to_owned());
            if let Some(new) = self.file.moves.get(&parts) {
                moved.push((alias, new));
            }
        }
        let Some((_, first_moved)) = moved.first() else {
            return Some(base.to_vec());
        };
        let package: &[String] = first_moved.split_last().map_or(&[], |(_, parent)| parent);
        match submodule_refusal(self.file, base, (&moved, import.names.len()), package) {
            None => Some(package.to_vec()),
            Some(reason) => {
                self.refuse(start, reason);
                None
            }
        }
    }

    /// The byte span of `<level dots><module>` after `from`, when the source spells it plainly.
    fn module_span(&self, import: &StmtImportFrom) -> Option<(usize, usize)> {
        let contents: &str = self.file.contents;
        let keyword_end: usize = import.range().start().to_usize() + FROM_KEYWORD.len();
        let rest: &str = contents.get(keyword_end..)?;
        let start: usize = keyword_end + (rest.len() - rest.trim_start_matches([' ', '\t']).len());
        let end: usize = match &import.module {
            Some(module) => module.range().end().to_usize(),
            None => {
                let dots: usize = contents
                    .get(start..)?
                    .chars()
                    .take_while(|character| *character == MODULE_SEPARATOR)
                    .count();
                start + dots
            }
        };
        let written: &str = contents.get(start..end)?;
        let expected: String = format!(
            "{}{}",
            MODULE_SEPARATOR.to_string().repeat(import.level as usize),
            import.module.as_ref().map_or("", |module| module.as_str())
        );
        (written == expected).then_some((start, end))
    }

    /// `importlib.import_module("...")` or `__import__("...")` naming a moved module.
    fn dynamic_import(&mut self, call: &ExprCall) {
        let function: Option<&str> = match call.func.as_ref() {
            Expr::Name(name) => Some(name.id.as_str()),
            Expr::Attribute(attribute) => Some(attribute.attr.as_str()),
            _ => None,
        };
        if !function.is_some_and(|function| DYNAMIC_IMPORT_FUNCTIONS.contains(&function)) {
            return;
        }
        let Some(Expr::StringLiteral(literal)) = call.arguments.args.first() else {
            return;
        };
        let name: &str = literal.value.to_str();
        let relative: &str = name.trim_start_matches(MODULE_SEPARATOR);
        let named: Option<Vec<String>> = self
            .file
            .moves
            .keys()
            .find(|old| {
                let dotted_old: String = dotted(old);
                name == dotted_old
                    || name.starts_with(&format!("{dotted_old}{MODULE_SEPARATOR}"))
                    || (relative.len() < name.len()
                        && old.last().is_some_and(|stem| {
                            relative == stem
                                || relative.ends_with(&format!("{MODULE_SEPARATOR}{stem}"))
                        }))
            })
            .cloned();
        if let Some(old) = named {
            self.refuse(
                call.range().start().to_usize(),
                format!(
                    "imports {} dynamically by name, which cannot be rewritten safely; \
                     change it to an import statement or update it by hand first",
                    dotted(&old)
                ),
            );
        }
    }
}

/// Why moved modules imported by name from `base` cannot follow to `package`, if they cannot.
fn submodule_refusal(
    file: &ImportFile<'_>,
    base: &[String],
    (moved, names): (&[(&Alias, &Vec<String>)], usize),
    package: &[String],
) -> Option<String> {
    for (alias, new) in moved {
        let name: &str = alias.name.as_str();
        let mut old: Vec<String> = base.to_vec();
        old.push(name.to_owned());
        if file
            .package_bindings
            .get(base)
            .is_some_and(|bound| bound.contains(name))
        {
            return Some(format!(
                "imports {name} from {}, whose __init__.py also binds {name}, so the import \
                 would read the moved module {} instead after a rewrite; rewrite it by hand first",
                dotted(base),
                dotted(&old)
            ));
        }
        if new.last().map(String::as_str) != Some(name) {
            return Some(format!(
                "imports the moved module {} by its name, which becomes {}; rewrite the import \
                 by hand or import the module with an alias first",
                dotted(&old),
                dotted(new)
            ));
        }
        if new.split_last().map(|(_, parent)| parent) != Some(package) {
            return Some(format!(
                "imports modules from {} that move to different packages; split the import \
                 first",
                dotted(base)
            ));
        }
    }
    (moved.len() != names).then(|| {
        format!(
            "imports a moved module from {} together with names that do not move with it; split \
             the import first",
            dotted(base)
        )
    })
}

fn unusual_spelling(parts: &[String]) -> String {
    format!(
        "imports {} with spacing or line breaks inside the module name; write it on one line \
         first",
        dotted(parts)
    )
}
