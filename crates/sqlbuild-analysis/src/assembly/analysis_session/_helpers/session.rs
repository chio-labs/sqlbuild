//! The session's phases: Python's uncached model analysis, wave by wave.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use rayon::ThreadPool;
use rayon::iter::{IndexedParallelIterator, IntoParallelRefIterator, ParallelIterator};
use sqlbuild_cache::digest::types::ContentDigest;
use sqlbuild_cache::store::errors::StoreDecodeError;
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::assembly::analysis_session::_helpers::analysis_cache::{
    CachedOutcome, decode_outcome, encode_outcome,
};
use crate::assembly::analysis_session::_helpers::catalog_state::SessionCatalog;
use crate::assembly::analysis_session::_helpers::compact_batch::{
    Batch, BatchMember, MemberAnalysis, MemberResult,
};
use crate::assembly::analysis_session::_helpers::cte_facts::{
    LegacyAnalysis, LegacyInput, RecoveryProfile, legacy_analysis,
};
use crate::assembly::analysis_session::_helpers::dynamic_pivot::{PivotFacts, pivot_outcome};
use crate::assembly::analysis_session::_helpers::enrichment::{
    Enrichment, EnrichmentInput, enrichment,
};
use crate::assembly::analysis_session::_helpers::mappings::{
    ShapeTable, dict_from_pairs, same_keys, same_relations,
};
use crate::assembly::analysis_session::_helpers::mappings::{producers, waves};
use crate::assembly::analysis_session::_helpers::publication::{ShapeOptions, ShapeSource};
use crate::assembly::analysis_session::constants::{
    DEFERRAL_ANALYSIS, DEFERRAL_ENRICHMENT, UNKNOWN_NULLABILITY, UNKNOWN_TYPE,
};
use crate::assembly::analysis_session::models::{
    AnalysisSession, Awaiting, ColumnFact, Deferral, DeferredAnalysis, FinishedSession,
    LineageFacts, LineageRow, ModelAnalysis, ModelOutcome, ModelRequest, Phase, PivotOutcome,
    PivotTables, SessionModelFacts, SessionOutcome, SessionRequest, SessionStep,
};
use crate::assembly::analysis_session::types::{Pairs, Shapes};
use crate::semantic_validation::models::ProjectCatalog;
use crate::semantic_validation::types::DiagnosticRow;

/// The enrichment deferrals of one wave and whether each model's star was pending.
type Enrichments = (Vec<Deferral>, HashMap<usize, bool>);

impl AnalysisSession {
    /// A session over `request`, or None where Python's cycle handling must analyse.
    pub(crate) fn start(request: SessionRequest, catalog: &ProjectCatalog) -> Option<Self> {
        let waves: Vec<Vec<usize>> = waves(&producers(&request.models)?)?;
        let complete_shapes: ShapeTable = ShapeTable::from_shapes(&request.complete_schemas);
        let dependency_ordered: bool = request
            .models
            .iter()
            .flat_map(|model| model.required_names.iter())
            .any(|name| complete_shapes.get(name).is_none_or(Vec::is_empty));
        Some(Self {
            catalog: SessionCatalog::new(catalog, &request.catalog_schemas),
            available_types: ShapeTable::from_shapes(&request.column_types),
            available_nullability: ShapeTable::from_shapes(&request.column_nullability),
            complete_shapes,
            outcomes: vec![None; request.models.len()],
            waves: if dependency_ordered || waves.is_empty() {
                waves
            } else {
                vec![(0..request.models.len()).collect()]
            },
            dependency_ordered,
            next_wave: 0,
            phase: Phase::Analyze,
            publications: Vec::new(),
            failures: Vec::new(),
            cache: None,
            request,
        })
    }

    /// Advance until Python must answer deferrals; a step without deferrals means done.
    pub(crate) fn run(&mut self) -> Result<SessionStep, String> {
        loop {
            match std::mem::replace(&mut self.phase, Phase::Done) {
                Phase::Await(awaiting) => {
                    self.phase = Phase::Await(awaiting);
                    return Err("the session is waiting for deferred analyses".to_owned());
                }
                Phase::Done => return Ok(self.step(Vec::new())),
                Phase::Analyze => {
                    let Some(models) = self.waves.get(self.next_wave).cloned() else {
                        return Ok(self.step(Vec::new()));
                    };
                    let wave: usize = self.next_wave;
                    self.next_wave += 1;
                    let deferrals: Vec<Deferral> = self.analyze_wave(&models)?;
                    if deferrals.is_empty() {
                        self.phase = Phase::Complete(wave);
                        continue;
                    }
                    let deferred: Vec<usize> = deferrals.iter().map(Deferral::model).collect();
                    self.phase = Phase::Await(Awaiting::Analyses {
                        wave,
                        models: deferred,
                    });
                    return Ok(self.step(deferrals));
                }
                Phase::Complete(wave) => {
                    let (deferrals, star_pending) = self.complete_wave(wave)?;
                    if deferrals.is_empty() {
                        self.phase = Phase::Finish(wave);
                        continue;
                    }
                    self.phase = Phase::Await(Awaiting::Enrichments { wave, star_pending });
                    return Ok(self.step(deferrals));
                }
                Phase::Finish(wave) => {
                    self.finish_wave(wave)?;
                    self.phase = Phase::Analyze;
                }
            }
        }
    }

    /// Answer the deferrals of the last step.
    pub(crate) fn provide(&mut self, results: Vec<DeferredAnalysis>) -> Result<(), String> {
        let Phase::Await(awaiting) = std::mem::replace(&mut self.phase, Phase::Done) else {
            return Err("the session is not waiting for deferred analyses".to_owned());
        };
        match awaiting {
            Awaiting::Analyses { wave, models } => {
                let mut answered: Vec<usize> = results.iter().map(|result| result.model).collect();
                answered.sort_unstable();
                let mut expected: Vec<usize> = models;
                expected.sort_unstable();
                if answered != expected {
                    return Err("deferred analyses do not match the deferrals".to_owned());
                }
                for result in results {
                    let model: usize = result.model;
                    self.mark_uncacheable(model);
                    self.outcome_mut(model)?.analysis = python_analysis(result);
                }
                self.phase = Phase::Complete(wave);
            }
            Awaiting::Enrichments { wave, star_pending } => {
                if results.len() != star_pending.len() {
                    return Err("deferred enrichments do not match the deferrals".to_owned());
                }
                for result in results {
                    let pending: bool = *star_pending
                        .get(&result.model)
                        .ok_or("an enrichment answers no deferral")?;
                    self.mark_uncacheable(result.model);
                    let outcome: &mut ModelOutcome = self.outcome_mut(result.model)?;
                    outcome.analysis = enriched_analysis(
                        &outcome.analysis,
                        result,
                        pending,
                        LineageFacts::PythonEnrichment,
                    );
                }
                self.phase = Phase::Finish(wave);
            }
        }
        Ok(())
    }

    /// Every model's outcome and the binding catalog changes Python records.
    pub(crate) fn finish(self) -> Result<(SessionOutcome, FinishedSession), String> {
        if !matches!(self.phase, Phase::Done) {
            return Err("the session has not finished".to_owned());
        }
        let dynamic_contracts: Vec<PivotOutcome> = self.dynamic_contracts()?;
        let pool: Result<Arc<ThreadPool>, String> = self.catalog.native.analysis_pool();
        let models: Vec<ModelOutcome> = self
            .outcomes
            .into_iter()
            .collect::<Option<_>>()
            .ok_or("the session left a model unanalysed")?;
        let (schema_additions, analysis_names) = self.catalog.into_changes();
        let request: SessionRequest = self.request;
        let mut model_facts: HashMap<String, SessionModelFacts> = HashMap::new();
        for (model, outcome) in request.models.iter().zip(&models) {
            if let Some(facts) = session_model_facts(&outcome.analysis) {
                model_facts.insert(model.name.clone(), facts);
            }
        }
        let finished = FinishedSession {
            tables: PivotTables {
                dialect: request.dialect,
                column_types: request.column_types,
                authoritative_types: request.complete_schemas,
                column_nullability: request.column_nullability,
                families_by_table: request.dynamic_families_by_table,
            },
            pool,
            models: model_facts,
        };
        let outcome = SessionOutcome {
            models,
            schema_additions,
            analysis_names,
            dynamic_contracts,
        };
        Ok((outcome, finished))
    }

    /// Python's dynamic pivot proof of each model over the relation facts before analysis.
    fn dynamic_contracts(&self) -> Result<Vec<PivotOutcome>, String> {
        let models: &[ModelRequest] = &self.request.models;
        if models.iter().all(|model| model.dynamic_families.is_empty()) {
            return Ok(vec![PivotOutcome::Absent; models.len()]);
        }
        let facts = PivotFacts {
            dialect: &self.request.dialect,
            column_types: &self.request.column_types,
            authoritative_types: &self.request.complete_schemas,
            column_nullability: &self.request.column_nullability,
            families_by_table: &self.request.dynamic_families_by_table,
        };
        let pool = self.catalog.native.analysis_pool()?;
        Ok(pool.install(|| {
            models
                .par_iter()
                .map(|model| pivot_outcome(&model.pivot_sql, &model.dynamic_families, &facts))
                .collect()
        }))
    }

    fn step(&mut self, deferrals: Vec<Deferral>) -> SessionStep {
        SessionStep {
            publications: std::mem::take(&mut self.publications),
            deferrals,
            failures: std::mem::take(&mut self.failures),
        }
    }

    fn outcome_mut(&mut self, model: usize) -> Result<&mut ModelOutcome, String> {
        self.outcomes
            .get_mut(model)
            .and_then(Option::as_mut)
            .ok_or_else(|| "a deferral names an unanalysed model".to_owned())
    }

    /// Python's `_analyze_model_sql_requests` for one wave, less the models the cache answers.
    fn analyze_wave(&mut self, models: &[usize]) -> Result<Vec<Deferral>, String> {
        let schemas: Vec<Shapes> = models
            .iter()
            .map(|model| self.binding_schema(&self.request.models[*model]))
            .collect();
        let misses: Vec<usize> = self.read_cache(models, &schemas)?;
        let batch = Batch {
            dialect: &self.request.dialect,
            function_return_types: &self.request.function_return_types,
            rich_type_inference: self.request.rich_type_inference,
            members: misses
                .iter()
                .map(|position| {
                    batch_member(&self.request.models[models[*position]], &schemas[*position])
                })
                .collect(),
            types: &self.available_types,
            nullability: &self.available_nullability,
        };
        let results: Vec<MemberResult> = self.catalog.analyze_batch(&batch)?;
        let mut deferrals: Vec<Deferral> = Vec::new();
        let mut tables: Option<ContentDigest> = None;
        for (position, result) in misses.into_iter().zip(results) {
            let model: &usize = &models[position];
            let schema: Shapes = schemas[position].clone();
            if let Some(failure) = result.failure {
                self.failures.push(failure);
            }
            let diagnostics: Vec<DiagnosticRow> = result.binding_diagnostics.unwrap_or_default();
            let analysis: ModelAnalysis = match result.analysis {
                MemberAnalysis::Projected {
                    columns,
                    lineage,
                    has_star,
                    star_resolved,
                } => ModelAnalysis {
                    analysis_succeeded: true,
                    columns: Some(columns),
                    lineage: LineageFacts::Native(lineage),
                    has_star,
                    star_resolved,
                    binding_diagnostics: diagnostics,
                    binding_validated: true,
                },
                MemberAnalysis::Failed => {
                    failed_analysis(LineageFacts::Native(Vec::new()), diagnostics)
                }
                MemberAnalysis::Legacy { lineage } => {
                    match self.native_legacy(&self.request.models[*model], &result.cleaned_sql) {
                        Ok(legacy) => {
                            self.record_legacy_tables(*model, &mut tables);
                            legacy_outcome(legacy, lineage, diagnostics)
                        }
                        Err(_deferred) => {
                            deferrals.push(Deferral::Analysis {
                                model: *model,
                                cleaned_sql: result.cleaned_sql.clone(),
                                binding_schema: schema.clone(),
                                binding_diagnostics: diagnostics.clone(),
                                lineage,
                            });
                            failed_analysis(LineageFacts::PythonAnalysis, diagnostics)
                        }
                    }
                }
            };
            self.outcomes[*model] = Some(ModelOutcome {
                analysis,
                cleaned_sql: result.cleaned_sql,
                validated_schema: schema,
                fused_binding_validated: true,
            });
        }
        Ok(deferrals)
    }

    /// Python's legacy analysis of a model the engine handed back, or why Python must answer.
    fn native_legacy(
        &self,
        model: &ModelRequest,
        cleaned_sql: &str,
    ) -> Result<LegacyAnalysis, String> {
        catch_compiler_panic(|| {
            legacy_analysis(&LegacyInput {
                cleaned_sql,
                lineage_references: &model.lineage_references,
                recover: model.recover_cte_facts,
                types: &self.available_types,
                nullability: &self.available_nullability,
                profile: RecoveryProfile {
                    dialect: &self.request.dialect,
                    function_return_types: &self.request.function_return_types,
                    rules: self.request.nullability_rules.as_ref(),
                },
            })
        })
    }

    /// The closed shape of each relation the model binds, open relations empty.
    fn binding_schema(&self, model: &ModelRequest) -> Shapes {
        model
            .required_names
            .iter()
            .map(|name| {
                (
                    name.clone(),
                    self.complete_shapes.get(name).cloned().unwrap_or_default(),
                )
            })
            .collect()
    }

    /// Python's `_complete_inferred_bindings` star and type pass for one wave.
    fn complete_wave(&mut self, wave: usize) -> Result<Enrichments, String> {
        let mut deferrals: Vec<Deferral> = Vec::new();
        let mut star_pending_by_model: HashMap<usize, bool> = HashMap::new();
        let mut candidates: Vec<(usize, Shapes, bool)> = Vec::new();
        for model in self.waves[wave].clone() {
            if self.cached(model) {
                continue;
            }
            let request: &ModelRequest = &self.request.models[model];
            let required: Vec<String> = request.required_names.clone();
            let has_set_operation: bool = request.has_set_operation;
            let inputs_known: bool = !required.is_empty()
                && required
                    .iter()
                    .all(|name| self.complete_shapes.contains(name));
            let stars_expanded_natively: bool =
                required.iter().all(|name| self.supplied_relation(name));
            let input_schemas: Shapes = self.input_schemas(&required);
            let analysis: &mut ModelAnalysis = &mut self.outcome_mut(model)?.analysis;
            let mut star_pending: bool =
                analysis.has_star && !analysis.star_resolved && inputs_known;
            if star_pending && has_columns(analysis.columns.as_ref()) && stars_expanded_natively {
                analysis.star_resolved = true;
                star_pending = false;
            }
            let untyped: bool = analysis
                .columns
                .iter()
                .flatten()
                .any(|column| column.data_type.is_none());
            if !required.is_empty() && (untyped || star_pending) && !has_set_operation {
                candidates.push((model, input_schemas, star_pending));
            }
        }
        let enrichments: Vec<Option<Enrichment>> = self.native_enrichments(&candidates)?;
        for ((model, input_schemas, star_pending), native) in
            candidates.into_iter().zip(enrichments)
        {
            let Some(native) = native else {
                star_pending_by_model.insert(model, star_pending);
                deferrals.push(Deferral::Enrichment {
                    model,
                    input_schemas,
                });
                continue;
            };
            let outcome: &mut ModelOutcome = self.outcome_mut(model)?;
            outcome.analysis = enriched_analysis(
                &outcome.analysis,
                native_answer(
                    model,
                    native.analysis_succeeded,
                    native.columns,
                    native.has_star,
                ),
                star_pending,
                LineageFacts::NativeFacts(native.lineage),
            );
        }
        Ok((deferrals, star_pending_by_model))
    }

    /// Python's re-analysis of each candidate natively, None where Python must answer it.
    fn native_enrichments(
        &self,
        candidates: &[(usize, Shapes, bool)],
    ) -> Result<Vec<Option<Enrichment>>, String> {
        if candidates.is_empty() {
            return Ok(Vec::new());
        }
        let inputs: Vec<EnrichmentInput<'_>> = candidates
            .iter()
            .map(|(model, input_schemas, _)| EnrichmentInput {
                model: &self.request.models[*model],
                input_schemas,
                dialect: &self.request.dialect,
                function_return_types: &self.request.function_return_types,
                nullability_rules: self.request.nullability_rules.as_ref(),
            })
            .collect();
        let pool = self.catalog.native.analysis_pool()?;
        Ok(pool.install(|| inputs.par_iter().map(enrichment).collect()))
    }

    fn input_schemas(&self, required: &[String]) -> Shapes {
        let mut schemas: Shapes = Vec::with_capacity(required.len());
        for name in required {
            if let Some(shape) = self.complete_shapes.get(name) {
                schemas.push((name.clone(), shape.clone()));
            }
        }
        schemas
    }

    /// Whether the dataflow supplied `name`'s closed shape to the wave's analysis.
    fn supplied_relation(&self, name: &str) -> bool {
        let Some(shape) = self.complete_shapes.get(name) else {
            return false;
        };
        self.dependency_ordered
            && same_keys(self.available_types.get(name).unwrap_or(&Vec::new()), shape)
    }

    /// Python's deferred binding validation, then the dataflow's shape publication.
    fn finish_wave(&mut self, wave: usize) -> Result<(), String> {
        let models: Vec<usize> = self.waves[wave].clone();
        let mut validations: Vec<(usize, String, Shapes)> = Vec::new();
        for model in &models {
            let schema: Shapes = self.binding_schema(&self.request.models[*model]);
            let outcome: &ModelOutcome = self.outcomes[*model]
                .as_ref()
                .ok_or("a wave model was not analysed")?;
            if !outcome.fused_binding_validated
                || !same_relations(&outcome.validated_schema, &schema)
            {
                validations.push((*model, outcome.cleaned_sql.clone(), schema));
            }
        }
        if !validations.is_empty() {
            let requests: Vec<(&str, &Shapes)> = validations
                .iter()
                .map(|(_, sql, schema)| (sql.as_str(), schema))
                .collect();
            let prepared: Vec<_> = self.catalog.prepare(&requests);
            let rows: Vec<Vec<DiagnosticRow>> = self.catalog.native.binding_results(prepared)?;
            for ((model, _, _), diagnostics) in validations.iter().zip(rows) {
                let analysis: &mut ModelAnalysis = &mut self.outcome_mut(*model)?.analysis;
                analysis.binding_diagnostics = diagnostics;
                analysis.binding_validated = true;
            }
        }
        if self.dependency_ordered {
            for model in &models {
                self.publish(*model)?;
            }
        }
        self.store_cached(&models);
        Ok(())
    }

    /// Answer `models` from the cache where it can; returns the positions it cannot answer.
    fn read_cache(&mut self, models: &[usize], schemas: &[Shapes]) -> Result<Vec<usize>, String> {
        let Some(mut cache) = self.cache.take() else {
            return Ok((0..models.len()).collect());
        };
        let mut required: Vec<String> = Vec::new();
        let mut seen: HashSet<&str> = HashSet::new();
        for model in models {
            for reference in &self.request.models[*model].references {
                if seen.insert(reference.analysis_name.as_str()) {
                    required.push(reference.analysis_name.clone());
                }
            }
        }
        self.catalog.prepare_analysis(
            &required,
            &self.available_types,
            &self.available_nullability,
        );
        for schema in schemas {
            let _ = self.catalog.prepare(&[("", schema)]);
        }
        let pool: Arc<ThreadPool> = self.catalog.native.analysis_pool()?;
        let session_digest: ContentDigest = cache.session_digest;
        let names: Vec<&str> = models
            .iter()
            .flat_map(|model| self.model_relation_names(*model))
            .collect::<HashSet<&str>>()
            .into_iter()
            .collect();
        let keys: Vec<ContentDigest> = pool.install(|| {
            let relations: HashMap<&str, ContentDigest> = names
                .par_iter()
                .map(|name| (*name, self.relation_digest(name)))
                .collect();
            models
                .par_iter()
                .zip(schemas)
                .map(|(model, schema)| self.model_key(&session_digest, *model, schema, &relations))
                .collect()
        });
        let stored: Vec<Option<Vec<u8>>> = keys
            .iter()
            .map(|key| cache.store.get(key).map(<[u8]>::to_vec))
            .collect();
        let decoded: Vec<Option<Result<CachedOutcome, StoreDecodeError>>> = pool.install(|| {
            stored
                .par_iter()
                .zip(schemas)
                .map(|(bytes, schema)| Some(decode_outcome(bytes.as_ref()?, schema)))
                .collect()
        });
        let mut tables: Option<ContentDigest> = None;
        let mut hits: Vec<(usize, ModelOutcome)> = Vec::new();
        let mut misses: Vec<usize> = Vec::new();
        for (position, (model, found)) in models.iter().zip(decoded).enumerate() {
            cache.keys[*model] = Some(keys[position]);
            let hit: Option<ModelOutcome> = match found {
                Some(Ok((outcome, None))) => Some(outcome),
                Some(Ok((outcome, Some(required)))) => {
                    let current: ContentDigest =
                        *tables.get_or_insert_with(|| self.tables_digest());
                    (current == required).then_some(outcome)
                }
                Some(Err(StoreDecodeError)) | None => None,
            };
            match hit {
                Some(outcome) => hits.push((position, outcome)),
                None => misses.push(position),
            }
        }
        let members: Vec<BatchMember<'_>> = hits
            .iter()
            .map(|(position, _)| {
                batch_member(&self.request.models[models[*position]], &schemas[*position])
            })
            .collect();
        let cleaned: Vec<Result<String, String>> = self
            .catalog
            .normalize_each(&self.request.dialect, &members)
            .unwrap_or_else(|error| members.iter().map(|_| Err(error.clone())).collect());
        for ((position, mut outcome), sql) in hits.into_iter().zip(cleaned) {
            let model: usize = models[position];
            match sql {
                Ok(sql) => {
                    outcome.cleaned_sql = sql;
                    self.outcomes[model] = Some(outcome);
                    cache.hits[model] = true;
                }
                Err(_) => misses.push(position),
            }
        }
        misses.sort_unstable();
        cache.stats.hits += models.len() - misses.len();
        cache.stats.misses += misses.len();
        self.cache = Some(cache);
        Ok(misses)
    }

    /// Store each finished native outcome of `models` the cache did not answer.
    fn store_cached(&mut self, models: &[usize]) {
        let Some(cache) = self.cache.as_mut() else {
            return;
        };
        for model in models {
            if cache.hits[*model] || cache.uncacheable[*model] {
                continue;
            }
            let (Some(key), Some(outcome)) = (cache.keys[*model], self.outcomes[*model].as_ref())
            else {
                continue;
            };
            if let Some(bytes) = encode_outcome(outcome, cache.legacy_tables[*model].as_ref()) {
                cache.store.put(key, bytes);
                cache.stats.stored += 1;
            }
        }
    }

    fn mark_uncacheable(&mut self, model: usize) {
        if let Some(cache) = self.cache.as_mut() {
            cache.uncacheable[model] = true;
        }
    }

    /// Record the whole-table digest a legacy analysis of `model` read, computed once a wave.
    fn record_legacy_tables(&mut self, model: usize, tables: &mut Option<ContentDigest>) {
        if self.cache.is_none() {
            return;
        }
        let digest: ContentDigest = *tables.get_or_insert_with(|| self.tables_digest());
        if let Some(cache) = self.cache.as_mut() {
            cache.legacy_tables[model] = Some(digest);
        }
    }

    /// The dataflow's `_publish` for one analysed model.
    fn publish(&mut self, model: usize) -> Result<(), String> {
        let request: &ModelRequest = &self.request.models[model];
        let outcome: &ModelOutcome = self.outcomes[model]
            .as_ref()
            .ok_or("a published model was not analysed")?;
        let analysis: &ModelAnalysis = &outcome.analysis;
        let required_known: bool = request
            .required_names
            .iter()
            .all(|name| self.complete_shapes.contains(name));
        let star_known: bool = !analysis.has_star || (analysis.star_resolved && required_known);
        let Some(columns) = analysis
            .columns
            .as_ref()
            .filter(|columns| !columns.is_empty())
        else {
            return Ok(());
        };
        if !star_known {
            return Ok(());
        }
        let inputs: Shapes = self.binding_schema(request);
        let shape: Pairs = self.catalog.published_model_shape(
            &ShapeOptions {
                dialect: &self.request.dialect,
                case_sensitive: self.request.case_sensitive_shapes,
            },
            ShapeSource {
                sql: if outcome.cleaned_sql.is_empty() {
                    &request.query_sql
                } else {
                    &outcome.cleaned_sql
                },
                columns: shape_columns(columns),
                inputs: &inputs,
                snapshot_columns: request.snapshot_columns.as_ref(),
            },
        )?;
        let name: String = request.name.clone();
        let nullability: Pairs = shape
            .iter()
            .map(|(column, _)| (column.clone(), UNKNOWN_NULLABILITY.to_owned()))
            .collect();
        self.complete_shapes.set_default(&name, shape.clone());
        self.available_types.set_default(&name, shape.clone());
        self.available_nullability.set_default(&name, nullability);
        self.publications.push((name, shape));
        Ok(())
    }
}

fn batch_member<'a>(model: &'a ModelRequest, schema: &'a Shapes) -> BatchMember<'a> {
    BatchMember {
        query_sql: &model.query_sql,
        placeholders: &model.placeholders,
        analysis_names: model
            .references
            .iter()
            .map(|reference| reference.analysis_name.as_str())
            .collect(),
        lineage_references: &model.lineage_references,
        recover_cte_facts: model.recover_cte_facts,
        binding_schema: Some(schema),
    }
}

/// Python's `{column.name: column.type or "UNKNOWN"}`.
pub(crate) fn shape_columns(columns: &[ColumnFact]) -> Pairs {
    dict_from_pairs(columns.iter().map(shape_column))
}

fn shape_column(column: &ColumnFact) -> (String, String) {
    let data_type: &str = match column.data_type.as_deref() {
        Some(data_type) if !data_type.is_empty() => data_type,
        _ => UNKNOWN_TYPE,
    };
    (column.name.clone(), data_type.to_owned())
}

fn has_columns(columns: Option<&Vec<ColumnFact>>) -> bool {
    columns.is_some_and(|columns| !columns.is_empty())
}

fn failed_analysis(lineage: LineageFacts, diagnostics: Vec<DiagnosticRow>) -> ModelAnalysis {
    ModelAnalysis {
        analysis_succeeded: false,
        columns: None,
        lineage,
        has_star: false,
        star_resolved: false,
        binding_diagnostics: diagnostics,
        binding_validated: true,
    }
}

/// Python's `analyze_deferred` result, answered natively.
fn legacy_outcome(
    legacy: LegacyAnalysis,
    native_lineage: Option<Vec<LineageRow>>,
    diagnostics: Vec<DiagnosticRow>,
) -> ModelAnalysis {
    if !legacy.succeeded {
        return ModelAnalysis {
            analysis_succeeded: false,
            columns: None,
            lineage: LineageFacts::NativeFacts(Vec::new()),
            has_star: false,
            star_resolved: false,
            binding_diagnostics: Vec::new(),
            binding_validated: false,
        };
    }
    ModelAnalysis {
        analysis_succeeded: true,
        columns: legacy.columns,
        lineage: match native_lineage {
            Some(rows) => LineageFacts::Native(rows),
            None => LineageFacts::NativeFacts(legacy.lineage),
        },
        has_star: legacy.has_star,
        star_resolved: false,
        binding_diagnostics: diagnostics,
        binding_validated: true,
    }
}

fn python_analysis(result: DeferredAnalysis) -> ModelAnalysis {
    ModelAnalysis {
        analysis_succeeded: result.analysis_succeeded,
        columns: result.columns,
        lineage: LineageFacts::PythonAnalysis,
        has_star: result.has_star,
        star_resolved: result.star_resolved,
        binding_diagnostics: result.binding_diagnostics,
        binding_validated: result.binding_validated,
    }
}

impl Deferral {
    /// The deferred model's request index.
    pub fn model(&self) -> usize {
        match self {
            Self::Analysis { model, .. } | Self::Enrichment { model, .. } => *model,
        }
    }

    /// Python's name for the deferral's kind.
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Analysis { .. } => DEFERRAL_ANALYSIS,
            Self::Enrichment { .. } => DEFERRAL_ENRICHMENT,
        }
    }
}

/// Python's merge of a re-analysis with known inputs into the model's analysis.
fn enriched_analysis(
    analysis: &ModelAnalysis,
    enriched: DeferredAnalysis,
    star_pending: bool,
    lineage: LineageFacts,
) -> ModelAnalysis {
    let mut recovered: HashMap<String, String> = HashMap::new();
    for column in enriched
        .columns
        .iter()
        .flatten()
        .chain(analysis.columns.iter().flatten())
    {
        if let Some(data_type) = &column.data_type {
            recovered.insert(column.name.clone(), data_type.clone());
        }
    }
    let star_expanded: bool = star_pending && enriched.analysis_succeeded;
    let replaced: bool =
        (!has_columns(analysis.columns.as_ref()) || star_expanded) && enriched.analysis_succeeded;
    let mut merged: ModelAnalysis = if replaced {
        ModelAnalysis {
            analysis_succeeded: enriched.analysis_succeeded,
            columns: enriched.columns,
            lineage,
            has_star: enriched.has_star,
            star_resolved: enriched.star_resolved,
            binding_diagnostics: analysis.binding_diagnostics.clone(),
            binding_validated: analysis.binding_validated,
        }
    } else {
        analysis.clone()
    };
    let mut columns: Vec<ColumnFact> = merged.columns.take().unwrap_or_default();
    for column in &mut columns {
        if column.data_type.as_deref().is_none_or(str::is_empty) {
            column.data_type = recovered.get(&column.name).cloned();
        }
    }
    merged.columns = Some(columns);
    merged.star_resolved = merged.star_resolved || star_expanded;
    merged
}

/// A native re-analysis as Python's successful answer.
fn native_answer(
    model: usize,
    analysis_succeeded: bool,
    columns: Option<Vec<ColumnFact>>,
    has_star: bool,
) -> DeferredAnalysis {
    DeferredAnalysis {
        model,
        analysis_succeeded,
        columns,
        has_star,
        star_resolved: false,
        binding_diagnostics: Vec::new(),
        binding_validated: false,
    }
}

/// A compiled model's output names and lineage from a successful analysis with native lineage.
fn session_model_facts(analysis: &ModelAnalysis) -> Option<SessionModelFacts> {
    let rows: &Vec<LineageRow> = match &analysis.lineage {
        LineageFacts::Native(rows) | LineageFacts::NativeFacts(rows) => rows,
        LineageFacts::PythonAnalysis | LineageFacts::PythonEnrichment => return None,
    };
    analysis.analysis_succeeded.then(|| SessionModelFacts {
        columns: analysis.columns.as_deref().map(column_names),
        lineage: rows.iter().map(output_sources).collect(),
    })
}

fn column_names(columns: &[ColumnFact]) -> Vec<String> {
    columns.iter().map(|column| column.name.clone()).collect()
}

/// One lineage row as `(output column, [(resource name, column name)])`.
fn output_sources(row: &LineageRow) -> (String, Vec<(String, String)>) {
    let mut sources: Vec<(String, String)> = Vec::with_capacity(row.sources.len());
    for (_, name, column) in &row.sources {
        sources.push((name.clone(), column.clone()));
    }
    (row.output_column.clone(), sources)
}
