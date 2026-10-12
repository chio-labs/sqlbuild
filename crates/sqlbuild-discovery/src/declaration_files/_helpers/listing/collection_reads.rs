//! Read and parse the files of one collection into its retained native form.

use crate::declaration_files::_helpers::listing::collections::{
    NamedKind, declaration_files, file_name, function_files, named_declaration_files, read_files,
    seed_files,
};
use crate::declaration_files::_helpers::parsing::audit_files::parse_audit_file;
use crate::declaration_files::_helpers::parsing::constant_files::parse_constant_file;
use crate::declaration_files::_helpers::parsing::enum_files::parse_enum_file;
use crate::declaration_files::_helpers::parsing::function_files::parse_function_file;
use crate::declaration_files::_helpers::parsing::hook_files::parse_hook_file;
use crate::declaration_files::_helpers::parsing::schema_files::parse_schema_file;
use crate::declaration_files::models::{
    CollectionFailure, CollectionKind, CollectionRequest, DeclarationCollection,
    DeclarationFileOptions, DiscoverySession, MacroFile, ScopedFile, SeedFile,
};
use crate::declarations::models::DeclarationKind;
use crate::models::{DiscoveredFile, FileOutcome, ProjectRoot, StageFailure};
use crate::tree::models::ProjectTree;

/// The project a collection is read from and the options its parsers use.
pub(crate) struct CollectionSource<'a> {
    pub(crate) session: &'a DiscoverySession,
    pub(crate) tree: &'a ProjectTree,
}

/// Read and parse the collection `request` names.
pub(crate) fn read_collection(
    source: &CollectionSource<'_>,
    request: CollectionRequest,
) -> DeclarationCollection {
    let tree: &ProjectTree = source.tree;
    let root: &ProjectRoot = &source.session.root;
    let options: &DeclarationFileOptions = &source.session.options;
    let isolate_kind: bool = request.isolate_kind;
    match request.kind {
        CollectionKind::Enums => DeclarationCollection::Enums(
            declaration_files(source, DeclarationKind::Enum, isolate_kind).map(|files| {
                read_files(root, tree, files, |file_path, _, contents| {
                    parse_enum_file(file_path, contents)
                })
            }),
        ),
        CollectionKind::Constants => DeclarationCollection::Constants(
            declaration_files(source, DeclarationKind::Constant, isolate_kind).map(|files| {
                read_files(root, tree, files, |file_path, _, contents| {
                    parse_constant_file(file_path, contents)
                })
            }),
        ),
        CollectionKind::Macros => DeclarationCollection::Macros(
            declaration_files(source, DeclarationKind::Macro, isolate_kind).map(|files| {
                read_files(root, tree, files, |_, _, contents| {
                    Ok(MacroFile { contents })
                })
            }),
        ),
        CollectionKind::ModelSchemas => DeclarationCollection::ModelSchemas(
            named_declaration_files(source, &[NamedKind::Schema], false).map(|files| {
                read_files(root, tree, files, |file_path, _, contents| {
                    parse_schema_file(file_path, contents)
                })
            }),
        ),
        CollectionKind::Audits => DeclarationCollection::Audits(
            named_declaration_files(source, &[NamedKind::Audit, NamedKind::SingularAudit], false)
                .map(|files| {
                    read_files(root, tree, files, |file_path, _, contents| {
                        parse_audit_file(file_path, contents, options)
                    })
                }),
        ),
        CollectionKind::SqlHooks => DeclarationCollection::SqlHooks(
            named_declaration_files(source, &[NamedKind::SqlHook], true).map(|files| {
                read_files(root, tree, files, |file_path, relative_path, contents| {
                    parse_hook_file(file_path, stem(file_name(relative_path)), contents, options)
                })
            }),
        ),
        CollectionKind::SqlFunctions => {
            DeclarationCollection::SqlFunctions(function_files(tree).map(|files| {
                read_files(root, tree, files, |file_path, _, contents| {
                    parse_function_file(file_path, contents, options)
                })
            }))
        }
        CollectionKind::Seeds => DeclarationCollection::Seeds(
            seed_files(tree).map(|paths| paths.into_iter().map(seed_file).collect()),
        ),
    }
}

fn seed_file(relative_path: String) -> ScopedFile<SeedFile> {
    ScopedFile {
        file: DiscoveredFile {
            relative_path,
            outcome: FileOutcome::Parsed(SeedFile),
        },
        scope: None,
    }
}

/// The collection `kind` failing as a whole.
pub(crate) fn failed_collection(
    kind: CollectionKind,
    failure: StageFailure,
) -> DeclarationCollection {
    let failure = CollectionFailure::Stage(failure);
    match kind {
        CollectionKind::Enums => DeclarationCollection::Enums(Err(failure)),
        CollectionKind::Constants => DeclarationCollection::Constants(Err(failure)),
        CollectionKind::ModelSchemas => DeclarationCollection::ModelSchemas(Err(failure)),
        CollectionKind::SqlFunctions => DeclarationCollection::SqlFunctions(Err(failure)),
        CollectionKind::SqlHooks => DeclarationCollection::SqlHooks(Err(failure)),
        CollectionKind::Audits => DeclarationCollection::Audits(Err(failure)),
        CollectionKind::Seeds => DeclarationCollection::Seeds(Err(failure)),
        CollectionKind::Macros => DeclarationCollection::Macros(Err(failure)),
    }
}

/// Python's `Path.stem` of a file name.
fn stem(file_name: &str) -> &str {
    match file_name.rfind('.') {
        Some(index) if index > 0 && index + 1 < file_name.len() => &file_name[..index],
        _ => file_name,
    }
}
