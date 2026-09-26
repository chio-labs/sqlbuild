//! Compile-owned schema catalog and native, batched binding requests.

use std::collections::HashMap;

use crate::semantic_validation::models::{CatalogInput, Columns, ProjectCatalog};
use crate::semantic_validation::types::{BindingRequest, DiagnosticRow, Relations};
use crate::semantic_validation::{
    _helpers::{diagnostics, identifiers},
    main as validation,
};
use polyglot_sql::validation::{SchemaColumn, SchemaTable};
use polyglot_sql::{
    Dialect, DialectType, SchemaValidationOptions, ValidationError, ValidationResult,
    ValidationSchema,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, FromPyObject, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pymethods;
use pyo3::types::{PyBytes, PyDict, PyDictMethods};
use rayon::iter::{IntoParallelIterator, ParallelIterator};

impl<'py> FromPyObject<'py> for Columns {
    fn extract_bound(value: &Bound<'py, PyAny>) -> PyResult<Self> {
        value
            .downcast::<PyDict>()?
            .iter()
            .map(|(name, data_type)| Ok((name.extract()?, data_type.extract()?)))
            .collect::<PyResult<Vec<_>>>()
            .map(Self)
    }
}
#[pymethods]
impl ProjectCatalog {
    #[new]
    fn new(request: CatalogInput) -> PyResult<Self> {
        let CatalogInput {
            dialect,
            quoted_ignore_case,
            known_functions,
            known_types,
            relations,
        } = request;
        let dialect = dialect
            .parse::<DialectType>()
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        let mut catalog = Self {
            dialect,
            quoted_ignore_case,
            options: SchemaValidationOptions {
                known_functions,
                known_types,
                check_types: matches!(
                    dialect,
                    DialectType::DuckDB
                        | DialectType::PostgreSQL
                        | DialectType::Snowflake
                        | DialectType::BigQuery
                ),
                check_references: true,
                semantic: true,
                strict: Some(true),
                complexity_guard: Some(polyglot_sql::ComplexityGuardOptions {
                    max_function_call_depth: Some(512),
                    ..Default::default()
                }),
                ..Default::default()
            },
            tables: HashMap::new(),
            overrides: Vec::new(),
            analysis_tables: HashMap::new(),
        };
        catalog.update_relations(relations);
        Ok(catalog)
    }

    fn update_relations(&mut self, relations: Relations) {
        for (name, columns) in relations {
            self.tables.insert(name.clone(), self.table(&name, columns));
        }
    }

    fn with_relations(&self, relations: Relations) -> Self {
        let mut catalog = Self {
            dialect: self.dialect,
            options: self.options.clone(),
            quoted_ignore_case: self.quoted_ignore_case,
            tables: self.tables.clone(),
            overrides: Vec::new(),
            analysis_tables: self.analysis_tables.clone(),
        };
        catalog.update_relations(relations);
        catalog
    }

    fn update_analysis(&mut self, relations: HashMap<String, (Columns, Columns)>) {
        for (name, (types, nullability)) in relations {
            let types: HashMap<_, _> = types.0.into_iter().collect();
            let mut table = self.table(&name, Columns::default());
            table.name = name.clone();
            for (column, nullable) in nullability.0 {
                table.columns.push(SchemaColumn {
                    data_type: types
                        .get(&column)
                        .and_then(Clone::clone)
                        .unwrap_or_else(|| "UNKNOWN".to_owned()),
                    name: column,
                    nullable: match nullable.as_deref() {
                        Some("non_null") => Some(false),
                        Some("nullable") => Some(true),
                        _ => None,
                    },
                    primary_key: false,
                    unique: false,
                    references: None,
                });
            }
            self.analysis_tables.insert(name, table);
        }
    }

    fn register_override(&mut self, relations: Relations) -> usize {
        let tables: HashMap<String, SchemaTable> = relations
            .into_iter()
            .map(|(name, columns)| (name.clone(), self.table(&name, columns)))
            .collect();
        self.overrides.push(tables);
        self.overrides.len() - 1
    }

    fn validation_payload(&self, requests: Vec<BindingRequest>) -> PyResult<String> {
        let mut payloads = Vec::with_capacity(requests.len());
        for (sql, references, overrides) in requests {
            let schema = self
                .schema(&references, overrides)
                .map_err(PyValueError::new_err)?;
            payloads.push(serde_json::json!({"sql": sql, "dialect": self.dialect.to_string(), "schema": schema,
                "options": self.options, "quoted_ignore_case": self.quoted_ignore_case}));
        }
        serde_json::to_string(&payloads).map_err(|error| PyValueError::new_err(error.to_string()))
    }

    fn analyze_compact<'py>(
        &self,
        py: Python<'py>,
        payload: &[u8],
    ) -> PyResult<Bound<'py, PyBytes>> {
        let text = std::str::from_utf8(payload)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        let result = py.detach(|| crate::query_analysis::main::analyze_project_catalog::analyze_project_compact_with_catalog(text, self))
            .map_err(PyValueError::new_err)?;
        Ok(PyBytes::new(py, result.as_bytes()))
    }

    fn binding_results(
        &self,
        py: Python<'_>,
        requests: Vec<BindingRequest>,
    ) -> PyResult<Vec<Vec<DiagnosticRow>>> {
        py.detach(|| {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(4.min(requests.len().max(1)))
                .stack_size(16 * 1024 * 1024)
                .build()
                .map_err(|error| error.to_string())?;
            pool.install(|| {
                requests
                    .into_par_iter()
                    .map(|(sql, references, overrides)| {
                        let schema = self.schema(&references, overrides)?;
                        let result = self.validate(&sql, &schema)?;
                        let result = diagnostics::map_diagnostics(&sql, self.dialect, result)?;
                        Ok(result.errors.into_iter().map(diagnostic_row).collect())
                    })
                    .collect::<Result<Vec<_>, String>>()
            })
        })
        .map_err(PyValueError::new_err)
    }
}

impl ProjectCatalog {
    pub(crate) fn with_options(
        dialect: DialectType,
        options: SchemaValidationOptions,
        quoted_ignore_case: bool,
    ) -> Self {
        Self {
            dialect,
            options,
            quoted_ignore_case,
            tables: HashMap::new(),
            overrides: Vec::new(),
            analysis_tables: HashMap::new(),
        }
    }
    pub(crate) fn analysis_schema(
        &self,
        references: &[(String, String)],
    ) -> Option<ValidationSchema> {
        let mut tables: Vec<SchemaTable> = Vec::new();
        for (name, alias) in references {
            if let Some(table) = self
                .analysis_tables
                .get(name)
                .filter(|table| !table.columns.is_empty())
            {
                let mut table = table.clone();
                table.name = alias.clone();
                tables.push(table);
            }
        }
        if tables.is_empty() {
            None
        } else {
            Some(ValidationSchema {
                tables,
                strict: None,
            })
        }
    }
    pub(crate) fn reference_schema(
        &self,
        references: &[(String, bool)],
        override_id: Option<usize>,
    ) -> Result<ValidationSchema, String> {
        let mut schema = self.schema(references, HashMap::new())?;
        if let Some(id) = override_id {
            let overrides = self
                .overrides
                .get(id)
                .ok_or("invalid native binding override")?;
            for ((name, _), table) in references.iter().zip(&mut schema.tables) {
                if let Some(replacement) = overrides.get(name) {
                    *table = replacement.clone();
                }
            }
        }
        Ok(schema)
    }
    fn table(&self, name: &str, columns: Columns) -> SchemaTable {
        let columns: Vec<_> = columns
            .0
            .into_iter()
            .map(|(name, data_type)| SchemaColumn {
                name: self.schema_name(name),
                data_type: data_type.unwrap_or_else(|| "UNKNOWN".to_owned()),
                nullable: None,
                primary_key: false,
                unique: false,
                references: None,
            })
            .collect();
        SchemaTable {
            name: self.schema_name(name.to_owned()),
            schema: None,
            columns,
            aliases: Vec::new(),
            primary_key: Vec::new(),
            unique_keys: Vec::new(),
            foreign_keys: Vec::new(),
        }
    }

    fn schema_name(&self, name: String) -> String {
        if self.quoted_ignore_case {
            name.to_ascii_uppercase()
        } else {
            name
        }
    }

    pub(crate) fn schema(
        &self,
        references: &[(String, bool)],
        mut overrides: Relations,
    ) -> Result<ValidationSchema, String> {
        let mut tables = Vec::with_capacity(references.len());
        for (name, closed) in references {
            let table = if let Some(columns) = overrides.remove(name) {
                self.table(name, columns)
            } else if !closed {
                self.table(name, Columns::default())
            } else {
                self.tables
                    .get(name)
                    .cloned()
                    .ok_or_else(|| format!("binding catalog has no relation {name}"))?
            };
            tables.push(table);
        }
        Ok(ValidationSchema {
            tables,
            strict: Some(true),
        })
    }

    pub(crate) fn validate(
        &self,
        sql: &str,
        schema: &ValidationSchema,
    ) -> Result<ValidationResult, String> {
        if !self.quoted_ignore_case || !sql.contains('"') {
            return validation::validation_result(validation::ValidationRequest {
                sql: sql.to_owned(),
                dialect: self.dialect.to_string(),
                schema: schema.clone(),
                options: self.options.clone(),
                quoted_ignore_case: false,
            });
        }
        let statements = match Dialect::get(self.dialect).parse_with_options(
            sql,
            &polyglot_sql::ParseOptions {
                complexity_guard: self.options.complexity_guard,
            },
        ) {
            Ok(statements) => statements,
            Err(_) => {
                return Ok(polyglot_sql::validate_with_schema(
                    sql,
                    self.dialect,
                    schema,
                    &self.options,
                ));
            }
        };
        let (statements, authored) = identifiers::fold_statements(statements)?;
        let mut result = polyglot_sql::validation::validate_parsed_with_schema(
            statements.clone(),
            self.dialect,
            schema,
            &self.options,
        );
        if result.valid && validation::may_have_extra_clause_checks(sql) {
            let mapping = polyglot_sql::mapping_schema_from_validation_schema_with_dialect(
                schema,
                self.dialect,
            );
            for statement in &statements {
                result.errors.extend(validation::missing_clause_columns(
                    &polyglot_sql::build_scope(statement),
                    &mapping,
                ));
            }
        }
        for error in &mut result.errors {
            for (normalized, spelling, span) in &authored {
                if error.start.is_none_or(|start| {
                    span.is_none_or(|span| {
                        start <= span.end && error.end.unwrap_or(start) >= span.start
                    })
                }) {
                    error.message = error
                        .message
                        .replace(&format!("'{normalized}'"), &format!("'{spelling}'"))
                        .replace(
                            &format!("'{}'", normalized.to_ascii_lowercase()),
                            &format!("'{spelling}'"),
                        );
                }
            }
        }
        result.valid = !result
            .errors
            .iter()
            .any(|error| error.severity == polyglot_sql::ValidationSeverity::Error);
        Ok(result)
    }
}

pub(super) fn diagnostic_row(error: ValidationError) -> DiagnosticRow {
    let severity = match error.severity {
        polyglot_sql::ValidationSeverity::Error => "error",
        _ => "warning",
    };
    (
        error.code,
        error.message,
        error.line,
        error.column,
        error.start,
        error.end,
        severity.to_owned(),
    )
}
