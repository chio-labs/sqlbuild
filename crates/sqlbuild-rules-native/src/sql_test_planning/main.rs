//! Coarse project-level planning for SQL-native test artifacts.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Instant;

use polyglot_sql::{Dialect, Expression};
use rayon::iter::{IntoParallelIterator, ParallelIterator};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::sql_test_rendering::main::{
    AssertionStep, ChainStep, RenderRequest, render_comparison_sql,
};

const DEFAULT_WORKERS: usize = 4;
const MAX_WORKERS: usize = 4;
const WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;
const REF_PREFIX: &str = "__ref__";
const SOURCE_PREFIX: &str = "__source__";
const SEED_PREFIX: &str = "__seed__";
const DBT_REF_PREFIX: &str = "__dbt_ref__";
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
struct CteInput {
    name: String,
    sql_body: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PlanResponse {
    sql: String,
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
    analysis_templates: Arc<Mutex<HashMap<String, Option<AnalysisTemplate>>>>,
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
struct AnalysisTemplate {
    existing_cte_names: HashSet<String>,
    marker_calls: Vec<(String, String)>,
}

struct TestFixtures {
    mock_refs: BTreeMap<String, String>,
    mock_sources: BTreeMap<String, String>,
    mock_seeds: BTreeMap<String, String>,
    mock_dbt_refs: BTreeMap<String, String>,
    mock_table_functions: BTreeMap<String, String>,
    helpers: Vec<CteInput>,
    expected: BTreeMap<String, String>,
    assertions: Vec<(String, String)>,
}

pub(crate) fn plan_and_render_json(request_json: &str) -> Result<String, String> {
    let request: PlanBatchRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
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
                let planned = plan_test(test, &context)?;
                let planning_ns = planning_start.elapsed().as_nanos();
                let rendering_start = Instant::now();
                let response = PlanResponse {
                    sql: render_comparison_sql(planned.request),
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
    let planning_ns = if measured_cpu_ns == 0 {
        batch_ns
    } else {
        batch_ns.saturating_mul(planning_cpu_ns) / measured_cpu_ns
    };
    let rendering_ns = batch_ns.saturating_sub(planning_ns);
    let artifacts = responses
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
            test.name,
            mode,
            actual_cte,
            expected_cte,
            helper_ctes,
            context,
        ),
        TestPayload::Model {
            authored_ctes,
            model_query_overrides,
            expected_ctes,
            expected_model_names,
            assertion_ctes,
        } => plan_model_test(
            test.name,
            test.file_label,
            authored_ctes,
            model_query_overrides,
            expected_ctes,
            expected_model_names,
            assertion_ctes,
            context,
        ),
    }
}

fn plan_direct_test(
    name: String,
    mode: String,
    actual_cte: CteInput,
    expected_cte: CteInput,
    helpers: Vec<CteInput>,
    context: &ProjectContext,
) -> Result<PlannedResponse, String> {
    let helper_with = helper_with_clause(&helpers);
    let mut actual_sql = actual_cte.sql_body;
    if mode == "udf" {
        actual_sql = resolve_function_calls(&actual_sql, &context.functions, false)?;
    } else if mode == "table_fn" {
        actual_sql = resolve_function_calls(&actual_sql, &context.functions, true)?;
    }
    let model_name = format!("{mode} {name}");
    let request = RenderRequest {
        chain: vec![ChainStep {
            model_name: model_name.clone(),
            resolved_sql: wrap_direct_sql(&actual_sql, &helper_with),
            expected_cte_sql: Some(wrap_direct_sql(&expected_cte.sql_body, &helper_with)),
            lifted_ctes: Vec::new(),
            comparison_body_sql: None,
        }],
        assertions: Vec::new(),
        sql_analysis_enabled: context.sql_analysis_enabled,
        set_difference_operator: context.set_difference_operator.clone(),
        _sql_analysis_dialect: Some(context.dialect.clone()),
    };
    Ok(PlannedResponse {
        request,
        model_names: vec![model_name],
        warnings: Vec::new(),
    })
}

#[allow(clippy::too_many_arguments)]
fn plan_model_test(
    test_name: String,
    file_label: String,
    authored_ctes: Vec<CteInput>,
    model_query_overrides: BTreeMap<String, String>,
    expected_ctes: Vec<CteInput>,
    expected_model_names: Vec<String>,
    assertion_ctes: Vec<CteInput>,
    context: &ProjectContext,
) -> Result<PlannedResponse, String> {
    let fixtures = classify_fixtures(authored_ctes, expected_ctes, assertion_ctes);
    let mut expected_names = expected_model_names;
    expected_names.extend(assertion_ref_targets(&fixtures.assertions));
    dedupe_in_place(&mut expected_names);
    let ordered_names = topo_sort_model_chain(
        &expected_names,
        &context.models,
        &model_query_overrides,
        &fixtures.mock_refs,
    );
    let mut warnings = Vec::new();
    let mut reachable_mocks = HashSet::new();
    let mut analysis_resolved: HashMap<String, AnalysisResolvedSql> = HashMap::new();
    let mut textual_resolved: HashMap<String, String> = HashMap::new();
    let mut chain = Vec::new();

    for (model_index, model_name) in ordered_names.iter().enumerate() {
        let Some(model) = context.models.get(model_name) else {
            warnings.push(PlanWarning {
                model_name: None,
                severity: "error",
                message: format!(
                    "test '{test_name}' expects model '{model_name}' which does not exist"
                ),
            });
            continue;
        };
        let query_sql = model_query_overrides
            .get(model_name)
            .unwrap_or(&model.query_sql);
        let (fixture_resolved_sql, reached_table_functions) = resolve_table_function_fixtures(
            query_sql,
            &fixtures.mock_table_functions,
            &fixtures.helpers,
        )?;
        reachable_mocks.extend(reached_table_functions);
        let analyzed = if context.sql_analysis_enabled {
            analyze_and_resolve_sql(
                &fixture_resolved_sql,
                &fixtures,
                &analysis_resolved,
                &context.functions,
                &file_label,
                &context.dialect,
                &context.analysis_templates,
            )?
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
            let (resolved, reached) = ensure_textual_chain_through(
                &ordered_names[..=model_index],
                &model_query_overrides,
                &fixtures,
                context,
                &mut textual_resolved,
            )?;
            reachable_mocks.extend(reached);
            (resolved, Vec::new(), None)
        };
        warnings.extend(unresolved_reference_warnings(
            &resolved_sql,
            &test_name,
            model_name,
        ));
        chain.push(ChainStep {
            model_name: model_name.clone(),
            resolved_sql,
            expected_cte_sql: fixtures.expected.get(model_name).cloned(),
            lifted_ctes,
            comparison_body_sql,
        });
    }

    let mut assertions = Vec::new();
    let mut textual_assertion_chain: Option<HashMap<String, String>> = None;
    for (assertion_name, assertion_sql) in &fixtures.assertions {
        let (fixture_resolved_sql, reached_table_functions) = resolve_table_function_fixtures(
            assertion_sql,
            &fixtures.mock_table_functions,
            &fixtures.helpers,
        )?;
        reachable_mocks.extend(reached_table_functions);
        let analyzed = if context.sql_analysis_enabled {
            analyze_and_resolve_sql(
                &fixture_resolved_sql,
                &fixtures,
                &analysis_resolved,
                &context.functions,
                &file_label,
                &context.dialect,
                &context.analysis_templates,
            )?
        } else {
            None
        };
        let (resolved_sql, lifted_ctes, comparison_body_sql) = match analyzed {
            Some(value) if !has_unresolved_test_reference(&value.resolved_sql) => {
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
                        &model_query_overrides,
                        &fixtures,
                        context,
                    )?;
                    reachable_mocks.extend(reached);
                    textual_assertion_chain = Some(chain);
                }
                let (resolved, reached) = resolve_assertion_textual_sql(
                    &fixture_resolved_sql,
                    &fixtures,
                    textual_assertion_chain
                        .as_ref()
                        .expect("textual assertion chain is initialized"),
                    &context.functions,
                    context.requires_derived_table_aliases,
                )?;
                reachable_mocks.extend(reached);
                (resolved, Vec::new(), None)
            }
        };
        assertions.push(AssertionStep {
            name: assertion_name.clone(),
            resolved_sql,
            lifted_ctes,
            comparison_body_sql,
        });
    }
    warnings.extend(unreachable_mock_warnings(
        &test_name,
        &reachable_mocks,
        &fixtures,
    ));
    let model_names = chain.iter().map(|step| step.model_name.clone()).collect();
    let request = RenderRequest {
        chain,
        assertions,
        sql_analysis_enabled: context.sql_analysis_enabled,
        set_difference_operator: context.set_difference_operator.clone(),
        _sql_analysis_dialect: Some(context.dialect.clone()),
    };
    Ok(PlannedResponse {
        request,
        model_names,
        warnings,
    })
}

fn ensure_textual_chain_through(
    ordered_names: &[String],
    overrides: &BTreeMap<String, String>,
    fixtures: &TestFixtures,
    context: &ProjectContext,
    resolved_chain: &mut HashMap<String, String>,
) -> Result<(String, HashSet<String>), String> {
    let mut reachable = HashSet::new();
    for model_name in ordered_names {
        if resolved_chain.contains_key(model_name) {
            continue;
        }
        let Some(model) = context.models.get(model_name) else {
            continue;
        };
        let query_sql = overrides.get(model_name).unwrap_or(&model.query_sql);
        let (resolved_sql, reached) =
            resolve_textual_sql(query_sql, fixtures, resolved_chain, &context.functions)?;
        reachable.extend(reached);
        resolved_chain.insert(model_name.clone(), format!("({resolved_sql})"));
    }
    let current_name = ordered_names
        .last()
        .ok_or_else(|| "textual SQL-test chain is empty".to_string())?;
    let wrapped = resolved_chain
        .get(current_name)
        .ok_or_else(|| format!("SQL-test model '{current_name}' could not be resolved"))?;
    let body = wrapped
        .strip_prefix('(')
        .and_then(|value| value.strip_suffix(')'))
        .unwrap_or(wrapped)
        .to_string();
    Ok((body, reachable))
}

fn build_textual_chain(
    ordered_names: &[String],
    overrides: &BTreeMap<String, String>,
    fixtures: &TestFixtures,
    context: &ProjectContext,
) -> Result<(HashMap<String, String>, HashSet<String>), String> {
    let mut resolved_chain = HashMap::new();
    let mut reachable = HashSet::new();
    for model_name in ordered_names {
        let Some(model) = context.models.get(model_name) else {
            continue;
        };
        let query_sql = overrides.get(model_name).unwrap_or(&model.query_sql);
        let (resolved_sql, reached) =
            resolve_textual_sql(query_sql, fixtures, &resolved_chain, &context.functions)?;
        reachable.extend(reached);
        resolved_chain.insert(model_name.clone(), format!("({resolved_sql})"));
    }
    Ok((resolved_chain, reachable))
}

fn resolve_assertion_textual_sql(
    assertion_sql: &str,
    fixtures: &TestFixtures,
    resolved_chain: &HashMap<String, String>,
    functions: &HashMap<String, FunctionInput>,
    requires_flat_ctes: bool,
) -> Result<(String, HashSet<String>), String> {
    if requires_flat_ctes && leading_with_prefix_end(assertion_sql).is_some() {
        return Err(planner_error(
            "SQL test assertion fallback cannot safely flatten an assertion beginning with WITH",
        ));
    }
    let mut assertion_chain = HashMap::new();
    let mut cte_parts = Vec::new();
    let mut seen = HashSet::new();
    for name in marker_names(ref_pattern(), assertion_sql) {
        if !seen.insert(name.clone()) {
            continue;
        }
        let Some(resolved_sql) = resolved_chain.get(&name) else {
            continue;
        };
        let mut body = resolved_sql.trim();
        if body.starts_with('(') && body.ends_with(')') {
            body = body[1..body.len() - 1].trim();
        }
        if requires_flat_ctes && leading_with_prefix_end(body).is_some() {
            return Err(planner_error(
                "SQL test assertion fallback cannot safely flatten a referenced model beginning with WITH",
            ));
        }
        let cte_name = format!("{REF_PREFIX}{name}");
        assertion_chain.insert(name, cte_name.clone());
        cte_parts.push(cte_definition_sql(&cte_name, body));
    }
    let (resolved_sql, reached) =
        resolve_textual_sql(assertion_sql, fixtures, &assertion_chain, functions)?;
    if cte_parts.is_empty() {
        Ok((resolved_sql, reached))
    } else {
        Ok((
            format!("WITH {} {resolved_sql}", cte_parts.join(", ")),
            reached,
        ))
    }
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

fn topo_sort_model_chain(
    expected_names: &[String],
    models: &HashMap<String, ModelInputOwned>,
    overrides: &BTreeMap<String, String>,
    mock_refs: &BTreeMap<String, String>,
) -> Vec<String> {
    fn visit(
        name: &str,
        models: &HashMap<String, ModelInputOwned>,
        overrides: &BTreeMap<String, String>,
        mock_refs: &BTreeMap<String, String>,
        visited: &mut HashSet<String>,
        ordered: &mut Vec<String>,
    ) {
        if !visited.insert(name.to_string()) {
            return;
        }
        if let Some(model) = models.get(name) {
            let mut dependencies = if let Some(override_sql) = overrides.get(name) {
                marker_names(ref_pattern(), override_sql)
            } else {
                model.model_dependencies.clone()
            };
            dependencies.retain(|dependency| {
                !mock_refs.contains_key(dependency) && models.contains_key(dependency)
            });
            dependencies.sort();
            dependencies.dedup();
            for dependency in dependencies {
                visit(&dependency, models, overrides, mock_refs, visited, ordered);
            }
        }
        ordered.push(name.to_string());
    }

    let mut roots = expected_names.to_vec();
    roots.sort();
    let mut visited = HashSet::new();
    let mut ordered = Vec::new();
    for root in roots {
        visit(
            &root,
            models,
            overrides,
            mock_refs,
            &mut visited,
            &mut ordered,
        );
    }
    ordered
}

fn analyze_and_resolve_sql(
    query_sql: &str,
    fixtures: &TestFixtures,
    resolved_chain: &HashMap<String, AnalysisResolvedSql>,
    functions: &HashMap<String, FunctionInput>,
    file_label: &str,
    dialect_name: &str,
    templates: &Mutex<HashMap<String, Option<AnalysisTemplate>>>,
) -> Result<Option<AnalysisResolvedSql>, String> {
    let Some(template) = analysis_template(query_sql, dialect_name, templates)? else {
        return Ok(None);
    };
    let mut names = template.existing_cte_names;
    let mut generated_ctes = Vec::new();
    let mut reachable = HashSet::new();
    let mut replacements = HashMap::new();
    for (function_name, referenced_name) in template.marker_calls {
        let target = if function_name == REF_FUNCTION {
            if let Some(chain_sql) = resolved_chain.get(&referenced_name) {
                for (name, sql) in &chain_sql.generated_ctes {
                    insert_generated_cte(&mut generated_ctes, &mut names, name, sql, file_label)?;
                }
                let generated_name = format!("{REF_PREFIX}{referenced_name}");
                insert_generated_cte(
                    &mut generated_ctes,
                    &mut names,
                    &generated_name,
                    &chain_sql.cte_body_sql,
                    file_label,
                )?;
                Some(generated_name)
            } else {
                mock_target(
                    REF_PREFIX,
                    &referenced_name,
                    &fixtures.mock_refs,
                    fixtures,
                    &mut generated_ctes,
                    &mut names,
                    &mut reachable,
                    file_label,
                )?
            }
        } else if function_name == SOURCE_FUNCTION {
            mock_target(
                SOURCE_PREFIX,
                &referenced_name,
                &fixtures.mock_sources,
                fixtures,
                &mut generated_ctes,
                &mut names,
                &mut reachable,
                file_label,
            )?
        } else if function_name == SEED_FUNCTION {
            mock_target(
                SEED_PREFIX,
                &referenced_name,
                &fixtures.mock_seeds,
                fixtures,
                &mut generated_ctes,
                &mut names,
                &mut reachable,
                file_label,
            )?
        } else if function_name == DBT_REF_FUNCTION {
            mock_target(
                DBT_REF_PREFIX,
                &referenced_name,
                &fixtures.mock_dbt_refs,
                fixtures,
                &mut generated_ctes,
                &mut names,
                &mut reachable,
                file_label,
            )?
        } else if function_name == UDF_FUNCTION || function_name == TABLE_FUNCTION {
            functions
                .get(&referenced_name)
                .map(|_| referenced_name.clone())
        } else {
            None
        };
        if let Some(target) = target {
            replacements.insert((function_name, referenced_name), target);
        }
    }
    let cte_body_sql = replace_relation_markers(query_sql, &replacements);
    let resolved_sql = assemble_resolved_sql(&cte_body_sql, &generated_ctes);
    Ok(Some(AnalysisResolvedSql {
        resolved_sql,
        cte_body_sql,
        generated_ctes,
        reachable_mock_names: reachable,
    }))
}

fn analysis_template(
    query_sql: &str,
    dialect_name: &str,
    templates: &Mutex<HashMap<String, Option<AnalysisTemplate>>>,
) -> Result<Option<AnalysisTemplate>, String> {
    if let Some(cached) = templates
        .lock()
        .map_err(|error| error.to_string())?
        .get(query_sql)
        .cloned()
    {
        return Ok(cached);
    }
    let parsed = Dialect::get_by_name(dialect_name).and_then(|dialect| {
        let mut statements = dialect.parse(query_sql).ok()?;
        if statements.len() != 1 {
            return None;
        }
        let expression = statements.remove(0);
        let value = serde_json::to_value(&expression).ok()?;
        Some(AnalysisTemplate {
            existing_cte_names: top_level_cte_names(&expression),
            marker_calls: relation_marker_calls(&value),
        })
    });
    let mut cache = templates.lock().map_err(|error| error.to_string())?;
    let cached = cache
        .entry(query_sql.to_string())
        .or_insert_with(|| parsed.clone());
    Ok(cached.clone())
}

fn insert_generated_cte(
    generated: &mut Vec<(String, String)>,
    names: &mut HashSet<String>,
    name: &str,
    sql: &str,
    file_label: &str,
) -> Result<(), String> {
    if let Some((_, existing)) = generated
        .iter()
        .find(|(existing_name, _)| existing_name == name)
    {
        if existing == sql {
            return Ok(());
        }
    }
    if names.contains(name) && !generated.iter().any(|(existing, _)| existing == name) {
        return Err(compile_error(&format!(
            "SQL test '{file_label}' defines CTE '{name}', which conflicts with the generated CTE"
        )));
    }
    if names.insert(name.to_string()) {
        generated.push((name.to_string(), sql.to_string()));
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn mock_target(
    prefix: &str,
    referenced_name: &str,
    mocks: &BTreeMap<String, String>,
    fixtures: &TestFixtures,
    generated: &mut Vec<(String, String)>,
    names: &mut HashSet<String>,
    reachable: &mut HashSet<String>,
    file_label: &str,
) -> Result<Option<String>, String> {
    let Some(mock_body) = mocks.get(referenced_name) else {
        return Ok(None);
    };
    reachable.insert(referenced_name.to_string());
    let generated_name = format!("{prefix}{referenced_name}");
    if names.contains(&generated_name)
        && !generated
            .iter()
            .any(|(existing_name, _)| existing_name == &generated_name)
    {
        let referenced_kind = prefix.trim_matches('_');
        return Err(compile_error(&format!(
            "SQL test '{file_label}' defines CTE '{generated_name}', which conflicts with the generated {referenced_kind} CTE for '{referenced_name}'"
        )));
    }
    let sql = if fixtures.helpers.is_empty() {
        mock_body.clone()
    } else {
        format!("{} {mock_body}", helper_with_clause(&fixtures.helpers))
    };
    insert_generated_cte(generated, names, &generated_name, &sql, file_label)?;
    Ok(Some(generated_name))
}

fn resolve_textual_sql(
    query_sql: &str,
    fixtures: &TestFixtures,
    resolved_chain: &HashMap<String, String>,
    functions: &HashMap<String, FunctionInput>,
) -> Result<(String, HashSet<String>), String> {
    let helper_with = helper_with_clause(&fixtures.helpers);
    let mut reached = HashSet::new();
    let mut result = replace_named_markers(query_sql, ref_pattern(), |name| {
        if let Some(sql) = resolved_chain.get(name) {
            return Some(sql.clone());
        }
        fixtures.mock_refs.get(name).map(|sql| {
            reached.insert(name.to_string());
            wrap_mock(sql, &helper_with)
        })
    });
    result = replace_named_markers(&result, source_pattern(), |name| {
        fixtures.mock_sources.get(name).map(|sql| {
            reached.insert(name.to_string());
            wrap_mock(sql, &helper_with)
        })
    });
    result = replace_named_markers(&result, seed_pattern(), |name| {
        fixtures.mock_seeds.get(name).map(|sql| {
            reached.insert(name.to_string());
            wrap_mock(sql, &helper_with)
        })
    });
    result = replace_dbt_ref_markers(&result, |name| {
        fixtures.mock_dbt_refs.get(name).map(|sql| {
            reached.insert(name.to_string());
            wrap_mock(sql, &helper_with)
        })
    });
    let (table_resolved, table_reached) = resolve_table_function_fixtures(
        &result,
        &fixtures.mock_table_functions,
        &fixtures.helpers,
    )?;
    reached.extend(table_reached);
    result = resolve_function_calls(&table_resolved, functions, false)?;
    result = resolve_function_calls(&result, functions, true)?;
    Ok((result, reached))
}

fn resolve_table_function_fixtures(
    sql: &str,
    fixtures: &BTreeMap<String, String>,
    helpers: &[CteInput],
) -> Result<(String, HashSet<String>), String> {
    if fixtures.is_empty() {
        return Ok((sql.to_string(), HashSet::new()));
    }
    let helper_with = helper_with_clause(helpers);
    replace_callable_markers(sql, table_function_pattern(), |name, _call_suffix| {
        fixtures
            .get(name)
            .map(|body| (wrap_mock(body, &helper_with), true))
    })
}

fn resolve_function_calls(
    sql: &str,
    functions: &HashMap<String, FunctionInput>,
    table_function: bool,
) -> Result<String, String> {
    let pattern = if table_function {
        table_function_pattern()
    } else {
        udf_pattern()
    };
    let (result, _) = replace_callable_markers(sql, pattern, |name, call_suffix| {
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

fn replace_callable_markers<F>(
    sql: &str,
    pattern: &Regex,
    mut replacement: F,
) -> Result<(String, HashSet<String>), String>
where
    F: FnMut(&str, &str) -> Option<(String, bool)>,
{
    let protected = protected_ranges(sql);
    let mut output = String::with_capacity(sql.len());
    let mut reached = HashSet::new();
    let mut cursor = 0;
    for captures in pattern.captures_iter(sql) {
        let full = captures
            .get(0)
            .expect("marker pattern has a complete match");
        if full.start() < cursor || in_protected_range(full.start(), &protected) {
            continue;
        }
        let suffix_start = skip_whitespace(sql, full.end());
        if !sql[suffix_start..].starts_with('(') {
            continue;
        }
        let suffix_end = matching_paren_end(sql, suffix_start)?;
        let name = captures
            .get(1)
            .expect("marker pattern captures a name")
            .as_str();
        let call_suffix = &sql[suffix_start..suffix_end];
        let Some((value, records_reach)) = replacement(name, call_suffix) else {
            continue;
        };
        output.push_str(&sql[cursor..full.start()]);
        output.push_str(&value);
        cursor = suffix_end;
        if records_reach {
            reached.insert(name.to_string());
        }
    }
    output.push_str(&sql[cursor..]);
    Ok((output, reached))
}

fn matching_paren_end(sql: &str, open: usize) -> Result<usize, String> {
    let bytes = sql.as_bytes();
    let mut depth = 0usize;
    let mut index = open;
    while index < bytes.len() {
        match bytes[index] {
            b'\'' | b'"' | b'`' => index = skip_quoted(sql, index)?,
            b'-' if bytes.get(index + 1) == Some(&b'-') => {
                index = sql[index..]
                    .find('\n')
                    .map_or(bytes.len(), |offset| index + offset + 1)
            }
            b'/' if bytes.get(index + 1) == Some(&b'*') => {
                let Some(offset) = sql[index + 2..].find("*/") else {
                    return Err(compile_error(
                        "SQL function call contains an unclosed block comment",
                    ));
                };
                index += offset + 4;
            }
            b'(' => {
                depth += 1;
                index += 1;
            }
            b')' => {
                depth -= 1;
                index += 1;
                if depth == 0 {
                    return Ok(index);
                }
            }
            _ => index += 1,
        }
    }
    Err(compile_error(
        "SQL function call contains an unclosed parenthesis",
    ))
}

fn skip_quoted(sql: &str, start: usize) -> Result<usize, String> {
    let quote = sql.as_bytes()[start];
    let bytes = sql.as_bytes();
    let mut index = start + 1;
    while index < bytes.len() {
        if bytes[index] != quote {
            index += 1;
            continue;
        }
        if bytes.get(index + 1) == Some(&quote) {
            index += 2;
            continue;
        }
        return Ok(index + 1);
    }
    Err(compile_error(
        "SQL function call contains an unclosed quoted string",
    ))
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

    let mut calls = Vec::new();
    walk(value, &mut calls);
    calls
}

fn top_level_cte_names(expression: &Expression) -> HashSet<String> {
    let Expression::Select(select) = expression else {
        return HashSet::new();
    };
    select
        .with
        .as_ref()
        .map(|with| with.ctes.iter().map(|cte| cte.alias.name.clone()).collect())
        .unwrap_or_default()
}

fn replace_relation_markers(sql: &str, replacements: &HashMap<(String, String), String>) -> String {
    let mut result = sql.to_string();
    for (function_name, pattern) in [
        (REF_FUNCTION, ref_pattern()),
        (SOURCE_FUNCTION, source_pattern()),
        (SEED_FUNCTION, seed_pattern()),
    ] {
        result = replace_named_markers(&result, pattern, |name| {
            replacements
                .get(&(function_name.to_string(), name.to_string()))
                .cloned()
        });
    }
    replace_dbt_ref_markers(&result, |name| {
        replacements
            .get(&(DBT_REF_FUNCTION.to_string(), name.to_string()))
            .cloned()
    })
}

fn replace_named_markers<F>(sql: &str, pattern: &Regex, mut replacement: F) -> String
where
    F: FnMut(&str) -> Option<String>,
{
    let protected = protected_ranges(sql);
    let mut output = String::with_capacity(sql.len());
    let mut cursor = 0;
    for captures in pattern.captures_iter(sql) {
        let full = captures
            .get(0)
            .expect("marker pattern has a complete match");
        if in_protected_range(full.start(), &protected) {
            continue;
        }
        let name = captures
            .get(1)
            .expect("marker pattern captures a name")
            .as_str();
        let Some(value) = replacement(name) else {
            continue;
        };
        output.push_str(&sql[cursor..full.start()]);
        output.push_str(&value);
        cursor = full.end();
    }
    output.push_str(&sql[cursor..]);
    output
}

fn replace_dbt_ref_markers<F>(sql: &str, mut replacement: F) -> String
where
    F: FnMut(&str) -> Option<String>,
{
    let protected = protected_ranges(sql);
    let mut output = String::with_capacity(sql.len());
    let mut cursor = 0;
    for captures in dbt_ref_pattern().captures_iter(sql) {
        let full = captures
            .get(0)
            .expect("marker pattern has a complete match");
        if in_protected_range(full.start(), &protected) {
            continue;
        }
        let first = captures.get(1).expect("dbt ref captures a name").as_str();
        let name = captures.get(2).map_or_else(
            || first.to_string(),
            |second| format!("{first}__{}", second.as_str()),
        );
        let Some(value) = replacement(&name) else {
            continue;
        };
        output.push_str(&sql[cursor..full.start()]);
        output.push_str(&value);
        cursor = full.end();
    }
    output.push_str(&sql[cursor..]);
    output
}

fn marker_names(pattern: &Regex, sql: &str) -> Vec<String> {
    let protected = protected_ranges(sql);
    pattern
        .captures_iter(sql)
        .filter(|captures| {
            !in_protected_range(
                captures
                    .get(0)
                    .expect("marker pattern has a complete match")
                    .start(),
                &protected,
            )
        })
        .filter_map(|captures| captures.get(1).map(|value| value.as_str().to_string()))
        .collect()
}

fn protected_ranges(sql: &str) -> Vec<(usize, usize)> {
    protected_pattern()
        .find_iter(sql)
        .map(|value| (value.start(), value.end()))
        .collect()
}

fn in_protected_range(index: usize, ranges: &[(usize, usize)]) -> bool {
    ranges
        .iter()
        .any(|(start, end)| index >= *start && index < *end)
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

fn leading_with_prefix_end(sql: &str) -> Option<usize> {
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

fn unresolved_reference_warnings(sql: &str, test_name: &str, model_name: &str) -> Vec<PlanWarning> {
    let mut warnings = Vec::new();
    for name in marker_names(ref_pattern(), sql) {
        warnings.push(PlanWarning {
            model_name: Some(model_name.to_string()),
            severity: "error",
            message: format!(
                "test '{test_name}': model '{model_name}' references __ref('{name}') which has no mock and is not in the expected chain"
            ),
        });
    }
    for (pattern, function_name, suffix) in [
        (source_pattern(), SOURCE_FUNCTION, " which has no mock"),
        (seed_pattern(), SEED_FUNCTION, " which has no mock"),
    ] {
        for name in marker_names(pattern, sql) {
            warnings.push(PlanWarning {
                model_name: Some(model_name.to_string()),
                severity: "error",
                message: format!(
                    "test '{test_name}': model '{model_name}' references {function_name}('{name}'){suffix}"
                ),
            });
        }
    }
    for captures in dbt_ref_pattern().captures_iter(sql) {
        let full = captures.get(0).expect("dbt ref has a complete match");
        if in_protected_range(full.start(), &protected_ranges(sql)) {
            continue;
        }
        let first = captures.get(1).expect("dbt ref captures a name").as_str();
        let name = captures.get(2).map_or_else(
            || first.to_string(),
            |second| format!("{first}__{}", second.as_str()),
        );
        warnings.push(PlanWarning {
            model_name: Some(model_name.to_string()),
            severity: "error",
            message: format!(
                "test '{test_name}': model '{model_name}' references __dbt_ref__{name} which has no mock"
            ),
        });
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
    let mut warnings = Vec::new();
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

fn assertion_ref_targets(assertions: &[(String, String)]) -> Vec<String> {
    let mut targets = Vec::new();
    for (_, sql) in assertions {
        targets.extend(marker_names(ref_pattern(), sql));
    }
    dedupe_in_place(&mut targets);
    targets
}

fn has_unresolved_test_reference(sql: &str) -> bool {
    !marker_names(ref_pattern(), sql).is_empty()
        || !marker_names(source_pattern(), sql).is_empty()
        || !marker_names(seed_pattern(), sql).is_empty()
        || dbt_ref_pattern().is_match(sql)
        || table_function_pattern().is_match(sql)
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

fn skip_whitespace(sql: &str, mut index: usize) -> usize {
    while sql
        .as_bytes()
        .get(index)
        .is_some_and(u8::is_ascii_whitespace)
    {
        index += 1;
    }
    index
}

fn dedupe_in_place(values: &mut Vec<String>) {
    let mut seen = HashSet::new();
    values.retain(|value| seen.insert(value.clone()));
}

fn ref_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r#"(?i)__ref\(\"([^\"]+)\"\)"#).expect("valid regex"))
}

fn source_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r#"(?i)__source\(\"([^\"]+)\"\)"#).expect("valid regex"))
}

fn seed_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r#"(?i)__seed\(\"([^\"]+)\"\)"#).expect("valid regex"))
}

fn udf_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r#"(?i)__udf\(\"([^\"]+)\"\)"#).expect("valid regex"))
}

fn table_function_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r#"(?i)__table_fn\(\"([^\"]+)\"\)"#).expect("valid regex"))
}

fn dbt_ref_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r#"(?i)__dbt_ref\(\s*\"([^\"]+)\"\s*(?:,\s*\"([^\"]+)\"\s*)?\)"#)
            .expect("valid regex")
    })
}

fn protected_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(
            r#"(?s)'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\$\$.*?\$\$|--[^\n]*|/\*.*?\*/"#,
        )
        .expect("valid regex")
    })
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

fn compile_error(message: &str) -> String {
    format!("compile_input:{message}")
}

fn planner_error(message: &str) -> String {
    format!("planner_input:{message}")
}
