//! Discovery + render floor: a minimal native pass that discovers a project, layers model config,
//! substitutes vars, expands `@const`/`@enum`, calls user Python macros through an embedded
//! interpreter (memoised, plain data only) and extracts references.
//!
//! Usage: render_floor PROJECT_DIR [--threads N] [--runs R] [--verify RENDER_JSON]
//!                     [--site-packages DIR] [--target NAME]
//!
//! Models using constructs this PoC does not implement are counted as unhandled, never faked.

#![allow(clippy::type_complexity)]

use _native::poc::{self, HeaderValue};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use rayon::prelude::*;
use sqlbuild_floor::pylit::{Lit, Parser};
use sqlbuild_floor::scan;
use sqlbuild_floor::{load_average, median, pool, process_cpu_seconds};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::time::Instant;

const ROLE_DIRS: [&str; 12] = [
    "macros",
    "_macros",
    "constants",
    "_constants",
    "enums",
    "_enums",
    "audits",
    "_audits",
    "schemas",
    "_schemas",
    "hooks",
    "_hooks",
];

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Role {
    Macro,
    Constant,
    Enum,
    Other,
}

/// Where a declaration is visible: the owner directory and whether it is owner-private.
#[derive(Clone, Debug)]
struct Scope {
    owner: PathBuf,
    private: bool,
    global: bool,
}

impl Scope {
    fn visible_from(&self, model_dir: &Path) -> bool {
        self.global
            || if self.private {
                model_dir == self.owner
            } else {
                model_dir.starts_with(&self.owner)
            }
    }
    fn depth(&self) -> usize {
        if self.global {
            0
        } else {
            self.owner.components().count()
        }
    }
}

#[derive(Clone, Debug)]
enum Value {
    Str(String),
    Int(String),
    Float(String),
    Bool(bool),
    Null,
    List(Vec<Value>),
}

#[derive(Clone, Debug)]
struct Constant {
    value: Value,
    render_as_array: bool,
}

struct DeclFile {
    path: PathBuf,
    role: Role,
    scope: Scope,
}

struct ModelFile {
    name: String,
    relative: PathBuf,
    dir: PathBuf,
}

struct Project {
    root: PathBuf,
    adapter: String,
    target_name: String,
    defaults: toml::Table,
    path_defaults: Vec<(String, toml::Table)>,
    vars: Vec<(String, String)>,
    vars_table: toml::Table,
    target_database: Option<String>,
    target_schema: Option<String>,
}

fn resolve_template(text: &str) -> String {
    let Some(inner) = text.strip_prefix("${").and_then(|t| t.strip_suffix('}')) else {
        return text.to_owned();
    };
    let lookup = |part: &str| -> Option<String> {
        let part = part.trim();
        if let Some(name) = part.strip_prefix("ENV:") {
            return std::env::var(name).ok();
        }
        part.strip_prefix('\'')
            .and_then(|p| p.strip_suffix('\''))
            .map(str::to_owned)
    };
    if let Some(args) = inner
        .strip_prefix("coalesce(")
        .and_then(|t| t.strip_suffix(')'))
    {
        return args.split(',').find_map(lookup).unwrap_or_default();
    }
    lookup(inner).unwrap_or_default()
}

fn load_project(root: &Path, target: Option<&str>) -> Project {
    let mut text =
        std::fs::read_to_string(root.join("sqlbuild_project.toml")).expect("project toml");
    if let Ok(local) = std::fs::read_to_string(root.join("sqlbuild_local.toml")) {
        // Local overrides only matter here for vars and targets; append as extra tables when
        // they do not redefine existing keys (PoC simplification, reported).
        let _ = local;
    }
    text.push('\n');
    let table: toml::Table = text.parse().expect("toml");
    let section = |name: &str| {
        table
            .get(name)
            .and_then(|v| v.as_table())
            .cloned()
            .unwrap_or_default()
    };
    let target_name = target
        .map(str::to_owned)
        .or_else(|| {
            table
                .get("default_target")
                .and_then(|v| v.as_str())
                .map(str::to_owned)
        })
        .unwrap_or_default();
    let target = section("targets")
        .get(&target_name)
        .and_then(|v| v.as_table())
        .cloned()
        .unwrap_or_default();
    let vars_table = section("vars");
    let vars = vars_table
        .iter()
        .filter_map(|(name, value)| match value {
            toml::Value::String(s) => Some((name.clone(), s.clone())),
            toml::Value::Integer(i) => Some((name.clone(), i.to_string())),
            toml::Value::Float(f) => Some((name.clone(), f.to_string())),
            toml::Value::Boolean(b) => Some((name.clone(), b.to_string())),
            _ => None,
        })
        .collect();
    Project {
        root: root.to_owned(),
        adapter: table
            .get("adapter")
            .and_then(|v| v.as_str())
            .unwrap_or("duckdb")
            .to_owned(),
        target_name,
        defaults: section("defaults"),
        path_defaults: section("path_defaults")
            .into_iter()
            .filter_map(|(key, value)| value.as_table().cloned().map(|t| (key, t)))
            .collect(),
        vars,
        vars_table,
        target_database: target
            .get("database")
            .and_then(|v| v.as_str())
            .map(resolve_template),
        target_schema: target
            .get("schema")
            .and_then(|v| v.as_str())
            .map(resolve_template),
    }
}

/// Classify a project file. Returns (role, scope) for declarations, or None.
fn classify(relative: &Path) -> Option<(Role, Scope)> {
    let parts: Vec<&str> = relative.iter().filter_map(|p| p.to_str()).collect();
    let role_of = |dir: &str| match dir.trim_start_matches('_') {
        "macros" => Role::Macro,
        "constants" => Role::Constant,
        "enums" => Role::Enum,
        _ => Role::Other,
    };
    if parts.len() >= 2 && matches!(parts[0], "macros" | "constants" | "enums") {
        return Some((
            role_of(parts[0]),
            Scope {
                owner: PathBuf::new(),
                private: false,
                global: true,
            },
        ));
    }
    if parts.first() != Some(&"models") {
        return None;
    }
    if let Some(position) = parts.iter().position(|p| *p == "_sqlbuild")
        && position + 2 < parts.len()
    {
        let role = parts[position + 1];
        return Some((
            role_of(role),
            Scope {
                owner: parts[..position].iter().collect(),
                private: role.starts_with('_'),
                global: false,
            },
        ));
    }
    for (position, part) in parts.iter().enumerate().take(parts.len() - 1).skip(1) {
        if ROLE_DIRS.contains(part) {
            return Some((
                role_of(part),
                Scope {
                    owner: parts[..position].iter().collect(),
                    private: part.starts_with('_'),
                    global: false,
                },
            ));
        }
    }
    None
}

struct Discovery {
    models: Vec<ModelFile>,
    decls: Vec<DeclFile>,
    python_models: usize,
}

fn discover(project: &Project) -> Discovery {
    let mut models = Vec::new();
    let mut decls = Vec::new();
    let mut python_models = 0;
    let walker = walkdir::WalkDir::new(&project.root)
        .sort_by_file_name()
        .into_iter()
        .filter_entry(|entry| {
            let name = entry.file_name().to_string_lossy();
            entry.depth() == 0
                || !(name.starts_with('.')
                    || name == "__pycache__"
                    || (entry.depth() == 1 && matches!(name.as_ref(), "target" | "logs")))
        });
    for entry in walker.flatten() {
        if !entry.file_type().is_file() {
            continue;
        }
        let relative = entry
            .path()
            .strip_prefix(&project.root)
            .unwrap_or(entry.path())
            .to_owned();
        let extension = relative
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or_default()
            .to_owned();
        if let Some((role, scope)) = classify(&relative) {
            let wanted = match role {
                Role::Macro => extension == "py",
                Role::Constant | Role::Enum => extension == "sql",
                Role::Other => false,
            };
            if wanted {
                decls.push(DeclFile {
                    path: entry.path().to_owned(),
                    role,
                    scope,
                });
            }
            continue;
        }
        if relative.starts_with("models") {
            match extension.as_str() {
                "sql" => models.push(ModelFile {
                    name: relative
                        .file_stem()
                        .and_then(|s| s.to_str())
                        .unwrap_or_default()
                        .to_owned(),
                    dir: relative.parent().map(Path::to_owned).unwrap_or_default(),
                    relative,
                }),
                "py" => python_models += 1,
                _ => {}
            }
        }
    }
    Discovery {
        models,
        decls,
        python_models,
    }
}

fn header_get<'a>(map: &'a [(String, HeaderValue)], key: &str) -> Option<&'a HeaderValue> {
    map.iter().find(|(k, _)| k == key).map(|(_, v)| v)
}

fn scalar(value: &HeaderValue) -> Option<String> {
    match value {
        HeaderValue::BareWord(s) | HeaderValue::String(s) => Some(s.clone()),
        HeaderValue::Boolean(b) => Some(b.to_string()),
        _ => None,
    }
}

fn constant_value(value: &HeaderValue) -> Option<Value> {
    Some(match value {
        HeaderValue::String(s) => Value::Str(s.clone()),
        HeaderValue::BareWord(word) => {
            if word.parse::<i64>().is_ok() {
                Value::Int(word.clone())
            } else if word.parse::<f64>().is_ok() {
                Value::Float(word.clone())
            } else {
                return None;
            }
        }
        HeaderValue::Boolean(b) => Value::Bool(*b),
        HeaderValue::Null => Value::Null,
        HeaderValue::List(items) | HeaderValue::Set(items) => Value::List(
            items
                .iter()
                .map(constant_value)
                .collect::<Option<Vec<_>>>()?,
        ),
        _ => return None,
    })
}

/// Parse every `KEYWORD ( ... );` statement in a declaration file.
fn declaration_bodies<'a>(text: &'a str, keyword: &str) -> Vec<&'a str> {
    let bytes = text.as_bytes();
    let mut bodies = Vec::new();
    let mut index = 0;
    while let Some(offset) = text[index..].find(keyword) {
        let start = index + offset + keyword.len();
        let open = scan::skip_ws(bytes, start);
        if bytes.get(open) != Some(&b'(') {
            index = start;
            continue;
        }
        let Some(close) = scan::matching_paren(bytes, open) else {
            break;
        };
        bodies.push(&text[open + 1..close]);
        index = close + 1;
    }
    bodies
}

struct Declarations {
    constants: Vec<(String, Constant, Scope)>,
    enums: Vec<(String, Vec<(String, String)>, Scope)>,
    unsupported: usize,
}

fn parse_declarations(decls: &[DeclFile]) -> Declarations {
    let parsed: Vec<(
        Vec<(String, Constant, Scope)>,
        Vec<(String, Vec<(String, String)>, Scope)>,
        usize,
    )> = decls
        .par_iter()
        .filter(|d| matches!(d.role, Role::Constant | Role::Enum))
        .map(|decl| {
            let text = std::fs::read_to_string(&decl.path).unwrap_or_default();
            let mut constants = Vec::new();
            let mut enums = Vec::new();
            let mut unsupported = 0;
            let keyword = if decl.role == Role::Constant {
                "CONSTANT"
            } else {
                "ENUM"
            };
            for body in declaration_bodies(&text, keyword) {
                let Ok(HeaderValue::Map(map)) = poc::parse_header(body) else {
                    unsupported += 1;
                    continue;
                };
                let Some(name) = header_get(&map, "name").and_then(scalar) else {
                    unsupported += 1;
                    continue;
                };
                if decl.role == Role::Constant {
                    match header_get(&map, "value").and_then(constant_value) {
                        Some(value) => constants.push((
                            name,
                            Constant {
                                value,
                                render_as_array: header_get(&map, "render_as")
                                    .and_then(scalar)
                                    .as_deref()
                                    == Some("array"),
                            },
                            decl.scope.clone(),
                        )),
                        None => unsupported += 1,
                    }
                } else if let Some(HeaderValue::Map(members)) = header_get(&map, "members") {
                    let members = members
                        .iter()
                        .filter_map(|(member, value)| scalar(value).map(|v| (member.clone(), v)))
                        .collect();
                    enums.push((name, members, decl.scope.clone()));
                } else {
                    unsupported += 1;
                }
            }
            (constants, enums, unsupported)
        })
        .collect();
    let mut out = Declarations {
        constants: Vec::new(),
        enums: Vec::new(),
        unsupported: 0,
    };
    for (constants, enums, unsupported) in parsed {
        out.constants.extend(constants);
        out.enums.extend(enums);
        out.unsupported += unsupported;
    }
    out
}

fn render_scalar(value: &Value) -> String {
    match value {
        Value::Str(s) => format!("'{}'", s.replace('\'', "''")),
        Value::Int(s) | Value::Float(s) => s.clone(),
        Value::Bool(b) => {
            if *b {
                "TRUE".into()
            } else {
                "FALSE".into()
            }
        }
        Value::Null => "NULL".into(),
        Value::List(_) => String::new(),
    }
}

fn render_constant(constant: &Constant, adapter: &str) -> Option<String> {
    match &constant.value {
        Value::List(items) => {
            let parts: Vec<String> = items.iter().map(render_scalar).collect();
            if constant.render_as_array {
                match adapter {
                    "snowflake" => Some(format!("ARRAY_CONSTRUCT({})", parts.join(", "))),
                    "duckdb" | "postgres" => Some(format!("[{}]", parts.join(", "))),
                    _ => None,
                }
            } else {
                Some(format!("({})", parts.join(", ")))
            }
        }
        scalar => Some(render_scalar(scalar)),
    }
}

/// One user macro as loaded by the embedded interpreter.
struct Macro {
    file: usize,
    function: Py<PyAny>,
    injects_ctx: bool,
}

#[derive(Clone)]
struct CallSpec {
    macro_index: usize,
    positional: Vec<Lit>,
    keywords: Vec<(String, Lit)>,
    /// Visible-declaration scope (owner dir) when the macro reads ctx, else empty.
    ctx_scope: Option<PathBuf>,
}

enum Segment {
    Text(String),
    Call(String),
}

struct Rendered {
    name: String,
    segments: Vec<Segment>,
    calls: Vec<(String, CallSpec)>,
    macro_deps: Vec<String>,
    config: BTreeMap<String, serde_json::Value>,
    unhandled: Option<String>,
}

struct Context<'a> {
    project: &'a Project,
    decls: &'a Declarations,
    macros: &'a [Macro],
    /// (macro name, scope) for every exported macro function.
    macro_names: &'a [(String, Scope, usize)],
}

impl Context<'_> {
    fn constant(&self, name: &str, dir: &Path, private: &[(String, Constant)]) -> Option<Constant> {
        if let Some((_, c)) = private.iter().find(|(n, _)| n == name) {
            return Some(c.clone());
        }
        self.decls
            .constants
            .iter()
            .filter(|(n, _, scope)| n == name && scope.visible_from(dir))
            .max_by_key(|(_, _, scope)| scope.depth())
            .map(|(_, c, _)| c.clone())
    }

    fn enum_member(&self, name: &str, member: &str, dir: &Path) -> Option<String> {
        self.decls
            .enums
            .iter()
            .filter(|(n, _, scope)| n == name && scope.visible_from(dir))
            .max_by_key(|(_, _, scope)| scope.depth())
            .and_then(|(_, members, _)| members.iter().find(|(m, _)| m == member))
            .map(|(_, v)| match v.parse::<i64>() {
                Ok(i) => i.to_string(),
                Err(_) => format!("'{}'", v.replace('\'', "''")),
            })
    }

    fn macro_for(&self, name: &str, dir: &Path) -> Option<usize> {
        self.macro_names
            .iter()
            .filter(|(n, scope, _)| n == name && scope.visible_from(dir))
            .max_by_key(|(_, scope, _)| scope.depth())
            .map(|(_, _, index)| *index)
    }
}

fn layer_config(
    project: &Project,
    model: &ModelFile,
    header: &[(String, HeaderValue)],
) -> BTreeMap<String, serde_json::Value> {
    use serde_json::Value as J;
    let mut config: BTreeMap<String, J> = BTreeMap::new();
    let toml_json = |v: &toml::Value| serde_json::to_value(v).unwrap_or(J::Null);
    for key in ["materialized", "database", "schema", "contract"] {
        if let Some(v) = project.defaults.get(key) {
            config.insert(key.into(), toml_json(v));
        }
    }
    let default_tags: Vec<J> = project
        .defaults
        .get("tags")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().map(toml_json).collect())
        .unwrap_or_default();
    // Nearest path default: literal keys beat wildcards; more literal segments win.
    let path = model.relative.to_string_lossy().replace('\\', "/");
    let normalized = path.strip_prefix("models/").unwrap_or(&path).to_owned();
    let parts: Vec<&str> = normalized.split('/').collect();
    let matched = project
        .path_defaults
        .iter()
        .filter(|(key, _)| path_key_matches(key, &parts))
        .max_by_key(|(key, _)| {
            let segments: Vec<&str> = key.split('/').collect();
            let wildcard = key.contains('*');
            (
                !wildcard,
                segments.iter().filter(|s| !s.contains('*')).count(),
                segments.len(),
            )
        });
    if let Some((_, table)) = matched {
        for (key, value) in table {
            config.insert(key.clone(), toml_json(value));
        }
    }
    if let Some(database) = &project.target_database {
        config.insert("database".into(), J::String(database.clone()));
    }
    if let Some(schema) = &project.target_schema
        && schema != "preserve"
    {
        config.insert("schema".into(), J::String(schema.clone()));
    }
    let mut tags = default_tags;
    for (key, value) in header {
        match (key.as_str(), value) {
            ("materialized" | "contract" | "schema" | "database", v) => {
                if let Some(s) = scalar(v) {
                    config.insert(key.clone(), J::String(s));
                }
            }
            ("tags", HeaderValue::List(items)) => {
                for item in items.iter().filter_map(scalar) {
                    if !tags.contains(&J::String(item.clone())) {
                        tags.push(J::String(item));
                    }
                }
            }
            _ => {}
        }
    }
    if !tags.is_empty() {
        config.insert("tags".into(), J::Array(tags));
    }
    config
}

fn path_key_matches(key: &str, parts: &[&str]) -> bool {
    fn glob(pattern: &str, text: &str) -> bool {
        match pattern.split_once('*') {
            None => pattern == text,
            Some((prefix, rest)) => {
                text.starts_with(prefix)
                    && (0..=text.len() - prefix.len())
                        .any(|i| glob(rest, &text[prefix.len() + i..]))
            }
        }
    }
    fn walk(key: &[&str], parts: &[&str]) -> bool {
        match key.first() {
            None => true,
            Some(&"**") => (0..=parts.len()).any(|skip| walk(&key[1..], &parts[skip..])),
            Some(segment) => {
                parts.first().is_some_and(|p| glob(segment, p)) && walk(&key[1..], &parts[1..])
            }
        }
    }
    let key_parts: Vec<&str> = key.trim_end_matches('/').split('/').collect();
    walk(&key_parts, parts)
}

/// Phase A for one model: config, vars, declarations, macro call discovery.
fn render_model(ctx: &Context<'_>, model: &ModelFile, text: &str) -> Rendered {
    let mut out = Rendered {
        name: model.name.clone(),
        segments: Vec::new(),
        calls: Vec::new(),
        macro_deps: Vec::new(),
        config: BTreeMap::new(),
        unhandled: None,
    };
    let (header, sql) = match poc::match_model_header(text) {
        Some((start, end, sql_start)) => (&text[start..end], &text[sql_start..]),
        None => {
            out.unhandled = Some("no MODEL header".into());
            return out;
        }
    };
    let header = match poc::parse_header(header) {
        Ok(HeaderValue::Map(map)) => map,
        _ => {
            out.unhandled = Some("header parse".into());
            return out;
        }
    };
    out.config = layer_config(ctx.project, model, &header);
    let private_constants: Vec<(String, Constant)> = match header_get(&header, "constants") {
        Some(HeaderValue::Map(entries)) => entries
            .iter()
            .filter_map(|(name, value)| {
                constant_value(value).map(|v| {
                    (
                        name.clone(),
                        Constant {
                            value: v,
                            render_as_array: false,
                        },
                    )
                })
            })
            .collect(),
        _ => Vec::new(),
    };
    // Vars.
    let mut sql = sql.trim_end().to_owned();
    if sql.contains("@@") {
        match poc::substitute_vars(&sql, &ctx.project.vars) {
            (1, Some(substituted)) => sql = substituted,
            (0, _) => {}
            _ => {
                out.unhandled = Some("vars fallback (non-scalar or ENV/CTX)".into());
                return out;
            }
        }
    }
    // Declarations: @const("x") and @enum("x").MEMBER.
    if sql.contains("@const") || sql.contains("@enum") {
        let bytes = sql.as_bytes();
        let mut result = String::with_capacity(sql.len());
        let mut cursor = 0;
        let mut search = 0;
        while let Some((start, name, open)) = scan::next_call(bytes, search) {
            search = start + 1;
            if name != "const" && name != "enum" {
                continue;
            }
            let Some(close) = scan::matching_paren(bytes, open) else {
                break;
            };
            let argument = sql[open + 1..close].trim();
            let declared = argument.trim_matches(|c| c == '"' || c == '\'');
            let (replacement, end) = if name == "const" {
                match ctx
                    .constant(declared, &model.dir, &private_constants)
                    .and_then(|c| render_constant(&c, &ctx.project.adapter))
                {
                    Some(rendered) => (rendered, close + 1),
                    None => {
                        out.unhandled =
                            Some(format!("constant '{declared}' unresolved or unsupported"));
                        return out;
                    }
                }
            } else {
                let after = scan::skip_ws(bytes, close + 1);
                if bytes.get(after) != Some(&b'.') {
                    out.unhandled = Some("enum reference form".into());
                    return out;
                }
                let member_start = scan::skip_ws(bytes, after + 1);
                let mut member_end = member_start;
                while member_end < bytes.len() && scan::is_ident_continue(bytes[member_end]) {
                    member_end += 1;
                }
                match ctx.enum_member(declared, &sql[member_start..member_end], &model.dir) {
                    Some(rendered) => (rendered, member_end),
                    None => {
                        out.unhandled = Some("enum unresolved".into());
                        return out;
                    }
                }
            };
            result.push_str(&sql[cursor..start]);
            result.push_str(&replacement);
            cursor = end;
            search = end;
        }
        result.push_str(&sql[cursor..]);
        sql = result;
    }
    // Macros: split into text and call segments; nested calls become placeholders.
    let bytes = sql.as_bytes();
    let mut cursor = 0;
    while let Some((start, name, open)) = scan::next_call(bytes, cursor) {
        let Some(close) = scan::matching_paren(bytes, open) else {
            out.unhandled = Some("unbalanced macro call".into());
            return out;
        };
        match macro_call(ctx, model, &sql, &name, open, close, &mut out) {
            Ok(key) => {
                out.segments
                    .push(Segment::Text(sql[cursor..start].to_owned()));
                out.segments.push(Segment::Call(key));
            }
            Err(reason) => {
                out.unhandled = Some(reason);
                return out;
            }
        }
        cursor = close + 1;
    }
    out.segments.push(Segment::Text(sql[cursor..].to_owned()));
    out
}

fn macro_call(
    ctx: &Context<'_>,
    model: &ModelFile,
    sql: &str,
    name: &str,
    open: usize,
    close: usize,
    out: &mut Rendered,
) -> Result<String, String> {
    let macro_index = ctx
        .macro_for(name, &model.dir)
        .ok_or_else(|| format!("macro '@{name}' not found"))?;
    if !out.macro_deps.iter().any(|d| d == name) {
        out.macro_deps.push(name.to_owned());
    }
    // Rewrite nested calls inside the arguments first.
    let arguments = &sql[open + 1..close];
    let bytes = arguments.as_bytes();
    let mut rewritten = String::new();
    let mut placeholders: Vec<(String, String)> = Vec::new();
    let mut cursor = 0;
    while let Some((start, nested, nested_open)) = scan::next_call(bytes, cursor) {
        let nested_close =
            scan::matching_paren(bytes, nested_open).ok_or("unbalanced nested call")?;
        let key = macro_call(
            ctx,
            model,
            arguments,
            &nested,
            nested_open,
            nested_close,
            out,
        )?;
        let placeholder = format!("__sqlbuild_macro_arg_{}", placeholders.len());
        rewritten.push_str(&arguments[cursor..start]);
        rewritten.push_str(&placeholder);
        placeholders.push((placeholder, key));
        cursor = nested_close + 1;
    }
    rewritten.push_str(&arguments[cursor..]);
    if rewritten.contains("__ref(")
        || rewritten.contains("__source(")
        || rewritten.contains("__seed(")
    {
        return Err("typed relation reference in macro arguments".into());
    }
    let args = Parser::parse_args(&rewritten, &placeholders)?;
    let ctx_scope = ctx.macros[macro_index]
        .injects_ctx
        .then(|| model.dir.clone());
    let mut key = format!("{}:{name}|", ctx.macros[macro_index].file);
    for value in &args.positional {
        value.key(&mut key);
        key.push(',');
    }
    for (keyword, value) in &args.keywords {
        key.push_str(keyword);
        key.push('=');
        value.key(&mut key);
        key.push(',');
    }
    if let Some(scope) = &ctx_scope {
        key.push('|');
        key.push_str(&scope.to_string_lossy());
    }
    out.calls.push((
        key.clone(),
        CallSpec {
            macro_index,
            positional: args.positional,
            keywords: args.keywords,
            ctx_scope,
        },
    ));
    Ok(key)
}

const PY_HELPERS: &str = r#"
import importlib.util, inspect, sys, types

def load(paths):
    out = []
    for index, path in enumerate(paths):
        name = f"_sqb_poc_macros_{index}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        functions = []
        for attr, value in vars(module).items():
            if inspect.isfunction(value) and value.__module__ == name and not attr.startswith("_"):
                params = list(inspect.signature(value).parameters)
                functions.append((attr, value, bool(params) and params[0] == "ctx"))
        out.append(functions)
    return out

def make_ctx(adapter, target, variables, constants):
    return types.SimpleNamespace(adapter_name=adapter, target_name=target, vars=variables,
                                 constants=constants, enums={}, sql_analysis_enabled=True)
"#;

fn lit_to_py<'py>(
    py: Python<'py>,
    value: &Lit,
    results: &HashMap<String, Py<PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    Ok(match value {
        Lit::Str(s) => s.into_pyobject(py)?.into_any(),
        Lit::Int(i) => i.into_pyobject(py)?.into_any(),
        Lit::Float(f) => f
            .parse::<f64>()
            .unwrap_or(0.0)
            .into_pyobject(py)?
            .into_any(),
        Lit::Bool(b) => b.into_pyobject(py)?.to_owned().into_any(),
        Lit::None => py.None().into_bound(py),
        Lit::Nested(key) => results
            .get(key)
            .map(|v| v.bind(py).clone())
            .unwrap_or_else(|| py.None().into_bound(py)),
        Lit::List(items) => PyList::new(
            py,
            items
                .iter()
                .map(|i| lit_to_py(py, i, results))
                .collect::<PyResult<Vec<_>>>()?,
        )?
        .into_any(),
        Lit::Tuple(items) => PyTuple::new(
            py,
            items
                .iter()
                .map(|i| lit_to_py(py, i, results))
                .collect::<PyResult<Vec<_>>>()?,
        )?
        .into_any(),
        Lit::Dict(items) => {
            let dict = PyDict::new(py);
            for (k, v) in items {
                dict.set_item(lit_to_py(py, k, results)?, lit_to_py(py, v, results)?)?;
            }
            dict.into_any()
        }
    })
}

struct PhaseTimes {
    python_init: f64,
    macro_import: f64,
    discovery: f64,
    declarations: f64,
    render: f64,
    macro_calls: f64,
    splice: f64,
    total: f64,
    cpu: f64,
    unique_calls: usize,
    call_sites: usize,
}

struct Output {
    name: String,
    query_sql: Option<String>,
    references: Vec<(String, String, Option<String>)>,
    macro_deps: Vec<String>,
    config: BTreeMap<String, serde_json::Value>,
    unhandled: Option<String>,
}

fn run(
    project_dir: &Path,
    threads: usize,
    site_packages: Option<&str>,
    target: Option<&str>,
) -> (PhaseTimes, Vec<Output>, usize, usize) {
    let thread_pool = pool(threads);
    let cpu0 = process_cpu_seconds();
    let start = Instant::now();
    let t = Instant::now();
    Python::initialize();
    let helpers = Python::attach(|py| -> PyResult<Py<PyAny>> {
        if let Some(site) = site_packages {
            py.import("site")?.call_method1("addsitedir", (site,))?;
        }
        let module = PyModule::from_code(
            py,
            &std::ffi::CString::new(PY_HELPERS).unwrap_or_default(),
            c"_sqb_poc.py",
            c"_sqb_poc",
        )?;
        Ok(module.into_any().unbind())
    })
    .expect("python helpers");
    let python_init = t.elapsed().as_secs_f64();

    let t = Instant::now();
    let project = load_project(project_dir, target);
    let discovery = thread_pool.install(|| discover(&project));
    let texts: Vec<String> = thread_pool.install(|| {
        discovery
            .models
            .par_iter()
            .map(|m| std::fs::read_to_string(project.root.join(&m.relative)).unwrap_or_default())
            .collect()
    });
    let discovery_s = t.elapsed().as_secs_f64();

    let t = Instant::now();
    let decls = thread_pool.install(|| parse_declarations(&discovery.decls));
    let declarations_s = t.elapsed().as_secs_f64();

    // Import user macro modules (the user-extension cost).
    let t = Instant::now();
    let macro_files: Vec<&DeclFile> = discovery
        .decls
        .iter()
        .filter(|d| d.role == Role::Macro)
        .collect();
    let mut macros: Vec<Macro> = Vec::new();
    let mut macro_names: Vec<(String, Scope, usize)> = Vec::new();
    Python::attach(|py| -> PyResult<()> {
        let paths: Vec<String> = macro_files
            .iter()
            .map(|d| d.path.to_string_lossy().into_owned())
            .collect();
        let loaded = helpers.bind(py).getattr("load")?.call1((paths,))?;
        for (file_index, functions) in loaded.try_iter()?.enumerate() {
            for function in functions?.try_iter()? {
                let function = function?;
                let name: String = function.get_item(0)?.extract()?;
                macro_names.push((name, macro_files[file_index].scope.clone(), macros.len()));
                macros.push(Macro {
                    file: file_index,
                    function: function.get_item(1)?.unbind(),
                    injects_ctx: function.get_item(2)?.extract()?,
                });
            }
        }
        Ok(())
    })
    .expect("load macros");
    let macro_import = t.elapsed().as_secs_f64();

    // Phase A (parallel, no Python).
    let t = Instant::now();
    let ctx = Context {
        project: &project,
        decls: &decls,
        macros: &macros,
        macro_names: &macro_names,
    };
    let rendered: Vec<Rendered> = thread_pool.install(|| {
        discovery
            .models
            .par_iter()
            .zip(texts.par_iter())
            .map(|(model, text)| render_model(&ctx, model, text))
            .collect()
    });
    let render_s = t.elapsed().as_secs_f64();

    // Phase B (serial, Python): call each unique macro invocation once.
    let t = Instant::now();
    let mut unique: Vec<(String, CallSpec)> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    let mut call_sites = 0;
    for model in rendered.iter().filter(|r| r.unhandled.is_none()) {
        for (key, spec) in &model.calls {
            call_sites += 1;
            if seen.insert(key.clone()) {
                unique.push((key.clone(), spec.clone()));
            }
        }
    }
    let mut failures: HashMap<String, String> = HashMap::new();
    let results: HashMap<String, String> = Python::attach(|py| {
        let mut objects: HashMap<String, Py<PyAny>> = HashMap::new();
        let mut strings: HashMap<String, String> = HashMap::new();
        let mut ctx_cache: HashMap<PathBuf, Py<PyAny>> = HashMap::new();
        let mut per_macro: HashMap<usize, (usize, f64, f64)> = HashMap::new();
        // Nested calls were pushed before their parents, so a forward pass resolves children first.
        for (key, spec) in &unique {
            let mut call = || -> PyResult<Bound<'_, PyAny>> {
                let mut positional: Vec<Bound<'_, PyAny>> = Vec::new();
                if let Some(scope) = &spec.ctx_scope {
                    let context = match ctx_cache.get(scope) {
                        Some(c) => c.bind(py).clone(),
                        None => {
                            let constants = PyDict::new(py);
                            for (name, constant, scope_of) in &decls.constants {
                                if scope_of.visible_from(scope)
                                    && let Some(value) = py_value(py, &constant.value)
                                {
                                    constants.set_item(name, value)?;
                                }
                            }
                            let variables = PyDict::new(py);
                            for (name, value) in &project.vars_table {
                                variables.set_item(name, value.to_string().trim_matches('"'))?;
                            }
                            let context = helpers.bind(py).getattr("make_ctx")?.call1((
                                project.adapter.as_str(),
                                project.target_name.as_str(),
                                variables,
                                constants,
                            ))?;
                            ctx_cache.insert(scope.clone(), context.clone().unbind());
                            context
                        }
                    };
                    positional.push(context);
                }
                for value in &spec.positional {
                    positional.push(lit_to_py(py, value, &objects)?);
                }
                let kwargs = PyDict::new(py);
                for (keyword, value) in &spec.keywords {
                    kwargs.set_item(keyword, lit_to_py(py, value, &objects)?)?;
                }
                macros[spec.macro_index]
                    .function
                    .bind(py)
                    .call(PyTuple::new(py, positional)?, Some(&kwargs))
            };
            let call_start = Instant::now();
            let outcome = call();
            let elapsed = call_start.elapsed().as_secs_f64();
            let entry = per_macro
                .entry(spec.macro_index)
                .or_insert((0usize, 0.0f64, 0.0f64));
            entry.0 += 1;
            entry.1 += elapsed;
            entry.2 = entry.2.max(elapsed);
            match outcome {
                Ok(value) => {
                    if let Ok(text) = value.extract::<String>() {
                        strings.insert(key.clone(), text);
                    }
                    objects.insert(key.clone(), value.unbind());
                }
                Err(error) => {
                    failures.insert(key.clone(), error.to_string());
                }
            }
        }
        if std::env::var_os("POC_MACRO_PROFILE").is_some() {
            let mut rows: Vec<_> = per_macro.into_iter().collect();
            rows.sort_by(|a, b| b.1.1.total_cmp(&a.1.1));
            for (index, (count, total, max)) in rows.into_iter().take(8) {
                let name = macro_names
                    .iter()
                    .find(|(_, _, i)| *i == index)
                    .map(|(n, _, _)| n.as_str())
                    .unwrap_or("?");
                println!("  macro {name}: calls {count} total {total:.4}s max {max:.4}s");
            }
        }
        strings
    });
    let macro_calls_s = t.elapsed().as_secs_f64();

    // Phase C (parallel): splice macro output, extract references.
    let t = Instant::now();
    let outputs: Vec<Output> =
        thread_pool.install(|| {
            rendered
                .into_par_iter()
                .map(|model| {
                    let mut unhandled = model.unhandled.clone();
                    let mut sql = String::new();
                    if unhandled.is_none() {
                        for segment in &model.segments {
                            match segment {
                                Segment::Text(text) => sql.push_str(text),
                                Segment::Call(key) => match results.get(key) {
                                    Some(text) => sql.push_str(text),
                                    None => {
                                        unhandled =
                                            Some(failures.get(key).cloned().unwrap_or_else(|| {
                                                "macro returned non-string".into()
                                            }));
                                        break;
                                    }
                                },
                            }
                        }
                    }
                    let references = if unhandled.is_none() {
                        match poc::extract_references(&sql) {
                            Some(r) => r,
                            None => {
                                unhandled = Some("reference extraction fallback".into());
                                Vec::new()
                            }
                        }
                    } else {
                        Vec::new()
                    };
                    Output {
                        name: model.name,
                        query_sql: unhandled.is_none().then_some(sql),
                        references,
                        macro_deps: model.macro_deps,
                        config: model.config,
                        unhandled,
                    }
                })
                .collect()
        });
    let splice_s = t.elapsed().as_secs_f64();
    let times = PhaseTimes {
        python_init,
        macro_import,
        discovery: discovery_s,
        declarations: declarations_s,
        render: render_s,
        macro_calls: macro_calls_s,
        splice: splice_s,
        total: start.elapsed().as_secs_f64(),
        cpu: process_cpu_seconds() - cpu0,
        unique_calls: unique.len(),
        call_sites,
    };
    (times, outputs, discovery.python_models, decls.unsupported)
}

fn py_value<'py>(py: Python<'py>, value: &Value) -> Option<Bound<'py, PyAny>> {
    match value {
        Value::Str(s) => s.into_pyobject(py).ok().map(|v| v.into_any()),
        Value::Int(s) => s
            .parse::<i64>()
            .ok()?
            .into_pyobject(py)
            .ok()
            .map(|v| v.into_any()),
        Value::Float(s) => s
            .parse::<f64>()
            .ok()?
            .into_pyobject(py)
            .ok()
            .map(|v| v.into_any()),
        Value::Bool(b) => b.into_pyobject(py).ok().map(|v| v.to_owned().into_any()),
        Value::Null => Some(py.None().into_bound(py)),
        Value::List(items) => PyList::new(
            py,
            items
                .iter()
                .filter_map(|i| py_value(py, i))
                .collect::<Vec<_>>(),
        )
        .ok()
        .map(|v| v.into_any()),
    }
}

fn verify(outputs: &[Output], path: &str) {
    let text = std::fs::read_to_string(path).expect("render json");
    let expected: serde_json::Value = serde_json::from_str(&text).expect("json");
    let by_name: HashMap<&str, &serde_json::Value> = expected["models"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|m| m["name"].as_str().map(|n| (n, m)))
        .collect();
    let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
    let mut reasons: BTreeMap<String, usize> = BTreeMap::new();
    let mut examples: Vec<String> = Vec::new();
    for output in outputs {
        let Some(expected) = by_name.get(output.name.as_str()) else {
            *counts.entry("not in python output").or_default() += 1;
            continue;
        };
        let Some(sql) = &output.query_sql else {
            *counts.entry("unhandled").or_default() += 1;
            let reason = output.unhandled.clone().unwrap_or_default();
            let reason = reason.split('\'').next().unwrap_or_default().to_owned();
            *reasons.entry(reason).or_default() += 1;
            continue;
        };
        *counts.entry("handled").or_default() += 1;
        let sql_equal = expected["query_sql"].as_str() == Some(sql.as_str());
        *counts
            .entry(if sql_equal {
                "sql equal"
            } else {
                "sql DIFFERENT"
            })
            .or_default() += 1;
        if !sql_equal && examples.len() < 4 {
            let e = expected["query_sql"].as_str().unwrap_or_default();
            let position = e
                .bytes()
                .zip(sql.bytes())
                .position(|(a, b)| a != b)
                .unwrap_or(e.len().min(sql.len()));
            examples.push(format!(
                "{}: first difference at byte {position} (python len {}, rust len {})\n    python: {:?}\n    rust:   {:?}",
                output.name.len(),
                e.len(),
                sql.len(),
                e.get(position.saturating_sub(40)..(position + 60).min(e.len())).unwrap_or_default(),
                sql.get(position.saturating_sub(40)..(position + 60).min(sql.len())).unwrap_or_default()
            ));
        }
        let python_refs: Vec<(String, String)> = expected["references"]
            .as_array()
            .into_iter()
            .flatten()
            .map(|r| {
                (
                    r[0].as_str().unwrap_or_default().to_owned(),
                    r[1].as_str().unwrap_or_default().to_owned(),
                )
            })
            .collect();
        let rust_refs: Vec<(String, String)> = output
            .references
            .iter()
            .map(|(k, n, _)| (k.clone(), n.clone()))
            .collect();
        *counts
            .entry(if python_refs == rust_refs {
                "references equal"
            } else {
                "references DIFFERENT"
            })
            .or_default() += 1;
        let deps: Vec<String> = expected["macro_deps"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|d| d.as_str().map(str::to_owned))
            .collect();
        *counts
            .entry(if deps == output.macro_deps {
                "macro deps equal"
            } else {
                "macro deps DIFFERENT"
            })
            .or_default() += 1;
        let config_equal = output
            .config
            .iter()
            .all(|(key, value)| expected["config"].get(key) == Some(value))
            && ["materialized", "database", "schema", "contract", "tags"]
                .iter()
                .all(|k| expected["config"].get(*k).is_none() || output.config.contains_key(*k));
        *counts
            .entry(if config_equal {
                "config subset equal"
            } else {
                "config subset DIFFERENT"
            })
            .or_default() += 1;
    }
    println!("verify: {counts:?}");
    println!("unhandled reasons: {reasons:?}");
    for example in examples {
        println!("  {example}");
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let project = PathBuf::from(args.get(1).expect("project dir"));
    let flag = |name: &str| {
        args.iter()
            .position(|a| a == name)
            .and_then(|i| args.get(i + 1))
            .cloned()
    };
    let threads: usize = flag("--threads").and_then(|v| v.parse().ok()).unwrap_or(4);
    let runs: usize = flag("--runs").and_then(|v| v.parse().ok()).unwrap_or(1);
    let site = flag("--site-packages");
    let target = flag("--target");
    let load = load_average();
    // One process renders once: the interpreter, module imports and memo are per process, like a
    // compile. Repeat runs re-exec this binary (see --runs handling in the driver script).
    let (times, outputs, python_models, unsupported_decls) =
        run(&project, threads, site.as_deref(), target.as_deref());
    let handled = outputs.iter().filter(|o| o.query_sql.is_some()).count();
    println!(
        "render_floor threads {threads} load {load:.2}: models {} handled {handled} python models skipped {python_models} unsupported declarations {unsupported_decls}",
        outputs.len()
    );
    println!(
        "  total {:.3}s cpu {:.3}s | python init {:.3} | discovery+read {:.3} | declarations {:.3} | macro module import {:.3} | render (config, vars, decls, call scan) {:.3} | macro calls {:.3} ({} unique of {} call sites) | splice+refs {:.3}",
        times.total,
        times.cpu,
        times.python_init,
        times.discovery,
        times.declarations,
        times.macro_import,
        times.render,
        times.macro_calls,
        times.unique_calls,
        times.call_sites,
        times.splice
    );
    let _ = runs;
    let _ = median;
    if let Some(path) = flag("--verify") {
        verify(&outputs, &path);
    }
}
