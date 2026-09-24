//! Coarse project-level planning for SQL-native test artifacts.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Instant;

use polyglot_sql::{Dialect, Expression};
use rayon::iter::{IntoParallelIterator, ParallelIterator};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::compiler::_helpers::sql_tests::expected_columns::expected_columns;
use crate::compiler::_helpers::sql_tests::helper_scope::{
    ScopeGraph, helper_scope_ctes, merged_scoped_ctes,
};
use crate::compiler::_helpers::sql_tests::markers::{
    in_protected_range, marker_names, protected_ranges, replace_callable_markers,
    replace_dbt_ref_markers, replace_named_markers,
};
use crate::compiler::_helpers::sql_tests::rendering::{
    AssertionStep, ChainStep, RenderRequest, render_comparison_sql, render_dialect,
    rendered_chain_steps,
};
use crate::constants::{TABLE_FUNCTION_TEST_MODE, UDF_TEST_MODE};

const DEFAULT_WORKERS: usize = 4;
const MAX_WORKERS: usize = 4;
const WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;
pub(crate) const REF_PREFIX: &str = "__ref__";
pub(crate) const SOURCE_PREFIX: &str = "__source__";
pub(crate) const SEED_PREFIX: &str = "__seed__";
pub(crate) const DBT_REF_PREFIX: &str = "__dbt_ref__";
const TABLE_FUNCTION_PREFIX: &str = "__table_fn__";
const EXPECTED_PREFIX: &str = "__expected__";
const ASSERT_PREFIX: &str = "__assert__";
const REF_FUNCTION: &str = "__ref";
const SOURCE_FUNCTION: &str = "__source";
const SEED_FUNCTION: &str = "__seed";
const DBT_REF_FUNCTION: &str = "__dbt_ref";
const UDF_FUNCTION: &str = "__udf";
const TABLE_FUNCTION: &str = "__table_fn";

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct PlanBatchRequest {
    models: Vec<ModelInput>,
    #[serde(default)]
    functions: Vec<FunctionInput>,
    tests: Vec<TestInput>,
    #[serde(default = "default_true")]
    sql_analysis_enabled: bool,
    #[serde(default)]
    sql_analysis_dialect: Option<String>,
    #[serde(default = "default_set_difference")]
    set_difference_operator: String,
    #[serde(default)]
    requires_derived_table_aliases: bool,
    #[serde(default = "default_workers")]
    workers: usize,
    #[serde(default = "default_true")]
    render_sql: bool,
    #[serde(default = "default_true")]
    include_plan: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ChainBatchRequest {
    models: Vec<ModelInput>,
    tests: Vec<TestInput>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ChainBatchResponse {
    chains: Vec<Vec<String>>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ModelInput {
    name: String,
    query_sql: String,
    #[serde(default)]
    model_dependencies: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct FunctionInput {
    name: String,
    #[serde(default)]
    udf_prefix: Option<String>,
    #[serde(default)]
    udf_suffix: Option<String>,
    #[serde(default)]
    table_function_prefix: Option<String>,
    #[serde(default)]
    table_function_suffix: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct TestInput {
    name: String,
    file_label: String,
    payload: TestPayload,
}

#[derive(Debug, Deserialize)]
#[serde(
    tag = "kind",
    rename_all = "camelCase",
    rename_all_fields = "camelCase"
)]
enum TestPayload {
    Model {
        #[serde(default)]
        authored_ctes: Vec<CteInput>,
        #[serde(default)]
        model_query_overrides: BTreeMap<String, String>,
        #[serde(default)]
        expected_ctes: Vec<CteInput>,
        #[serde(default)]
        expected_model_names: Vec<String>,
        #[serde(default)]
        assertion_ctes: Vec<CteInput>,
    },
    Direct {
        mode: String,
        actual_cte: CteInput,
        expected_cte: CteInput,
        #[serde(default)]
        helper_ctes: Vec<CteInput>,
    },
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CteInput {
    pub(crate) name: String,
    pub(crate) sql_body: String,
}

/// One planned SQL test: the executable chain and assertion steps plus optional rendered SQL.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PlanResponse {
    sql: Option<String>,
    chain: Vec<ChainStep>,
    assertions: Vec<AssertionStep>,
    model_names: Vec<String>,
    warnings: Vec<PlanWarning>,
}

struct PlannedResponse {
    request: RenderRequest,
    model_names: Vec<String>,
    warnings: Vec<PlanWarning>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PlanBatchResponse {
    artifacts: Vec<PlanResponse>,
    planning_ns: u64,
    rendering_ns: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PlanWarning {
    model_name: Option<String>,
    severity: &'static str,
    message: String,
}

#[derive(Clone)]
struct ProjectContext {
    models: HashMap<String, ModelInputOwned>,
    functions: HashMap<String, FunctionInput>,
    sql_analysis_enabled: bool,
    dialect: String,
    set_difference_operator: String,
    requires_derived_table_aliases: bool,
    analysis_templates: Arc<AnalysisTemplateCache>,
    patterns: SqlTestPatterns,
    render_dialect: Arc<Dialect>,
}

#[derive(Clone)]
pub(crate) struct SqlTestPatterns {
    reference: Regex,
    source: Regex,
    seed: Regex,
    udf: Regex,
    table_function: Regex,
    dbt_reference: Regex,
    test_reference: Regex,
    pub(crate) protected: Regex,
    pub(crate) identifier: Regex,
}

impl SqlTestPatterns {
    fn new() -> Result<Self, String> {
        Ok(Self {
            reference: compile_pattern(r#"(?i)__ref\(\"([^\"]+)\"\)"#)?,
            source: compile_pattern(r#"(?i)__source\(\"([^\"]+)\"\)"#)?,
            seed: compile_pattern(r#"(?i)__seed\(\"([^\"]+)\"\)"#)?,
            udf: compile_pattern(r#"(?i)__udf\(\"([^\"]+)\"\)"#)?,
            table_function: compile_pattern(r#"(?i)__table_fn\(\"([^\"]+)\"\)"#)?,
            dbt_reference: compile_pattern(
                r#"(?i)__dbt_ref\(\s*\"([^\"]+)\"\s*(?:,\s*\"([^\"]+)\"\s*)?\)"#,
            )?,
            test_reference: compile_pattern(r#"(?i)__(?:ref|source|seed|dbt_ref|table_fn)\("#)?,
            protected: compile_pattern(
                r#"(?s)'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\$\$.*?\$\$|--[^\n]*|/\*.*?\*/"#,
            )?,
            identifier: compile_pattern(r"[A-Za-z_][A-Za-z0-9_$]*")?,
        })
    }
}

#[derive(Clone)]
struct ModelInputOwned {
    query_sql: String,
    model_dependencies: Vec<String>,
}

#[derive(Clone)]
struct AnalysisResolvedSql {
    resolved_sql: String,
    cte_body_sql: String,
    generated_ctes: Vec<(String, String)>,
    reachable_mock_names: HashSet<String>,
}

#[derive(Clone)]
pub(crate) struct AnalysisTemplate {
    existing_cte_names: HashSet<String>,
    marker_calls: Vec<(String, String)>,
}

type AnalysisTemplateCell = Arc<OnceLock<Option<AnalysisTemplate>>>;
type AnalysisTemplateCache = Mutex<HashMap<String, AnalysisTemplateCell>>;

pub(crate) struct TestFixtures {
    pub(crate) mock_refs: BTreeMap<String, String>,
    pub(crate) mock_sources: BTreeMap<String, String>,
    pub(crate) mock_seeds: BTreeMap<String, String>,
    pub(crate) mock_dbt_refs: BTreeMap<String, String>,
    mock_table_functions: BTreeMap<String, String>,
    pub(crate) helpers: Vec<CteInput>,
    pub(crate) scope: ScopeGraph,
    expected: BTreeMap<String, String>,
    assertions: Vec<(String, String)>,
}

struct DirectTestPlan {
    name: String,
    mode: String,
    actual_cte: CteInput,
    expected_cte: CteInput,
    helpers: Vec<CteInput>,
}

struct ModelTestPlan {
    test_name: String,
    file_label: String,
    authored_ctes: Vec<CteInput>,
    model_query_overrides: BTreeMap<String, String>,
    expected_ctes: Vec<CteInput>,
    expected_model_names: Vec<String>,
    assertion_ctes: Vec<CteInput>,
}

struct TextualChainRequest<'a> {
    ordered_names: &'a [String],
    overrides: &'a BTreeMap<String, String>,
    fixtures: &'a TestFixtures,
    context: &'a ProjectContext,
    chain: &'a mut TextualChain,
}

/// Chain models resolved once each as named CTE bodies, so work scales with models not paths.
#[derive(Default)]
struct TextualChain {
    cte_names: HashMap<String, String>,
    bodies: HashMap<String, String>,
    dependencies: HashMap<String, Vec<String>>,
    mock_ctes: HashMap<String, Vec<(String, String)>>,
    order: Vec<String>,
}

struct TextualChainInputs<'a> {
    ordered_names: &'a [String],
    overrides: &'a BTreeMap<String, String>,
    fixtures: &'a TestFixtures,
    context: &'a ProjectContext,
}

struct TextualStep {
    resolved_sql: String,
    lifted_ctes: Vec<(String, String)>,
    body_sql: String,
}

impl TextualChain {
    fn extend(&mut self, inputs: &TextualChainInputs<'_>) -> Result<HashSet<String>, String> {
        let mut reachable: HashSet<String> = HashSet::new();
        for model_name in inputs.ordered_names {
            if self.bodies.contains_key(model_name) {
                continue;
            }
            let Some(model) = inputs.context.models.get(model_name) else {
                continue;
            };
            let query_sql = inputs.overrides.get(model_name).unwrap_or(&model.query_sql);
            let mut chain_references: Vec<String> = Vec::new();
            let resolution = resolve_textual_sql(TextualResolutionRequest {
                query_sql,
                fixtures: inputs.fixtures,
                resolved_chain: &self.cte_names,
                chain_references: Some(&mut chain_references),
                functions: &inputs.context.functions,
                patterns: &inputs.context.patterns,
            })?;
            reachable.extend(resolution.reached);
            self.mock_ctes
                .insert(model_name.to_string(), resolution.mock_ctes);
            self.insert(model_name, resolution.sql, chain_references);
        }
        Ok(reachable)
    }

    fn insert(&mut self, model_name: &str, body: String, dependencies: Vec<String>) {
        self.cte_names
            .insert(model_name.to_string(), format!("{REF_PREFIX}{model_name}"));
        self.bodies.insert(model_name.to_string(), body);
        self.dependencies
            .insert(model_name.to_string(), dependencies);
        self.order.push(model_name.to_string());
    }

    /// Return the generated CTEs needed by `roots`, dependencies first, each exactly once.
    fn closure_ctes(&self, roots: &[String], include_roots: bool) -> Vec<(String, String)> {
        let mut needed: HashSet<String> = HashSet::new();
        let mut stack: Vec<String> = Vec::new();
        for root in roots {
            if include_roots {
                stack.push(root.clone());
            } else if let Some(dependencies) = self.dependencies.get(root) {
                stack.extend(dependencies.iter().cloned());
            }
        }
        while let Some(name) = stack.pop() {
            if !needed.insert(name.clone()) {
                continue;
            }
            if let Some(dependencies) = self.dependencies.get(&name) {
                stack.extend(dependencies.iter().cloned());
            }
        }
        let mut ctes: Vec<(String, String)> = Vec::new();
        for (name, sql) in self
            .order
            .iter()
            .filter(|name| needed.contains(*name) || roots.contains(name))
            .filter_map(|name| self.mock_ctes.get(name))
            .flatten()
        {
            if !ctes.iter().any(|(existing, _)| existing == name) {
                ctes.push((name.clone(), sql.clone()));
            }
        }
        ctes.extend(
            self.order
                .iter()
                .filter(|name| needed.contains(*name))
                .filter_map(|name| {
                    Some((
                        self.cte_names.get(name)?.clone(),
                        self.bodies.get(name)?.clone(),
                    ))
                }),
        );
        ctes
    }

    fn step(&self, model_name: &str) -> Option<TextualStep> {
        let body_sql = self.bodies.get(model_name)?.clone();
        let lifted_ctes = self.closure_ctes(&[model_name.to_string()], false);
        Some(TextualStep {
            resolved_sql: with_generated_ctes(&lifted_ctes, &body_sql),
            lifted_ctes,
            body_sql,
        })
    }
}

/// Prefix generated CTEs to a query, merging into its own leading WITH clause when present.
fn with_generated_ctes(ctes: &[(String, String)], body: &str) -> String {
    if ctes.is_empty() {
        return body.to_string();
    }
    let definitions: String = ctes
        .iter()
        .map(|(name, sql)| cte_definition_sql(name, sql))
        .collect::<Vec<_>>()
        .join(", ");
    match leading_with_prefix_end(body) {
        Some(end) => format!("{}{definitions}, {}", &body[..end], &body[end..]),
        None => format!("WITH {definitions} {body}"),
    }
}

struct AssertionResolutionRequest<'a> {
    assertion_sql: &'a str,
    fixtures: &'a TestFixtures,
    chain: &'a TextualChain,
    functions: &'a HashMap<String, FunctionInput>,
    requires_flat_ctes: bool,
    patterns: &'a SqlTestPatterns,
}

struct AnalysisResolutionRequest<'a> {
    query_sql: &'a str,
    fixtures: &'a TestFixtures,
    resolved_chain: &'a HashMap<String, AnalysisResolvedSql>,
    functions: &'a HashMap<String, FunctionInput>,
    file_label: &'a str,
    dialect_name: &'a str,
    templates: &'a AnalysisTemplateCache,
    patterns: &'a SqlTestPatterns,
}

struct TextualResolutionRequest<'a> {
    query_sql: &'a str,
    fixtures: &'a TestFixtures,
    resolved_chain: &'a HashMap<String, String>,
    chain_references: Option<&'a mut Vec<String>>,
    functions: &'a HashMap<String, FunctionInput>,
    patterns: &'a SqlTestPatterns,
}

struct TopoSortRequest<'a> {
    expected_names: &'a [String],
    models: &'a HashMap<String, ModelInputOwned>,
    overrides: &'a BTreeMap<String, String>,
    mock_refs: &'a BTreeMap<String, String>,
    patterns: &'a SqlTestPatterns,
}

struct MockTargetRequest<'a> {
    prefix: &'a str,
    referenced_name: &'a str,
    mocks: &'a BTreeMap<String, String>,
    fixtures: &'a TestFixtures,
    file_label: &'a str,
}

#[derive(Default)]
struct GeneratedCteState {
    generated: Vec<(String, String)>,
    names: HashSet<String>,
    reachable: HashSet<String>,
}

impl GeneratedCteState {
    fn insert(&mut self, name: &str, sql: &str, file_label: &str) -> Result<(), String> {
        if let Some((_, existing)) = self
            .generated
            .iter()
            .find(|(existing_name, _)| existing_name == name)
            && existing == sql
        {
            return Ok(());
        }
        if self.names.contains(name) && !self.generated.iter().any(|(existing, _)| existing == name)
        {
            return Err(compile_error(&format!(
                "SQL test '{file_label}' defines CTE '{name}', which conflicts with the generated CTE"
            )));
        }
        if self.names.insert(name.to_string()) {
            self.generated.push((name.to_string(), sql.to_string()));
        }
        Ok(())
    }

    fn mock_target(&mut self, request: MockTargetRequest<'_>) -> Result<Option<String>, String> {
        let Some(mock_body) = request.mocks.get(request.referenced_name) else {
            return Ok(None);
        };
        self.reachable.insert(request.referenced_name.to_string());
        let generated_name = format!("{}{}", request.prefix, request.referenced_name);
        if self.names.contains(&generated_name)
            && !self
                .generated
                .iter()
                .any(|(existing_name, _)| existing_name == &generated_name)
        {
            let referenced_kind = request.prefix.trim_matches('_');
            return Err(compile_error(&format!(
                "SQL test '{}' defines CTE '{generated_name}', which conflicts with the generated {referenced_kind} CTE for '{}'",
                request.file_label, request.referenced_name
            )));
        }
        for dependency in request.fixtures.scope.mock_dependencies(&generated_name) {
            self.reachable.insert(dependency.mock_name.clone());
            self.insert(
                &dependency.generated_name,
                &dependency.sql,
                request.file_label,
            )?;
        }
        let sql = mock_cte_sql(mock_body, &request.fixtures.helpers);
        self.insert(&generated_name, &sql, request.file_label)?;
        Ok(Some(generated_name))
    }
}

/// Return each test's topologically ordered unmocked model chain without planning SQL.
pub(crate) fn resolve_chains_json(request_json: &str) -> Result<String, String> {
    let request: ChainBatchRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let patterns = SqlTestPatterns::new()?;
    let models: HashMap<String, ModelInputOwned> = request
        .models
        .into_iter()
        .map(|model| {
            (
                model.name,
                ModelInputOwned {
                    query_sql: model.query_sql,
                    model_dependencies: model.model_dependencies,
                },
            )
        })
        .collect();
    let chains: Vec<Vec<String>> = request
        .tests
        .into_iter()
        .map(|test| match test.payload {
            TestPayload::Direct { .. } => Vec::new(),
            TestPayload::Model {
                authored_ctes,
                model_query_overrides,
                expected_model_names,
                assertion_ctes,
                ..
            } => {
                let fixtures = classify_fixtures(authored_ctes, Vec::new(), assertion_ctes);
                let expected_names = chain_root_names(expected_model_names, &fixtures, &patterns);
                topo_sort_model_chain(TopoSortRequest {
                    expected_names: &expected_names,
                    models: &models,
                    overrides: &model_query_overrides,
                    mock_refs: &fixtures.mock_refs,
                    patterns: &patterns,
                })
            }
        })
        .collect();
    serde_json::to_string(&ChainBatchResponse { chains }).map_err(|error| error.to_string())
}

fn chain_root_names(
    mut expected_names: Vec<String>,
    fixtures: &TestFixtures,
    patterns: &SqlTestPatterns,
) -> Vec<String> {
    expected_names.extend(assertion_ref_targets(&fixtures.assertions, patterns));
    dedupe(expected_names)
}

pub(crate) fn plan_and_render_json(request_json: &str) -> Result<String, String> {
    let request: PlanBatchRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let render_sql = request.render_sql;
    let include_plan = request.include_plan;
    let render_dialect = Arc::new(render_dialect(request.sql_analysis_dialect.as_deref()));
    let context = ProjectContext {
        models: request
            .models
            .into_iter()
            .map(|model| {
                (
                    model.name,
                    ModelInputOwned {
                        query_sql: model.query_sql,
                        model_dependencies: model.model_dependencies,
                    },
                )
            })
            .collect(),
        functions: request
            .functions
            .into_iter()
            .map(|function| (function.name.clone(), function))
            .collect(),
        sql_analysis_enabled: request.sql_analysis_enabled,
        dialect: request
            .sql_analysis_dialect
            .unwrap_or_else(|| "generic".to_string()),
        set_difference_operator: request.set_difference_operator,
        requires_derived_table_aliases: request.requires_derived_table_aliases,
        analysis_templates: Arc::new(Mutex::new(HashMap::new())),
        patterns: SqlTestPatterns::new()?,
        render_dialect,
    };
    let workers = request.workers.clamp(1, MAX_WORKERS);
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(workers.min(request.tests.len().max(1)))
        .stack_size(WORKER_STACK_BYTES)
        .build()
        .map_err(|error| error.to_string())?;
    let batch_start = Instant::now();
    let responses: Vec<Result<(PlanResponse, u128, u128), String>> = pool.install(|| {
        request
            .tests
            .into_par_iter()
            .map(|test| {
                let planning_start = Instant::now();
                let mut planned = plan_test(test, &context)?;
                let planning_ns = planning_start.elapsed().as_nanos();
                let rendering_start = Instant::now();
                let sql = render_sql
                    .then(|| render_comparison_sql(&planned.request, &context.render_dialect));
                if !include_plan {
                    planned.request.chain.clear();
                    planned.request.assertions.clear();
                }
                let response = PlanResponse {
                    sql,
                    chain: planned.request.chain,
                    assertions: planned.request.assertions,
                    model_names: planned.model_names,
                    warnings: planned.warnings,
                };
                Ok((response, planning_ns, rendering_start.elapsed().as_nanos()))
            })
            .collect()
    });
    let responses: Vec<(PlanResponse, u128, u128)> =
        responses.into_iter().collect::<Result<_, _>>()?;
    let batch_ns = batch_start.elapsed().as_nanos();
    let planning_cpu_ns: u128 = responses.iter().map(|(_, value, _)| *value).sum();
    let rendering_cpu_ns: u128 = responses.iter().map(|(_, _, value)| *value).sum();
    let measured_cpu_ns = planning_cpu_ns + rendering_cpu_ns;
    let planning_ns = batch_ns
        .saturating_mul(planning_cpu_ns)
        .checked_div(measured_cpu_ns)
        .unwrap_or(batch_ns);
    let rendering_ns = batch_ns.saturating_sub(planning_ns);
    let artifacts: Vec<PlanResponse> = responses
        .into_iter()
        .map(|(response, _, _)| response)
        .collect();
    serde_json::to_string(&PlanBatchResponse {
        artifacts,
        planning_ns: planning_ns.min(u128::from(u64::MAX)) as u64,
        rendering_ns: rendering_ns.min(u128::from(u64::MAX)) as u64,
    })
    .map_err(|error| error.to_string())
}

fn plan_test(test: TestInput, context: &ProjectContext) -> Result<PlannedResponse, String> {
    match test.payload {
        TestPayload::Direct {
            mode,
            actual_cte,
            expected_cte,
            helper_ctes,
        } => plan_direct_test(
            DirectTestPlan {
                name: test.name,
                mode,
                actual_cte,
                expected_cte,
                helpers: helper_ctes,
            },
            context,
        ),
        TestPayload::Model {
            authored_ctes,
            model_query_overrides,
            expected_ctes,
            expected_model_names,
            assertion_ctes,
        } => plan_model_test(
            ModelTestPlan {
                test_name: test.name,
                file_label: test.file_label,
                authored_ctes,
                model_query_overrides,
                expected_ctes,
                expected_model_names,
                assertion_ctes,
            },
            context,
        ),
    }
}

fn plan_direct_test(
    plan: DirectTestPlan,
    context: &ProjectContext,
) -> Result<PlannedResponse, String> {
    let helper_with = helper_with_clause(&plan.helpers);
    let mut actual_sql = plan.actual_cte.sql_body;
    if plan.mode == UDF_TEST_MODE {
        actual_sql =
            resolve_function_calls(&actual_sql, &context.functions, false, &context.patterns)?;
    } else if plan.mode == TABLE_FUNCTION_TEST_MODE {
        actual_sql =
            resolve_function_calls(&actual_sql, &context.functions, true, &context.patterns)?;
    }
    let model_name = format!("{} {}", plan.mode, plan.name);
    let request = RenderRequest {
        chain: vec![ChainStep {
            model_name: model_name.clone(),
            resolved_sql: wrap_direct_sql(&actual_sql, &helper_with),
            expected_cte_sql: Some(wrap_direct_sql(&plan.expected_cte.sql_body, &helper_with)),
            expected_lifted_ctes: Vec::new(),
            lifted_ctes: Vec::new(),
            comparison_body_sql: None,
            expected_columns: None,
        }],
        assertions: Vec::new(),
        sql_analysis_enabled: context.sql_analysis_enabled,
        set_difference_operator: context.set_difference_operator.clone(),
        sql_analysis_dialect: Some(context.dialect.clone()),
        probe_step_index: None,
    };
    Ok(PlannedResponse {
        request,
        model_names: vec![model_name],
        warnings: Vec::new(),
    })
}

fn plan_model_test(
    plan: ModelTestPlan,
    context: &ProjectContext,
) -> Result<PlannedResponse, String> {
    let mut fixtures =
        classify_fixtures(plan.authored_ctes, plan.expected_ctes, plan.assertion_ctes);
    fixtures.scope = ScopeGraph::new(&fixtures, &context.patterns);
    let expected_names = chain_root_names(plan.expected_model_names, &fixtures, &context.patterns);
    let ordered_names = topo_sort_model_chain(TopoSortRequest {
        expected_names: &expected_names,
        models: &context.models,
        overrides: &plan.model_query_overrides,
        mock_refs: &fixtures.mock_refs,
        patterns: &context.patterns,
    });
    let mut warnings: Vec<PlanWarning> = Vec::new();
    let mut reported_missing_mocks: HashSet<(&'static str, String)> = HashSet::new();
    let mut reachable_mocks: HashSet<String> = HashSet::new();
    let mut analysis_resolved: HashMap<String, AnalysisResolvedSql> = HashMap::new();
    let mut textual_chain: TextualChain = TextualChain::default();
    let mut chain: Vec<ChainStep> = Vec::new();

    for (model_index, model_name) in ordered_names.iter().enumerate() {
        let Some(model) = context.models.get(model_name) else {
            warnings.push(PlanWarning {
                model_name: None,
                severity: "error",
                message: format!(
                    "test '{}' expects model '{model_name}' which does not exist",
                    plan.test_name
                ),
            });
            continue;
        };
        let query_sql = plan
            .model_query_overrides
            .get(model_name)
            .unwrap_or(&model.query_sql);
        let (fixture_resolved_sql, reached_table_functions) = resolve_table_function_fixtures(
            query_sql,
            &fixtures.mock_table_functions,
            &fixtures.helpers,
            &context.patterns,
        )?;
        reachable_mocks.extend(reached_table_functions);
        let analyzed = if context.sql_analysis_enabled && analysis_resolved.len() == model_index {
            analyze_and_resolve_sql(AnalysisResolutionRequest {
                query_sql: &fixture_resolved_sql,
                fixtures: &fixtures,
                resolved_chain: &analysis_resolved,
                functions: &context.functions,
                file_label: &plan.file_label,
                dialect_name: &context.dialect,
                templates: &context.analysis_templates,
                patterns: &context.patterns,
            })?
        } else {
            None
        };
        let (resolved_sql, lifted_ctes, comparison_body_sql) = if let Some(analyzed) = analyzed {
            reachable_mocks.extend(analyzed.reachable_mock_names.iter().cloned());
            let result = (
                analyzed.resolved_sql.clone(),
                analyzed.generated_ctes.clone(),
                Some(analyzed.cte_body_sql.clone()),
            );
            analysis_resolved.insert(model_name.clone(), analyzed);
            result
        } else {
            let (step, reached) = ensure_textual_chain_through(TextualChainRequest {
                ordered_names: &ordered_names[..=model_index],
                overrides: &plan.model_query_overrides,
                fixtures: &fixtures,
                context,
                chain: &mut textual_chain,
            })?;
            reachable_mocks.extend(reached);
            (step.resolved_sql, step.lifted_ctes, Some(step.body_sql))
        };
        warnings.extend(unresolved_reference_warnings(UnresolvedReferenceRequest {
            sql: &resolved_sql,
            test_name: &plan.test_name,
            model_name,
            patterns: &context.patterns,
            reported: &mut reported_missing_mocks,
        }));
        let expected_cte_sql = fixtures.expected.get(model_name).cloned();
        let expected_lifted_ctes = match expected_cte_sql.as_deref() {
            Some(sql) => {
                let scope = helper_scope_ctes(sql, &fixtures, &context.patterns, &plan.file_label)?;
                reachable_mocks.extend(scope.reached_mocks);
                scope.ctes
            }
            None => Vec::new(),
        };
        chain.push(ChainStep {
            model_name: model_name.clone(),
            resolved_sql,
            expected_columns: expected_cte_sql
                .as_deref()
                .and_then(|sql| expected_columns(sql, &context.render_dialect)),
            expected_cte_sql,
            expected_lifted_ctes,
            lifted_ctes,
            comparison_body_sql,
        });
    }

    let mut assertions: Vec<AssertionStep> = Vec::new();
    let mut textual_assertion_chain: Option<TextualChain> = None;
    for (assertion_name, assertion_sql) in &fixtures.assertions {
        let (fixture_resolved_sql, reached_table_functions) = resolve_table_function_fixtures(
            assertion_sql,
            &fixtures.mock_table_functions,
            &fixtures.helpers,
            &context.patterns,
        )?;
        reachable_mocks.extend(reached_table_functions);
        let analyzed =
            if context.sql_analysis_enabled && analysis_resolved.len() == ordered_names.len() {
                analyze_and_resolve_sql(AnalysisResolutionRequest {
                    query_sql: &fixture_resolved_sql,
                    fixtures: &fixtures,
                    resolved_chain: &analysis_resolved,
                    functions: &context.functions,
                    file_label: &plan.file_label,
                    dialect_name: &context.dialect,
                    templates: &context.analysis_templates,
                    patterns: &context.patterns,
                })?
            } else {
                None
            };
        let (mut resolved_sql, mut lifted_ctes, comparison_body_sql) = match analyzed {
            Some(value)
                if !has_unresolved_test_reference(&value.resolved_sql, &context.patterns) =>
            {
                reachable_mocks.extend(value.reachable_mock_names.iter().cloned());
                (
                    value.resolved_sql,
                    value.generated_ctes,
                    Some(value.cte_body_sql),
                )
            }
            _ => {
                if textual_assertion_chain.is_none() {
                    let (chain, reached) = build_textual_chain(
                        &ordered_names,
                        &plan.model_query_overrides,
                        &fixtures,
                        context,
                    )?;
                    reachable_mocks.extend(reached);
                    textual_assertion_chain = Some(chain);
                }
                let chain = textual_assertion_chain
                    .as_ref()
                    .ok_or_else(|| planner_error("textual assertion chain is unavailable"))?;
                let (resolved, reached) =
                    resolve_assertion_textual_sql(AssertionResolutionRequest {
                        assertion_sql: &fixture_resolved_sql,
                        fixtures: &fixtures,
                        chain,
                        functions: &context.functions,
                        requires_flat_ctes: context.requires_derived_table_aliases,
                        patterns: &context.patterns,
                    })?;
                reachable_mocks.extend(reached);
                (
                    resolved.resolved_sql,
                    resolved.lifted_ctes,
                    Some(resolved.body_sql),
                )
            }
        };
        let scope = helper_scope_ctes(
            &fixture_resolved_sql,
            &fixtures,
            &context.patterns,
            &plan.file_label,
        )?;
        if !scope.ctes.is_empty() {
            reachable_mocks.extend(scope.reached_mocks);
            lifted_ctes = merged_scoped_ctes(lifted_ctes, scope.ctes, &plan.file_label)?;
            resolved_sql = with_generated_ctes(
                &lifted_ctes,
                comparison_body_sql.as_deref().unwrap_or(&resolved_sql),
            );
        }
        assertions.push(AssertionStep {
            name: assertion_name.clone(),
            resolved_sql,
            lifted_ctes,
            comparison_body_sql,
        });
    }
    warnings.extend(unreachable_mock_warnings(
        &plan.test_name,
        &reachable_mocks,
        &fixtures,
    ));
    let chain = omit_unrendered_step_sql(chain, &assertions);
    let model_names: Vec<String> = chain.iter().map(|step| step.model_name.clone()).collect();
    let request = RenderRequest {
        chain,
        assertions,
        sql_analysis_enabled: context.sql_analysis_enabled,
        set_difference_operator: context.set_difference_operator.clone(),
        sql_analysis_dialect: Some(context.dialect.clone()),
        probe_step_index: None,
    };
    Ok(PlannedResponse {
        request,
        model_names,
        warnings,
    })
}

/// Drop SQL from chain steps the renderer never emits, keeping plan output linear in chain length.
fn omit_unrendered_step_sql(chain: Vec<ChainStep>, assertions: &[AssertionStep]) -> Vec<ChainStep> {
    let rendered_steps = rendered_chain_steps(&chain, assertions);
    chain
        .into_iter()
        .zip(rendered_steps)
        .map(|(step, rendered)| {
            if rendered {
                step
            } else {
                ChainStep {
                    model_name: step.model_name,
                    resolved_sql: String::new(),
                    expected_cte_sql: step.expected_cte_sql,
                    expected_lifted_ctes: step.expected_lifted_ctes,
                    lifted_ctes: Vec::new(),
                    comparison_body_sql: None,
                    expected_columns: step.expected_columns,
                }
            }
        })
        .collect()
}

fn ensure_textual_chain_through(
    request: TextualChainRequest<'_>,
) -> Result<(TextualStep, HashSet<String>), String> {
    let reachable: HashSet<String> = request.chain.extend(&TextualChainInputs {
        ordered_names: request.ordered_names,
        overrides: request.overrides,
        fixtures: request.fixtures,
        context: request.context,
    })?;
    let current_name = request
        .ordered_names
        .last()
        .ok_or_else(|| "textual SQL-test chain is empty".to_string())?;
    let step = request
        .chain
        .step(current_name)
        .ok_or_else(|| format!("SQL-test model '{current_name}' could not be resolved"))?;
    Ok((step, reachable))
}

fn build_textual_chain(
    ordered_names: &[String],
    overrides: &BTreeMap<String, String>,
    fixtures: &TestFixtures,
    context: &ProjectContext,
) -> Result<(TextualChain, HashSet<String>), String> {
    let mut chain: TextualChain = TextualChain::default();
    let reachable: HashSet<String> = chain.extend(&TextualChainInputs {
        ordered_names,
        overrides,
        fixtures,
        context,
    })?;
    Ok((chain, reachable))
}

fn resolve_assertion_textual_sql(
    request: AssertionResolutionRequest<'_>,
) -> Result<(TextualStep, HashSet<String>), String> {
    if request.requires_flat_ctes && leading_with_prefix_end(request.assertion_sql).is_some() {
        return Err(planner_error(
            "SQL test assertion fallback cannot safely flatten an assertion beginning with WITH",
        ));
    }
    let mut referenced: Vec<String> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    for name in marker_names(
        &request.patterns.reference,
        &request.patterns.protected,
        request.assertion_sql,
    ) {
        if !seen.insert(name.clone()) {
            continue;
        }
        let Some(body) = request.chain.bodies.get(&name) else {
            continue;
        };
        if request.requires_flat_ctes && leading_with_prefix_end(body).is_some() {
            return Err(planner_error(
                "SQL test assertion fallback cannot safely flatten a referenced model beginning with WITH",
            ));
        }
        referenced.push(name);
    }
    let resolution = resolve_textual_sql(TextualResolutionRequest {
        query_sql: request.assertion_sql,
        fixtures: request.fixtures,
        resolved_chain: &request.chain.cte_names,
        chain_references: None,
        functions: request.functions,
        patterns: request.patterns,
    })?;
    let mut lifted_ctes: Vec<(String, String)> = resolution.mock_ctes;
    for (name, sql) in request.chain.closure_ctes(&referenced, true) {
        if !lifted_ctes.iter().any(|(existing, _)| *existing == name) {
            lifted_ctes.push((name, sql));
        }
    }
    let body_sql = resolution.sql;
    let reached = resolution.reached;
    let resolved_sql = if lifted_ctes.is_empty() {
        body_sql.clone()
    } else {
        let cte_parts: Vec<String> = lifted_ctes
            .iter()
            .map(|(name, body)| cte_definition_sql(name, body))
            .collect();
        format!("WITH {} {body_sql}", cte_parts.join(", "))
    };
    Ok((
        TextualStep {
            resolved_sql,
            lifted_ctes,
            body_sql,
        },
        reached,
    ))
}

fn classify_fixtures(
    authored: Vec<CteInput>,
    expected: Vec<CteInput>,
    assertions: Vec<CteInput>,
) -> TestFixtures {
    let mut fixtures = TestFixtures {
        mock_refs: BTreeMap::new(),
        mock_sources: BTreeMap::new(),
        mock_seeds: BTreeMap::new(),
        mock_dbt_refs: BTreeMap::new(),
        mock_table_functions: BTreeMap::new(),
        helpers: Vec::new(),
        scope: ScopeGraph::default(),
        expected: BTreeMap::new(),
        assertions: Vec::new(),
    };
    for cte in authored {
        if let Some(name) = cte.name.strip_prefix(REF_PREFIX) {
            fixtures.mock_refs.insert(name.to_string(), cte.sql_body);
        } else if let Some(name) = cte.name.strip_prefix(SOURCE_PREFIX) {
            fixtures.mock_sources.insert(name.to_string(), cte.sql_body);
        } else if let Some(name) = cte.name.strip_prefix(SEED_PREFIX) {
            fixtures.mock_seeds.insert(name.to_string(), cte.sql_body);
        } else if let Some(name) = cte.name.strip_prefix(DBT_REF_PREFIX) {
            fixtures
                .mock_dbt_refs
                .insert(name.to_string(), cte.sql_body);
        } else if let Some(name) = cte.name.strip_prefix(TABLE_FUNCTION_PREFIX) {
            fixtures
                .mock_table_functions
                .insert(name.to_string(), cte.sql_body);
        } else if !cte.name.starts_with(ASSERT_PREFIX) {
            fixtures.helpers.push(cte);
        }
    }
    for cte in expected {
        fixtures.expected.insert(
            cte.name
                .strip_prefix(EXPECTED_PREFIX)
                .unwrap_or(&cte.name)
                .to_string(),
            cte.sql_body,
        );
    }
    for cte in assertions {
        fixtures.assertions.push((
            cte.name
                .strip_prefix(ASSERT_PREFIX)
                .unwrap_or(&cte.name)
                .to_string(),
            cte.sql_body,
        ));
    }
    fixtures
}

fn topo_sort_model_chain(request: TopoSortRequest<'_>) -> Vec<String> {
    fn visit(
        name: &str,
        models: &HashMap<String, ModelInputOwned>,
        overrides: &BTreeMap<String, String>,
        mock_refs: &BTreeMap<String, String>,
        patterns: &SqlTestPatterns,
        visited: &mut HashSet<String>,
        ordered: &mut Vec<String>,
    ) {
        if !visited.insert(name.to_string()) {
            return;
        }
        if let Some(model) = models.get(name) {
            let mut dependencies = if let Some(override_sql) = overrides.get(name) {
                marker_names(&patterns.reference, &patterns.protected, override_sql)
            } else {
                model.model_dependencies.clone()
            };
            dependencies.retain(|dependency| {
                !mock_refs.contains_key(dependency) && models.contains_key(dependency)
            });
            dependencies.sort();
            dependencies.dedup();
            for dependency in dependencies {
                visit(
                    &dependency,
                    models,
                    overrides,
                    mock_refs,
                    patterns,
                    visited,
                    ordered,
                );
            }
        }
        ordered.push(name.to_string());
    }

    let mut roots = request.expected_names.to_vec();
    roots.sort();
    let mut visited: HashSet<String> = HashSet::new();
    let mut ordered: Vec<String> = Vec::new();
    for root in roots {
        visit(
            &root,
            request.models,
            request.overrides,
            request.mock_refs,
            request.patterns,
            &mut visited,
            &mut ordered,
        );
    }
    ordered
}

fn analyze_and_resolve_sql(
    request: AnalysisResolutionRequest<'_>,
) -> Result<Option<AnalysisResolvedSql>, String> {
    let Some(template) =
        analysis_template(request.query_sql, request.dialect_name, request.templates)?
    else {
        return Ok(None);
    };
    let mut generated_state = GeneratedCteState {
        names: template.existing_cte_names,
        ..GeneratedCteState::default()
    };
    let mut replacements: HashMap<(String, String), String> = HashMap::new();
    for (function_name, referenced_name) in template.marker_calls {
        let target = if function_name == REF_FUNCTION {
            if let Some(chain_sql) = request.resolved_chain.get(&referenced_name) {
                for (name, sql) in &chain_sql.generated_ctes {
                    generated_state.insert(name, sql, request.file_label)?;
                }
                let generated_name = format!("{REF_PREFIX}{referenced_name}");
                generated_state.insert(
                    &generated_name,
                    &chain_sql.cte_body_sql,
                    request.file_label,
                )?;
                Some(generated_name)
            } else {
                generated_state.mock_target(MockTargetRequest {
                    prefix: REF_PREFIX,
                    referenced_name: &referenced_name,
                    mocks: &request.fixtures.mock_refs,
                    fixtures: request.fixtures,
                    file_label: request.file_label,
                })?
            }
        } else if function_name == SOURCE_FUNCTION {
            generated_state.mock_target(MockTargetRequest {
                prefix: SOURCE_PREFIX,
                referenced_name: &referenced_name,
                mocks: &request.fixtures.mock_sources,
                fixtures: request.fixtures,
                file_label: request.file_label,
            })?
        } else if function_name == SEED_FUNCTION {
            generated_state.mock_target(MockTargetRequest {
                prefix: SEED_PREFIX,
                referenced_name: &referenced_name,
                mocks: &request.fixtures.mock_seeds,
                fixtures: request.fixtures,
                file_label: request.file_label,
            })?
        } else if function_name == DBT_REF_FUNCTION {
            generated_state.mock_target(MockTargetRequest {
                prefix: DBT_REF_PREFIX,
                referenced_name: &referenced_name,
                mocks: &request.fixtures.mock_dbt_refs,
                fixtures: request.fixtures,
                file_label: request.file_label,
            })?
        } else if function_name == UDF_FUNCTION || function_name == TABLE_FUNCTION {
            request
                .functions
                .get(&referenced_name)
                .map(|_| referenced_name.clone())
        } else {
            None
        };
        if let Some(target) = target {
            replacements.insert((function_name, referenced_name), target);
        }
    }
    let cte_body_sql = replace_relation_markers(request.query_sql, &replacements, request.patterns);
    let resolved_sql = assemble_resolved_sql(&cte_body_sql, &generated_state.generated);
    Ok(Some(AnalysisResolvedSql {
        resolved_sql,
        cte_body_sql,
        generated_ctes: generated_state.generated,
        reachable_mock_names: generated_state.reachable,
    }))
}

fn analysis_template(
    query_sql: &str,
    dialect_name: &str,
    templates: &AnalysisTemplateCache,
) -> Result<Option<AnalysisTemplate>, String> {
    cached_analysis_template(query_sql, templates, || {
        Dialect::get_by_name(dialect_name).and_then(|dialect| {
            let mut statements = match dialect.parse(query_sql) {
                Ok(statements) => statements,
                Err(_) => return None,
            };
            if statements.len() != 1 {
                return None;
            }
            let expression = statements.remove(0);
            let value = match serde_json::to_value(&expression) {
                Ok(value) => value,
                Err(_) => return None,
            };
            Some(AnalysisTemplate {
                existing_cte_names: top_level_cte_names(&expression),
                marker_calls: relation_marker_calls(&value),
            })
        })
    })
}

pub(crate) fn cached_analysis_template<F>(
    query_sql: &str,
    templates: &AnalysisTemplateCache,
    initialize: F,
) -> Result<Option<AnalysisTemplate>, String>
where
    F: FnOnce() -> Option<AnalysisTemplate>,
{
    let cached = {
        let mut cache = templates.lock().map_err(|error| error.to_string())?;
        Arc::clone(
            cache
                .entry(query_sql.to_string())
                .or_insert_with(|| Arc::new(OnceLock::new())),
        )
    };
    Ok(cached.get_or_init(initialize).clone())
}

/// Textually resolved SQL plus the mocks it reached and the mock CTEs its inlined mocks read.
struct TextualResolution {
    sql: String,
    reached: HashSet<String>,
    mock_ctes: Vec<(String, String)>,
}

fn resolve_textual_sql(request: TextualResolutionRequest<'_>) -> Result<TextualResolution, String> {
    let helper_with = helper_with_clause(&request.fixtures.helpers);
    let mut reached: HashSet<String> = HashSet::new();
    let mut inlined: Vec<String> = Vec::new();
    let mut chain_references = request.chain_references;
    let mut result = replace_named_markers(
        request.query_sql,
        &request.patterns.reference,
        &request.patterns.protected,
        |name| {
            if let Some(sql) = request.resolved_chain.get(name) {
                if let Some(references) = chain_references.as_deref_mut()
                    && !references.iter().any(|existing| existing == name)
                {
                    references.push(name.to_string());
                }
                return Some(sql.clone());
            }
            request.fixtures.mock_refs.get(name).map(|sql| {
                reached.insert(name.to_string());
                inlined.push(format!("{REF_PREFIX}{name}"));
                wrap_mock(sql, &helper_with)
            })
        },
    );
    result = replace_named_markers(
        &result,
        &request.patterns.source,
        &request.patterns.protected,
        |name| {
            request.fixtures.mock_sources.get(name).map(|sql| {
                reached.insert(name.to_string());
                inlined.push(format!("{SOURCE_PREFIX}{name}"));
                wrap_mock(sql, &helper_with)
            })
        },
    );
    result = replace_named_markers(
        &result,
        &request.patterns.seed,
        &request.patterns.protected,
        |name| {
            request.fixtures.mock_seeds.get(name).map(|sql| {
                reached.insert(name.to_string());
                inlined.push(format!("{SEED_PREFIX}{name}"));
                wrap_mock(sql, &helper_with)
            })
        },
    );
    result = replace_dbt_ref_markers(
        &result,
        &request.patterns.dbt_reference,
        &request.patterns.protected,
        |name| {
            request.fixtures.mock_dbt_refs.get(name).map(|sql| {
                reached.insert(name.to_string());
                inlined.push(format!("{DBT_REF_PREFIX}{name}"));
                wrap_mock(sql, &helper_with)
            })
        },
    );
    let (table_resolved, table_reached) = resolve_table_function_fixtures(
        &result,
        &request.fixtures.mock_table_functions,
        &request.fixtures.helpers,
        request.patterns,
    )?;
    reached.extend(table_reached);
    result = resolve_function_calls(&table_resolved, request.functions, false, request.patterns)?;
    result = resolve_function_calls(&result, request.functions, true, request.patterns)?;
    let mut mock_ctes: Vec<(String, String)> = Vec::new();
    for generated_name in inlined {
        for dependency in request.fixtures.scope.mock_dependencies(&generated_name) {
            reached.insert(dependency.mock_name.clone());
            if !mock_ctes
                .iter()
                .any(|(name, _)| *name == dependency.generated_name)
            {
                mock_ctes.push((dependency.generated_name.clone(), dependency.sql.clone()));
            }
        }
    }
    Ok(TextualResolution {
        sql: result,
        reached,
        mock_ctes,
    })
}

fn resolve_table_function_fixtures(
    sql: &str,
    fixtures: &BTreeMap<String, String>,
    helpers: &[CteInput],
    patterns: &SqlTestPatterns,
) -> Result<(String, HashSet<String>), String> {
    if fixtures.is_empty() {
        return Ok((sql.to_string(), HashSet::new()));
    }
    let helper_with = helper_with_clause(helpers);
    replace_callable_markers(
        sql,
        &patterns.table_function,
        &patterns.protected,
        |name, _call_suffix| {
            fixtures
                .get(name)
                .map(|body| (wrap_mock(body, &helper_with), true))
        },
    )
}

fn resolve_function_calls(
    sql: &str,
    functions: &HashMap<String, FunctionInput>,
    table_function: bool,
    patterns: &SqlTestPatterns,
) -> Result<String, String> {
    let pattern = if table_function {
        &patterns.table_function
    } else {
        &patterns.udf
    };
    let (result, _) =
        replace_callable_markers(sql, pattern, &patterns.protected, |name, call_suffix| {
            let function = functions.get(name)?;
            let (prefix, suffix) = if table_function {
                (
                    function.table_function_prefix.as_deref()?,
                    function.table_function_suffix.as_deref()?,
                )
            } else {
                (
                    function.udf_prefix.as_deref()?,
                    function.udf_suffix.as_deref()?,
                )
            };
            Some((format!("{prefix}{call_suffix}{suffix}"), false))
        })?;
    Ok(result)
}

fn relation_marker_calls(value: &Value) -> Vec<(String, String)> {
    fn marker(expression: &Value) -> Option<(String, String)> {
        let object = expression.as_object()?;
        if let Some(alias) = object.get("alias") {
            return marker(alias.get("this")?);
        }
        let function = object.get("function")?.as_object()?;
        let function_name = function.get("name")?.as_str()?.to_ascii_lowercase();
        let args = function.get("args")?.as_array()?;
        let arg_name = |arg: &Value| {
            arg.get("column")?
                .get("name")?
                .get("name")?
                .as_str()
                .map(str::to_string)
        };
        let referenced_name = if function_name == DBT_REF_FUNCTION {
            match args.as_slice() {
                [first] => arg_name(first)?,
                [first, second] => format!("{}__{}", arg_name(first)?, arg_name(second)?),
                _ => return None,
            }
        } else {
            let [first] = args.as_slice() else {
                return None;
            };
            arg_name(first)?
        };
        Some((function_name, referenced_name))
    }

    fn walk(value: &Value, calls: &mut Vec<(String, String)>) {
        match value {
            Value::Object(object) => {
                if let Some(expressions) = object
                    .get("from")
                    .and_then(|from| from.get("expressions"))
                    .and_then(Value::as_array)
                {
                    calls.extend(expressions.iter().filter_map(marker));
                }
                if let Some(joins) = object.get("joins").and_then(Value::as_array) {
                    calls.extend(
                        joins
                            .iter()
                            .filter_map(|join| join.get("this"))
                            .filter_map(marker),
                    );
                }
                for child in object.values() {
                    walk(child, calls);
                }
            }
            Value::Array(values) => {
                for child in values {
                    walk(child, calls);
                }
            }
            _ => {}
        }
    }

    let mut calls: Vec<(String, String)> = Vec::new();
    walk(value, &mut calls);
    calls
}

fn top_level_cte_names(expression: &Expression) -> HashSet<String> {
    let Expression::Select(select) = expression else {
        return HashSet::new();
    };
    let Some(with) = select.with.as_ref() else {
        return HashSet::new();
    };
    with.ctes.iter().map(|cte| cte.alias.name.clone()).collect()
}

fn replace_relation_markers(
    sql: &str,
    replacements: &HashMap<(String, String), String>,
    patterns: &SqlTestPatterns,
) -> String {
    let mut result = sql.to_string();
    for (function_name, pattern) in [
        (REF_FUNCTION, &patterns.reference),
        (SOURCE_FUNCTION, &patterns.source),
        (SEED_FUNCTION, &patterns.seed),
    ] {
        result = replace_named_markers(&result, pattern, &patterns.protected, |name| {
            replacements
                .get(&(function_name.to_string(), name.to_string()))
                .cloned()
        });
    }
    replace_dbt_ref_markers(
        &result,
        &patterns.dbt_reference,
        &patterns.protected,
        |name| {
            replacements
                .get(&(DBT_REF_FUNCTION.to_string(), name.to_string()))
                .cloned()
        },
    )
}

fn assemble_resolved_sql(cte_body_sql: &str, generated: &[(String, String)]) -> String {
    if generated.is_empty() {
        return cte_body_sql.to_string();
    }
    let generated_sql = generated
        .iter()
        .map(|(name, sql)| cte_definition_sql(name, sql))
        .collect::<Vec<_>>()
        .join(", ");
    if let Some(with_end) = leading_with_prefix_end(cte_body_sql) {
        format!(
            "{}{generated_sql}, {}",
            &cte_body_sql[..with_end],
            &cte_body_sql[with_end..]
        )
    } else {
        format!("WITH {generated_sql} {cte_body_sql}")
    }
}

pub(crate) fn leading_with_prefix_end(sql: &str) -> Option<usize> {
    let mut index = skip_leading_ignorable(sql, 0);
    index = keyword_end(sql, index, "WITH")?;
    index = skip_leading_ignorable(sql, index);
    if let Some(recursive_end) = keyword_end(sql, index, "RECURSIVE") {
        index = skip_leading_ignorable(sql, recursive_end);
    }
    Some(index)
}

fn skip_leading_ignorable(sql: &str, mut index: usize) -> usize {
    while index < sql.len() {
        let byte = sql.as_bytes()[index];
        if byte.is_ascii_whitespace() {
            index += 1;
        } else if sql[index..].starts_with("--") {
            index = sql[index..]
                .find('\n')
                .map_or(sql.len(), |offset| index + offset + 1);
        } else if sql[index..].starts_with("/*") {
            let Some(offset) = sql[index + 2..].find("*/") else {
                return index;
            };
            index += offset + 4;
        } else {
            break;
        }
    }
    index
}

fn keyword_end(sql: &str, start: usize, keyword: &str) -> Option<usize> {
    let end = start + keyword.len();
    if !sql.get(start..end)?.eq_ignore_ascii_case(keyword) {
        return None;
    }
    if sql
        .as_bytes()
        .get(end)
        .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
    {
        return None;
    }
    Some(end)
}

struct UnresolvedReferenceRequest<'a> {
    sql: &'a str,
    test_name: &'a str,
    model_name: &'a str,
    patterns: &'a SqlTestPatterns,
    reported: &'a mut HashSet<(&'static str, String)>,
}

/// Report each unmocked reference once per test, attributed to the first step reaching it.
fn unresolved_reference_warnings(request: UnresolvedReferenceRequest<'_>) -> Vec<PlanWarning> {
    let UnresolvedReferenceRequest {
        sql,
        test_name,
        model_name,
        patterns,
        reported,
    } = request;
    if !patterns.test_reference.is_match(sql) {
        return Vec::new();
    }
    let mut warnings: Vec<PlanWarning> = Vec::new();
    let mut warn = |kind: &'static str, name: String, message: String| {
        if reported.insert((kind, name)) {
            warnings.push(PlanWarning {
                model_name: Some(model_name.to_string()),
                severity: "error",
                message,
            });
        }
    };
    for name in marker_names(&patterns.reference, &patterns.protected, sql) {
        let message = format!(
            "test '{test_name}': model '{model_name}' references __ref('{name}') which has no mock and is not in the expected chain"
        );
        warn(REF_FUNCTION, name, message);
    }
    for (pattern, function_name) in [
        (&patterns.source, SOURCE_FUNCTION),
        (&patterns.seed, SEED_FUNCTION),
    ] {
        for name in marker_names(pattern, &patterns.protected, sql) {
            let message = format!(
                "test '{test_name}': model '{model_name}' references {function_name}('{name}') which has no mock"
            );
            warn(function_name, name, message);
        }
    }
    let protected = protected_ranges(&patterns.protected, sql);
    for captures in patterns.dbt_reference.captures_iter(sql) {
        let Some(full) = captures.get(0) else {
            continue;
        };
        if in_protected_range(full.start(), &protected) {
            continue;
        }
        let Some(first) = captures.get(1).map(|value| value.as_str()) else {
            continue;
        };
        let name = captures.get(2).map_or_else(
            || first.to_string(),
            |second| format!("{first}__{}", second.as_str()),
        );
        let message = format!(
            "test '{test_name}': model '{model_name}' references __dbt_ref__{name} which has no mock"
        );
        warn(DBT_REF_FUNCTION, name, message);
    }
    warnings
}

fn unreachable_mock_warnings(
    test_name: &str,
    reachable: &HashSet<String>,
    fixtures: &TestFixtures,
) -> Vec<PlanWarning> {
    let groups = [
        (
            &fixtures.mock_refs,
            REF_PREFIX,
            " is unreachable because a downstream model is also in the expected chain",
        ),
        (&fixtures.mock_sources, SOURCE_PREFIX, " is unreachable"),
        (&fixtures.mock_seeds, SEED_PREFIX, " is unreachable"),
        (&fixtures.mock_dbt_refs, DBT_REF_PREFIX, " is unreachable"),
        (
            &fixtures.mock_table_functions,
            TABLE_FUNCTION_PREFIX,
            " is unreachable",
        ),
    ];
    let mut warnings: Vec<PlanWarning> = Vec::new();
    for (mocks, prefix, suffix) in groups {
        for name in mocks.keys().filter(|name| !reachable.contains(*name)) {
            warnings.push(PlanWarning {
                model_name: None,
                severity: "warning",
                message: format!("test '{test_name}' mock {prefix}{name}{suffix}"),
            });
        }
    }
    warnings
}

fn assertion_ref_targets(
    assertions: &[(String, String)],
    patterns: &SqlTestPatterns,
) -> Vec<String> {
    let mut targets: Vec<String> = Vec::new();
    for (_, sql) in assertions {
        targets.extend(marker_names(&patterns.reference, &patterns.protected, sql));
    }
    dedupe(targets)
}

fn has_unresolved_test_reference(sql: &str, patterns: &SqlTestPatterns) -> bool {
    if !patterns.test_reference.is_match(sql) {
        return false;
    }
    !marker_names(&patterns.reference, &patterns.protected, sql).is_empty()
        || !marker_names(&patterns.source, &patterns.protected, sql).is_empty()
        || !marker_names(&patterns.seed, &patterns.protected, sql).is_empty()
        || patterns.dbt_reference.is_match(sql)
        || patterns.table_function.is_match(sql)
}

fn helper_with_clause(helpers: &[CteInput]) -> String {
    if helpers.is_empty() {
        return String::new();
    }
    format!(
        "WITH {}",
        helpers
            .iter()
            .map(|cte| cte_definition_sql(&cte.name, &cte.sql_body))
            .collect::<Vec<_>>()
            .join(", ")
    )
}

/// Generated mock CTE body: the authored mock with every helper CTE in scope.
pub(crate) fn mock_cte_sql(mock_body: &str, helpers: &[CteInput]) -> String {
    if helpers.is_empty() {
        mock_body.to_string()
    } else {
        format!("{} {mock_body}", helper_with_clause(helpers))
    }
}

fn cte_definition_sql(name: &str, sql: &str) -> String {
    let body = sql.trim_end();
    let final_line = body.rsplit_once('\n').map_or(body, |(_, line)| line);
    let terminator = if final_line.contains("--") { "\n" } else { "" };
    format!("{name} AS ({body}{terminator})")
}

fn wrap_mock(sql: &str, helper_with: &str) -> String {
    if helper_with.is_empty() {
        format!("({sql})")
    } else {
        format!("({helper_with} {sql})")
    }
}

fn wrap_direct_sql(sql: &str, helper_with: &str) -> String {
    if helper_with.is_empty() {
        sql.to_string()
    } else {
        format!("{helper_with} {sql}")
    }
}

fn dedupe(mut values: Vec<String>) -> Vec<String> {
    let mut seen: HashSet<String> = HashSet::new();
    values.retain(|value| seen.insert(value.clone()));
    values
}

fn compile_pattern(pattern: &str) -> Result<Regex, String> {
    Regex::new(pattern)
        .map_err(|error| planner_error(&format!("invalid SQL-test pattern: {error}")))
}

fn default_workers() -> usize {
    DEFAULT_WORKERS
}

fn default_true() -> bool {
    true
}

fn default_set_difference() -> String {
    "EXCEPT".to_string()
}

pub(crate) fn compile_error(message: &str) -> String {
    format!("compile_input:{message}")
}

fn planner_error(message: &str) -> String {
    format!("planner_input:{message}")
}
