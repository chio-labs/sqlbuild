//! Strict analysis of a set of macro modules, and the fault-tolerant inventory built on it.

use ruff_python_ast::ModModule;
use sha2::{Digest, Sha256};
use std::cell::OnceCell;
use std::collections::{HashMap, HashSet};
use std::fmt::Write as _;

use crate::macro_modules::_helpers::declarations::{
    definition_line, is_public, parameter_names, public_non_function_declaration,
    top_level_functions,
};
use crate::macro_modules::_helpers::module_analysis::{
    ModuleAnalysis, ModuleSet, ParsedModule, analyze_module, parsed_module, repeated_path,
};
use crate::macro_modules::_helpers::module_names::{module_name, package_name};
use crate::macro_modules::constants::CYCLE_SEPARATOR;
use crate::macro_modules::errors::{MacroAnalysisFailure, MacroModuleParseError};
use crate::macro_modules::models::{
    MacroExport, MacroFault, MacroModuleInventory, MacroModuleLoad, MacroModuleSource,
};
use crate::module_parse::main::parse_python_module::parse_python_module;

/// A parsed module, or the message of the error its parse or declaration check raised.
type ParsedSource = Result<ModModule, String>;

/// The sources and their parses, each read at most once and only when analysis reaches it.
pub(crate) struct ProjectSources<'a> {
    sources: &'a [MacroModuleSource],
    parsed: Vec<OnceCell<Result<ParsedSource, MacroModuleParseError>>>,
}

impl<'a> ProjectSources<'a> {
    /// Unparsed sources.
    pub(crate) fn new(sources: &'a [MacroModuleSource]) -> Self {
        Self {
            sources,
            parsed: sources.iter().map(|_| OnceCell::new()).collect(),
        }
    }

    fn parsed(&self, index: usize) -> Result<&ParsedSource, MacroModuleParseError> {
        self.parsed[index]
            .get_or_init(|| parse_source(&self.sources[index]))
            .as_ref()
            .map_err(Clone::clone)
    }
}

fn parse_source(source: &MacroModuleSource) -> Result<ParsedSource, MacroModuleParseError> {
    if let Some(message) = &source.syntax_error {
        return Ok(Err(message.clone()));
    }
    let module: ModModule =
        parse_python_module(&source.contents).map_err(|message| MacroModuleParseError {
            relative_path: source.relative_path.display.clone(),
            message,
        })?;
    if let Some(name) = module.body.iter().find_map(public_non_function_declaration) {
        return Ok(Err(format!(
            "Macro module '{}' declaration '{name}' must be underscore-private",
            source.relative_path.display
        )));
    }
    Ok(Ok(module))
}

/// The modules of `subset` analysed in discovery order, or why analysis stopped first.
pub(crate) fn analyze_project(
    project: &ProjectSources<'_>,
    subset: &[usize],
) -> Result<Vec<ModuleAnalysis>, MacroAnalysisFailure> {
    let mut names: Vec<(usize, String)> = Vec::new();
    let mut seen: HashMap<String, usize> = HashMap::new();
    for index in subset {
        let name: String = module_name(&project.sources[*index]);
        if let Some(existing) = seen.get(&name) {
            return Err(MacroAnalysisFailure::Compile(format!(
                "Macro module path collision for '{name}': {} and {}",
                project.sources[*existing].relative_path.display,
                project.sources[*index].relative_path.display
            )));
        }
        seen.insert(name.clone(), *index);
        names.push((*index, name));
    }
    let mut modules: Vec<ParsedModule<'_>> = Vec::new();
    for (index, name) in names {
        let parsed: &ModModule = project
            .parsed(index)
            .map_err(MacroAnalysisFailure::Native)?
            .as_ref()
            .map_err(|message| MacroAnalysisFailure::Compile(message.clone()))?;
        modules.push(parsed_module(
            index,
            (name, &project.sources[index], parsed),
        ));
    }
    let package_names: Vec<String> = subset
        .iter()
        .map(|index| package_name(&project.sources[*index]))
        .collect();
    let set: ModuleSet<'_> = ModuleSet::new(modules, package_names);
    let analyses: Vec<ModuleAnalysis> = (0..set.modules.len())
        .map(|position| analyze_module(&set, position))
        .collect::<Result<_, _>>()
        .map_err(MacroAnalysisFailure::Compile)?;
    validate_import_cycles(project, &analyses).map_err(MacroAnalysisFailure::Compile)?;
    Ok(analyses)
}

fn validate_import_cycles(
    project: &ProjectSources<'_>,
    analyses: &[ModuleAnalysis],
) -> Result<(), String> {
    let edges: HashMap<String, Vec<String>> = analyses
        .iter()
        .map(|analysis| (analysis.name.clone(), analysis.module_dependencies.clone()))
        .collect();
    let files: HashMap<&str, usize> = analyses
        .iter()
        .map(|analysis| (analysis.name.as_str(), analysis.file_index))
        .collect();
    let mut sorted: Vec<&String> = edges.keys().collect();
    sorted.sort();
    let Some(cycle) = repeated_path(sorted, &edges) else {
        return Ok(());
    };
    let repeated: &str = cycle.last().map_or("", |name| name.as_str());
    let names: Vec<&str> = cycle.iter().map(|name| name.as_str()).collect();
    Err(format!(
        "Macro import cycle in '{}': {}",
        project.sources[files[repeated]].relative_path.display,
        names.join(CYCLE_SEPARATOR)
    ))
}

fn source_digest(contents: &str) -> String {
    let digest = Sha256::digest(contents.as_bytes());
    let mut text: String = String::with_capacity(digest.len() * 2);
    for byte in digest {
        let _ = write!(text, "{byte:02x}");
    }
    text
}

/// Exports of cleanly analysed modules, with a fault for every repeated export name.
fn inventory_from_analyses(
    project: &ProjectSources<'_>,
    analyses: &[ModuleAnalysis],
) -> (Vec<MacroExport>, Vec<MacroFault>) {
    let mut exports: HashMap<String, MacroExport> = HashMap::new();
    let mut collided: HashSet<String> = HashSet::new();
    let mut faults: Vec<MacroFault> = Vec::new();
    for analysis in analyses {
        let source: &MacroModuleSource = &project.sources[analysis.file_index];
        let Ok(Ok(module)) = project.parsed(analysis.file_index) else {
            continue;
        };
        let digest: String = source_digest(&source.contents);
        for function in top_level_functions(module) {
            let name: &str = function.name.as_str();
            if !is_public(name) {
                continue;
            }
            let item: MacroExport = MacroExport {
                name: name.to_owned(),
                file_index: analysis.file_index,
                parameters: parameter_names(function),
                line: definition_line(&source.contents, function),
                source_digest: digest.clone(),
                dependencies: analysis.dependencies[name].clone(),
            };
            let display: &str = &source.relative_path.display;
            if let Some(existing) = exports.remove(name) {
                collided.insert(name.to_owned());
                faults.push(MacroFault {
                    file_index: analysis.file_index,
                    message: format!(
                        "Macro name collision for '{name}': {} and {display}",
                        project.sources[existing.file_index].relative_path.display
                    ),
                });
            } else if collided.contains(name) {
                faults.push(MacroFault {
                    file_index: analysis.file_index,
                    message: format!("Macro name collision for '{name}' at {display}"),
                });
            } else {
                exports.insert(name.to_owned(), item);
            }
        }
    }
    let mut exports: Vec<MacroExport> = exports.into_values().collect();
    exports.sort_by(|left, right| {
        (
            &left.name,
            &project.sources[left.file_index].relative_path.posix,
        )
            .cmp(&(
                &right.name,
                &project.sources[right.file_index].relative_path.posix,
            ))
    });
    (exports, faults)
}

/// Groups of modules in `subset` sharing a module name, by name, each in discovery order.
fn module_path_collisions(
    project: &ProjectSources<'_>,
    subset: &[usize],
) -> Vec<(String, Vec<usize>)> {
    let mut grouped: HashMap<String, Vec<usize>> = HashMap::new();
    for index in subset {
        grouped
            .entry(module_name(&project.sources[*index]))
            .or_default()
            .push(*index);
    }
    let mut collisions: Vec<(String, Vec<usize>)> = grouped
        .into_iter()
        .filter(|(_, files)| files.len() > 1)
        .collect();
    collisions.sort_by(|left, right| left.0.cmp(&right.0));
    collisions
}

fn deduplicated(project: &ProjectSources<'_>, faults: Vec<MacroFault>) -> Vec<MacroFault> {
    let mut seen: HashSet<(String, String)> = HashSet::new();
    faults
        .into_iter()
        .filter(|fault| {
            seen.insert((
                project.sources[fault.file_index]
                    .relative_path
                    .posix
                    .clone(),
                fault.message.clone(),
            ))
        })
        .collect()
}

/// The module a failure is attributed to: the first whose path the message names.
fn fault_file(project: &ProjectSources<'_>, subset: &[usize], message: &str) -> usize {
    subset
        .iter()
        .copied()
        .find(|index| message.contains(project.sources[*index].relative_path.posix.as_str()))
        .unwrap_or(subset[0])
}

/// Re-analyse without each failing module until the rest analyse cleanly.
fn tolerant_inventory(
    project: &ProjectSources<'_>,
    first_failure: String,
) -> Result<MacroModuleInventory, MacroModuleParseError> {
    let mut remaining: Vec<usize> = (0..project.sources.len()).collect();
    let mut faults: Vec<MacroFault> = Vec::new();
    let mut failure: Option<String> = Some(first_failure);
    while !remaining.is_empty() {
        let outcome: Result<Vec<ModuleAnalysis>, MacroAnalysisFailure> = match failure.take() {
            Some(message) => Err(MacroAnalysisFailure::Compile(message)),
            None => analyze_project(project, &remaining),
        };
        let message: String = match outcome {
            Ok(analyses) => {
                let (exports, inventory_faults) = inventory_from_analyses(project, &analyses);
                faults.extend(inventory_faults);
                return Ok(MacroModuleInventory {
                    exports,
                    faults: deduplicated(project, faults),
                    modules: None,
                });
            }
            Err(MacroAnalysisFailure::Native(error)) => return Err(error),
            Err(MacroAnalysisFailure::Compile(message)) => message,
        };
        let collisions: Vec<(String, Vec<usize>)> = module_path_collisions(project, &remaining);
        if collisions.is_empty() {
            let file_index: usize = fault_file(project, &remaining, &message);
            let posix: &str = &project.sources[file_index].relative_path.posix;
            faults.push(MacroFault {
                file_index,
                message,
            });
            remaining.retain(|index| project.sources[*index].relative_path.posix != posix);
            continue;
        }
        let mut collided: HashSet<&str> = HashSet::new();
        for (name, files) in &collisions {
            let paths: Vec<&str> = files
                .iter()
                .map(|index| project.sources[*index].relative_path.display.as_str())
                .collect();
            let paths: String = paths.join(" and ");
            for index in files {
                collided.insert(&project.sources[*index].relative_path.posix);
                faults.push(MacroFault {
                    file_index: *index,
                    message: format!("Macro module path collision for '{name}': {paths}"),
                });
            }
        }
        remaining.retain(|index| {
            !collided.contains(project.sources[*index].relative_path.posix.as_str())
        });
    }
    Ok(MacroModuleInventory {
        exports: Vec::new(),
        faults: deduplicated(project, faults),
        modules: None,
    })
}

/// The inventory of every module, with the load plan when the strict analysis passes.
pub(crate) fn project_inventory(
    project: &ProjectSources<'_>,
) -> Result<MacroModuleInventory, MacroModuleParseError> {
    let all: Vec<usize> = (0..project.sources.len()).collect();
    match analyze_project(project, &all) {
        Ok(analyses) => {
            let (exports, faults) = inventory_from_analyses(project, &analyses);
            let modules: Vec<MacroModuleLoad> = analyses
                .into_iter()
                .map(|analysis| MacroModuleLoad {
                    file_index: analysis.file_index,
                    module_name: analysis.name,
                    module_dependencies: analysis.module_dependencies,
                })
                .collect();
            Ok(MacroModuleInventory {
                exports,
                faults,
                modules: Some(modules),
            })
        }
        Err(MacroAnalysisFailure::Native(error)) => Err(error),
        Err(MacroAnalysisFailure::Compile(message)) => tolerant_inventory(project, message),
    }
}
