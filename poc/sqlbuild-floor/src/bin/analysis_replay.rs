//! Replay a captured compile's native analysis inputs in pure Rust (no Python), dataflow order.
//!
//! Usage: analysis_replay OPS_JSONL [--threads 1,2,4] [--runs 5] [--verify] [--parse]
//!
//! Units are single compact queries (with every template/projection that shares the query).
//! A unit starts once every model it depends on has been analysed; a finished unit publishes
//! the shapes the compile published for its models. Batches outside the model dataflow run as
//! barriers in recorded order, split into parallel per-query units.

#![allow(clippy::type_complexity)]

use _native::poc::{self, Catalog, Cols, Relations};
use rayon::prelude::*;
use serde_json::{Value, json};
use sqlbuild_floor::{load_average, measure, median, pool, process_cpu_seconds};
use std::collections::{BinaryHeap, HashMap, HashSet};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Condvar, Mutex, RwLock};
use std::time::Instant;

fn cols(value: &Value) -> Cols {
    value
        .as_array()
        .map(|pairs| {
            pairs
                .iter()
                .map(|pair| {
                    (
                        pair[0].as_str().unwrap_or_default().to_owned(),
                        pair[1].as_str().map(str::to_owned),
                    )
                })
                .collect()
        })
        .unwrap_or_default()
}

fn relations(value: &Value) -> Relations {
    value
        .as_array()
        .map(|pairs| {
            pairs
                .iter()
                .map(|pair| {
                    (
                        pair[0].as_str().unwrap_or_default().to_owned(),
                        cols(&pair[1]),
                    )
                })
                .collect()
        })
        .unwrap_or_default()
}

fn string_map(value: &Value) -> HashMap<String, String> {
    value
        .as_array()
        .map(|pairs| {
            pairs
                .iter()
                .map(|pair| {
                    (
                        pair[0].as_str().unwrap_or_default().to_owned(),
                        pair[1].as_str().unwrap_or_default().to_owned(),
                    )
                })
                .collect()
        })
        .unwrap_or_default()
}

#[derive(Clone)]
enum Mutation {
    Relations(Relations),
    Analysis(Vec<(String, (Cols, Cols))>),
    Override(Relations),
}

struct Unit {
    payload: String,
    sql: String,
    dialect: String,
    produces: Vec<String>,
    deps: Vec<usize>,
    dependents: Vec<usize>,

    priority: usize,
    /// (batch job id, original projection index) for every projection in the unit.
    projections: Vec<(u64, usize)>,
}

struct Phase {
    /// Mutations to apply (in order) before the phase starts.
    mutations: Vec<Mutation>,
    units: Vec<usize>,
}

struct Replay {
    catalog_request: Value,
    phases: Vec<Phase>,
    units: Vec<Unit>,
    /// Shapes published when a model's unit finishes.
    published: HashMap<String, Vec<(String, (Cols, Cols))>>,
    normalize: Vec<(String, poc::NormalizationRequest, Value)>,
    bindings: Vec<(Vec<poc::BindingRequest>, Value)>,
    module_compact: Vec<(String, String)>,
    /// Recorded canonical result per (job, projection).
    expected: HashMap<(u64, usize), Value>,
    recorded_run_seconds: f64,
    stats: Vec<String>,
}

fn expand_projection(response: &Value, payload: &Value, index: usize) -> Value {
    let strings = response["strings"].as_array().cloned().unwrap_or_default();
    let s = |v: &Value| {
        v.as_u64()
            .map_or(Value::Null, |i| strings[i as usize].clone())
    };
    let facts = response["facts"].as_array().cloned().unwrap_or_default();
    let analysis = &response["analyses"][index];
    let template_index = analysis[0].as_u64().unwrap_or(0) as usize;
    let template = &response["templates"][template_index];
    let expanded_template = match template.as_array() {
        Some(parts) => {
            let columns: Vec<Value> = parts[0]
                .as_array()
                .map(|columns| {
                    columns
                        .iter()
                        .map(|fact_index| {
                            let fact = &facts[fact_index.as_u64().unwrap_or(0) as usize];
                            let upstream: Vec<Value> = fact[5]
                                .as_array()
                                .map(|sources| {
                                    sources
                                        .iter()
                                        .map(|src| json!([s(&src[0]), s(&src[1]), s(&src[2])]))
                                        .collect()
                                })
                                .unwrap_or_default();
                            json!([
                                s(&fact[0]),
                                s(&fact[1]),
                                fact[2],
                                fact[3],
                                fact[4],
                                upstream
                            ])
                        })
                        .collect()
                })
                .unwrap_or_default();
            json!([columns, parts[1], parts[2]])
        }
        None => template.clone(),
    };
    let names: Vec<Value> = analysis[1]
        .as_array()
        .map(|pairs| pairs.iter().map(|p| json!([s(&p[0]), s(&p[1])])).collect())
        .unwrap_or_default();
    let query_index = payload["templates"][template_index]["queryIndex"]
        .as_u64()
        .unwrap_or(0) as usize;
    let validation = response
        .get("validations")
        .map_or(Value::Null, |v| v[query_index].clone());
    json!({"template": expanded_template, "names": names, "validation": validation})
}

fn load(path: &str) -> Replay {
    let text = std::fs::read_to_string(path).expect("read ops");
    let ops: Vec<Value> = text
        .lines()
        .map(|line| serde_json::from_str(line).expect("json line"))
        .collect();
    let mut stats = Vec::new();
    let analysis_catalog = ops
        .iter()
        .find(|op| op["op"] == "prepare_compact")
        .and_then(|op| op["id"].as_u64());
    let catalog_request = ops
        .iter()
        .find(|op| op["op"] == "new" && op["id"].as_u64() == analysis_catalog)
        .map(|op| op["request"].clone())
        .expect("analysis catalog");
    let mut dependencies: HashMap<String, Vec<String>> = HashMap::new();
    let mut hash_names: HashMap<String, Vec<String>> = HashMap::new();
    let mut runs: HashMap<u64, (String, f64)> = HashMap::new();
    for op in &ops {
        match op["op"].as_str() {
            Some("dataflow") => {
                for pair in op["dependencies"].as_array().into_iter().flatten() {
                    dependencies.insert(
                        pair[0].as_str().unwrap_or_default().to_owned(),
                        pair[1]
                            .as_array()
                            .into_iter()
                            .flatten()
                            .filter_map(|v| v.as_str().map(str::to_owned))
                            .collect(),
                    );
                }
            }
            Some("ready") => {
                for pair in op["query_sqls"].as_array().into_iter().flatten() {
                    hash_names
                        .entry(pair[1].as_str().unwrap_or_default().to_owned())
                        .or_default()
                        .push(pair[0].as_str().unwrap_or_default().to_owned());
                }
            }
            Some("run") => {
                runs.insert(
                    op["job"].as_u64().unwrap_or(0),
                    (
                        op["result"].as_str().unwrap_or_default().to_owned(),
                        op["seconds"].as_f64().unwrap_or(0.0),
                    ),
                );
            }
            _ => {}
        }
    }
    let recorded_run_seconds = runs.values().map(|(_, s)| s).sum();

    // Pass 1: units, model producers, phases.
    let mut units: Vec<Unit> = Vec::new();
    let mut producer: HashMap<String, usize> = HashMap::new();
    let mut expected: HashMap<(u64, usize), Value> = HashMap::new();
    let mut phases: Vec<Phase> = Vec::new();
    let mut pending_mutations: Vec<(u64, Mutation)> = Vec::new();
    let mut phase_of_prepare: Vec<(u64, usize)> = Vec::new();
    let mut in_dataflow_phase = false;
    let mut unresolved_models = HashSet::new();
    for op in &ops {
        let seq = op["seq"].as_u64().unwrap_or(0);
        let on_catalog = op["id"].as_u64() == analysis_catalog;
        match op["op"].as_str() {
            Some("update_relations") if on_catalog => {
                pending_mutations.push((seq, Mutation::Relations(relations(&op["relations"]))));
            }
            Some("register_override") if on_catalog => {
                pending_mutations.push((seq, Mutation::Override(relations(&op["relations"]))));
            }
            Some("update_analysis") if on_catalog => {
                let entries = op["relations"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .map(|pair| {
                        (
                            pair[0].as_str().unwrap_or_default().to_owned(),
                            (cols(&pair[1][0]), cols(&pair[1][1])),
                        )
                    })
                    .collect();
                pending_mutations.push((seq, Mutation::Analysis(entries)));
            }
            Some("prepare_compact") if on_catalog => {
                let payload: Value =
                    serde_json::from_str(op["payload"].as_str().unwrap_or("{}")).expect("payload");
                let job = op["job"].as_u64().unwrap_or(0);
                let dataflow = !op["context"].is_null();
                if !dataflow || !in_dataflow_phase {
                    phases.push(Phase {
                        mutations: Vec::new(),
                        units: Vec::new(),
                    });
                }
                in_dataflow_phase = dataflow;
                let phase = phases.len() - 1;
                phase_of_prepare.push((seq, phase));
                let context: HashSet<String> = op["context"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|v| v.as_str().map(str::to_owned))
                    .collect();
                let hashes: Vec<String> = op["query_sqls"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|v| v.as_str().map(str::to_owned))
                    .collect();
                let response: Value = serde_json::from_str(&runs[&job].0).expect("run result");
                let queries = payload["queries"].as_array().cloned().unwrap_or_default();
                let templates = payload["templates"].as_array().cloned().unwrap_or_default();
                let projections = payload["projections"]
                    .as_array()
                    .cloned()
                    .unwrap_or_default();
                for (index, _) in projections.iter().enumerate() {
                    expected.insert((job, index), expand_projection(&response, &payload, index));
                }
                for (query_index, query) in queries.iter().enumerate() {
                    let template_ids: Vec<usize> = templates
                        .iter()
                        .enumerate()
                        .filter(|(_, t)| t["queryIndex"].as_u64() == Some(query_index as u64))
                        .map(|(i, _)| i)
                        .collect();
                    let mut unit_templates = Vec::new();
                    let mut remap = HashMap::new();
                    for (new_index, old_index) in template_ids.iter().enumerate() {
                        let mut template = templates[*old_index].clone();
                        template["queryIndex"] = json!(0);
                        unit_templates.push(template);
                        remap.insert(*old_index, new_index);
                    }
                    let mut unit_projections = Vec::new();
                    let mut unit_projection_ids = Vec::new();
                    let mut produces = Vec::new();
                    for (projection_index, projection) in projections.iter().enumerate() {
                        let old = projection["templateIndex"].as_u64().unwrap_or(0) as usize;
                        if let Some(new_index) = remap.get(&old) {
                            let mut projection = projection.clone();
                            projection["templateIndex"] = json!(new_index);
                            unit_projections.push(projection);
                            unit_projection_ids.push((job, projection_index));
                            if dataflow && let Some(hash) = hashes.get(projection_index) {
                                for name in hash_names.get(hash).into_iter().flatten() {
                                    if context.contains(name) {
                                        produces.push(name.clone());
                                    }
                                }
                            }
                        }
                    }
                    let unit_index = units.len();
                    for name in &produces {
                        producer.insert(name.clone(), unit_index);
                    }
                    let unit_payload = json!({
                        "queries": [query],
                        "templates": unit_templates,
                        "projections": unit_projections,
                        "workers": 1,
                    });
                    units.push(Unit {
                        payload: unit_payload.to_string(),
                        sql: query["sql"].as_str().unwrap_or_default().to_owned(),
                        dialect: query["dialect"].as_str().unwrap_or("generic").to_owned(),
                        produces,
                        deps: Vec::new(),
                        dependents: Vec::new(),

                        priority: 0,
                        projections: unit_projection_ids,
                    });
                    phases[phase].units.push(unit_index);
                }
                for name in context {
                    if !producer.contains_key(&name) {
                        unresolved_models.insert(name);
                    }
                }
            }
            _ => {}
        }
    }
    unresolved_models.retain(|name| !producer.contains_key(name));
    stats.push(format!(
        "units {} phases {} produced models {} models without own unit (memo-reused, available at start) {}",
        units.len(),
        phases.len(),
        producer.len(),
        unresolved_models.len()
    ));

    // Mutations: shapes of produced models publish on completion; the rest join the phase
    // following their record.
    let mut published: HashMap<String, Vec<(String, (Cols, Cols))>> = HashMap::new();
    let mut deferred_entries = 0usize;
    for (seq, mutation) in pending_mutations {
        let phase = phase_of_prepare
            .iter()
            .find(|(prepare_seq, _)| *prepare_seq > seq)
            .map_or(phases.len().saturating_sub(1), |(_, phase)| *phase);
        match mutation {
            Mutation::Analysis(entries) => {
                let mut immediate = Vec::new();
                for (name, shape) in entries {
                    if producer.contains_key(&name) {
                        deferred_entries += 1;
                        published
                            .entry(name.clone())
                            .or_default()
                            .push((name, shape));
                    } else {
                        immediate.push((name, shape));
                    }
                }
                if !immediate.is_empty() {
                    phases[phase].mutations.push(Mutation::Analysis(immediate));
                }
            }
            other => phases[phase].mutations.push(other),
        }
    }
    stats.push(format!(
        "shape entries published at producer completion {deferred_entries}"
    ));

    // Dependencies: dataflow model dependencies mapped to producing units.
    let mut edge_count = 0usize;
    for index in 0..units.len() {
        let mut deps: HashSet<usize> = HashSet::new();
        for name in &units[index].produces {
            for parent in dependencies.get(name).into_iter().flatten() {
                if let Some(parent_unit) = producer.get(parent)
                    && *parent_unit != index
                {
                    deps.insert(*parent_unit);
                }
            }
        }
        let mut deps: Vec<usize> = deps.into_iter().collect();
        deps.sort_unstable();
        edge_count += deps.len();
        for parent in &deps {
            units[*parent].dependents.push(index);
        }
        units[index].deps = deps;
    }
    // Priority: longest remaining chain, weighted by SQL size as a cost proxy.
    for index in (0..units.len()).rev() {
        let own = units[index].sql.len();
        let best = units[index]
            .dependents
            .iter()
            .map(|child| units[*child].priority)
            .max()
            .unwrap_or(0);
        units[index].priority = own + best;
    }
    stats.push(format!("dependency edges between units {edge_count}"));

    let mut normalize = Vec::new();
    let mut bindings = Vec::new();
    let mut module_compact = Vec::new();
    for op in &ops {
        match op["op"].as_str() {
            Some("normalize") => {
                let dialect = op["dialect"].as_str().unwrap_or("generic").to_owned();
                let results = op["result"].as_array().cloned().unwrap_or_default();
                for (request, result) in
                    op["requests"].as_array().into_iter().flatten().zip(results)
                {
                    normalize.push((
                        dialect.clone(),
                        (
                            request[0].as_str().unwrap_or_default().to_owned(),
                            string_map(&request[1]),
                            string_map(&request[2]),
                        ),
                        result,
                    ));
                }
            }
            Some("binding_results") if op["id"].as_u64() == analysis_catalog => {
                let requests = op["requests"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .map(|request| {
                        (
                            request[0].as_str().unwrap_or_default().to_owned(),
                            request[1]
                                .as_array()
                                .into_iter()
                                .flatten()
                                .map(|pair| {
                                    (
                                        pair[0].as_str().unwrap_or_default().to_owned(),
                                        pair[1].as_bool().unwrap_or(false),
                                    )
                                })
                                .collect(),
                            relations(&request[2]),
                        )
                    })
                    .collect();
                bindings.push((requests, op["result"].clone()));
            }
            Some("binding_results") => {
                stats.push("binding_results on another catalog skipped".into())
            }
            Some("compact_json") => module_compact.push((
                op["payload"].as_str().unwrap_or_default().to_owned(),
                op["result"].as_str().unwrap_or_default().to_owned(),
            )),
            _ => {}
        }
    }
    Replay {
        catalog_request,
        phases,
        units,
        published,
        normalize,
        bindings,
        module_compact,
        expected,
        recorded_run_seconds,
        stats,
    }
}

fn new_catalog(request: &Value) -> Catalog {
    let get = |key: &str| {
        request
            .as_array()
            .and_then(|pairs| pairs.iter().find(|pair| pair[0] == key))
            .map(|pair| pair[1].clone())
            .unwrap_or(Value::Null)
    };
    let strings = |value: Value| -> Vec<String> {
        value
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|v| v.as_str().map(str::to_owned))
            .collect()
    };
    Catalog::new(
        get("dialect").as_str().unwrap_or("generic").to_owned(),
        get("quoted_ignore_case").as_bool().unwrap_or(false),
        strings(get("known_functions")),
        strings(get("known_types")),
        relations(&get("relations")),
    )
    .expect("catalog")
}

fn apply(catalog: &mut Catalog, mutation: &Mutation) {
    match mutation {
        Mutation::Relations(value) => catalog.update_relations(value.clone()),
        Mutation::Analysis(value) => catalog.update_analysis(value.clone()),
        Mutation::Override(value) => {
            let _ = catalog.register_override(value.clone());
        }
    }
}

struct Ready(usize, usize);
impl PartialEq for Ready {
    fn eq(&self, other: &Self) -> bool {
        self.0 == other.0 && self.1 == other.1
    }
}
impl Eq for Ready {}
impl PartialOrd for Ready {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for Ready {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.0.cmp(&other.0).then(other.1.cmp(&self.1))
    }
}

struct RunResult {
    wall: f64,
    cpu: f64,
    phase_walls: Vec<f64>,
    outputs: Vec<Option<String>>,
    unit_seconds: Vec<f64>,
    errors: usize,
}

/// Run every phase with dataflow scheduling on a pool of `threads`.
fn run_analysis(replay: &Replay, threads: usize, keep_outputs: bool) -> RunResult {
    let thread_pool = Arc::new(pool(threads));
    let cpu0 = process_cpu_seconds();
    let start = Instant::now();
    let catalog = RwLock::new(new_catalog(&replay.catalog_request));
    catalog
        .read()
        .expect("lock")
        .set_pool(Arc::clone(&thread_pool));
    let outputs: Vec<Mutex<Option<String>>> =
        replay.units.iter().map(|_| Mutex::new(None)).collect();
    let unit_seconds: Vec<Mutex<f64>> = replay.units.iter().map(|_| Mutex::new(0.0)).collect();
    let errors = AtomicUsize::new(0);
    let mut phase_walls = Vec::new();
    for phase in &replay.phases {
        let phase_start = Instant::now();
        {
            let mut guard = catalog.write().expect("lock");
            for mutation in &phase.mutations {
                apply(&mut guard, mutation);
            }
        }
        let in_phase: HashSet<usize> = phase.units.iter().copied().collect();
        let pending: Vec<AtomicUsize> = replay
            .units
            .iter()
            .map(|unit| AtomicUsize::new(unit.deps.iter().filter(|d| in_phase.contains(d)).count()))
            .collect();
        let ready = Mutex::new(BinaryHeap::new());
        for index in &phase.units {
            if pending[*index].load(Ordering::Relaxed) == 0 {
                ready
                    .lock()
                    .expect("lock")
                    .push(Ready(replay.units[*index].priority, *index));
            }
        }
        let remaining = AtomicUsize::new(phase.units.len());
        let signal = Condvar::new();
        thread_pool.scope(|scope| {
            for _ in 0..threads {
                scope.spawn(|_| {
                    loop {
                        let next = {
                            let mut heap = ready.lock().expect("lock");
                            loop {
                                if let Some(Ready(_, index)) = heap.pop() {
                                    break Some(index);
                                }
                                if remaining.load(Ordering::Acquire) == 0 {
                                    break None;
                                }
                                heap = signal.wait(heap).expect("lock");
                            }
                        };
                        let Some(index) = next else {
                            signal.notify_all();
                            return;
                        };
                        let unit = &replay.units[index];
                        let unit_start = Instant::now();
                        let prepared = catalog.read().expect("lock").prepare_compact(&unit.payload);
                        let view = catalog.read().expect("lock").view();
                        let result = prepared.and_then(|job| job.run(&view));
                        *unit_seconds[index].lock().expect("lock") =
                            unit_start.elapsed().as_secs_f64();
                        match result {
                            Ok(text) => {
                                if keep_outputs {
                                    *outputs[index].lock().expect("lock") = Some(text);
                                }
                            }
                            Err(_) => {
                                errors.fetch_add(1, Ordering::Relaxed);
                            }
                        }
                        let shapes: Vec<(String, (Cols, Cols))> = unit
                            .produces
                            .iter()
                            .flat_map(|name| replay.published.get(name).into_iter().flatten())
                            .cloned()
                            .collect();
                        if !shapes.is_empty() {
                            catalog.write().expect("lock").update_analysis(shapes);
                        }
                        let mut heap = ready.lock().expect("lock");
                        for child in &unit.dependents {
                            if in_phase.contains(child)
                                && pending[*child].fetch_sub(1, Ordering::AcqRel) == 1
                            {
                                heap.push(Ready(replay.units[*child].priority, *child));
                            }
                        }
                        remaining.fetch_sub(1, Ordering::AcqRel);
                        drop(heap);
                        signal.notify_all();
                    }
                });
            }
        });
        phase_walls.push(phase_start.elapsed().as_secs_f64());
    }
    RunResult {
        wall: start.elapsed().as_secs_f64(),
        cpu: process_cpu_seconds() - cpu0,
        phase_walls,
        outputs: outputs
            .into_iter()
            .map(|m| m.into_inner().expect("lock"))
            .collect(),
        unit_seconds: unit_seconds
            .into_iter()
            .map(|m| m.into_inner().expect("lock"))
            .collect(),
        errors: errors.load(Ordering::Relaxed),
    }
}

fn verify(replay: &Replay, run: &RunResult) -> (usize, usize, Vec<String>) {
    let mut equal = 0;
    let mut different = 0;
    let mut examples = Vec::new();
    for (index, unit) in replay.units.iter().enumerate() {
        let Some(text) = &run.outputs[index] else {
            different += unit.projections.len();
            continue;
        };
        let response: Value = serde_json::from_str(text).expect("unit output");
        let payload: Value = serde_json::from_str(&unit.payload).expect("unit payload");
        for (position, key) in unit.projections.iter().enumerate() {
            let actual = expand_projection(&response, &payload, position);
            if replay.expected.get(key) == Some(&actual) {
                equal += 1;
            } else {
                different += 1;
                if examples.len() < 3 {
                    examples.push(format!("unit {index} projection {key:?}"));
                }
            }
        }
    }
    (equal, different, examples)
}

/// Critical path through the unit DAG using measured single-thread unit times.
fn critical_path(replay: &Replay, seconds: &[f64]) -> f64 {
    let mut finish = vec![0.0f64; replay.units.len()];
    let mut total = 0.0f64;
    for phase in &replay.phases {
        let mut phase_end: f64 = 0.0;
        for index in &phase.units {
            let start = replay.units[*index]
                .deps
                .iter()
                .map(|d| finish[*d])
                .fold(total, f64::max);
            finish[*index] = start + seconds[*index];
            phase_end = phase_end.max(finish[*index]);
        }
        total = total.max(phase_end);
    }
    total
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let path = args.get(1).expect("ops path").clone();
    let flag = |name: &str| args.iter().position(|a| a == name);
    let threads: Vec<usize> = flag("--threads")
        .and_then(|i| args.get(i + 1))
        .map_or(vec![1, 2, 4], |v| {
            v.split(',').filter_map(|t| t.parse().ok()).collect()
        });
    let runs: usize = flag("--runs")
        .and_then(|i| args.get(i + 1))
        .and_then(|v| v.parse().ok())
        .unwrap_or(5);
    let (replay, load_wall, _) = measure(|| load(&path));
    println!(
        "loaded {path} in {load_wall:.2}s (load avg {:.2})",
        load_average()
    );
    for line in &replay.stats {
        println!("  {line}");
    }
    println!(
        "  recorded compile: native job run seconds (sum over jobs) {:.3}",
        replay.recorded_run_seconds
    );

    if flag("--verify").is_some() {
        let run = run_analysis(&replay, 4, true);
        let (equal, different, examples) = verify(&replay, &run);
        println!(
            "verify analysis: projections equal {equal} different {different} errors {} {examples:?}",
            run.errors
        );
        let normalize_ok = replay
            .normalize
            .par_iter()
            .filter(|(dialect, request, expected)| {
                let actual = poc::normalize_analysis_sql(dialect, request.clone());
                match (actual, expected) {
                    (Ok(sql), Value::String(text)) => sql == *text,
                    (Err(_), Value::Object(_)) => true,
                    _ => false,
                }
            })
            .count();
        println!(
            "verify normalize: equal {normalize_ok} of {}",
            replay.normalize.len()
        );
        let catalog = final_catalog(&replay);
        for (requests, expected) in &replay.bindings {
            let rows = catalog.binding_results(requests.clone()).expect("bindings");
            let actual = serde_json::to_value(&rows).expect("rows");
            let same = actual
                .as_array()
                .zip(expected.as_array())
                .map(|(a, e)| a.iter().zip(e).filter(|(x, y)| x == y).count());
            println!(
                "verify binding_results: equal {:?} of {}",
                same,
                requests.len()
            );
        }
        for (payload, expected) in &replay.module_compact {
            let actual = poc::analyze_project_compact_json(payload);
            println!(
                "verify module compact_json: equal {}",
                actual.as_deref() == Ok(expected.as_str())
            );
        }
    }

    if flag("--parse").is_some() {
        // Single-thread split: parse only vs the full unit (parse + resolution + binding/shape
        // inference + projection), over the same units.
        let mut parse_seconds = Vec::new();
        let mut full = Vec::new();
        for _ in 0..3 {
            let (_, wall, _) = measure(|| {
                for unit in &replay.units {
                    let dialect = unit
                        .dialect
                        .parse::<polyglot_sql::DialectType>()
                        .unwrap_or(polyglot_sql::DialectType::Generic);
                    let _ = std::hint::black_box(polyglot_sql::parse(&unit.sql, dialect));
                }
            });
            parse_seconds.push(wall);
            let run = run_analysis(&replay, 1, false);
            full.push(run.unit_seconds.iter().sum::<f64>());
        }
        let parse = median(&mut parse_seconds);
        let full = median(&mut full);
        println!(
            "parse-only (1 thread) {parse:.3}s; full unit analysis (1 thread) {full:.3}s; parse share {:.0}%",
            100.0 * parse / full
        );
        let normalize_seconds = {
            let mut samples = Vec::new();
            for _ in 0..3 {
                let (_, wall, _) = measure(|| {
                    for (dialect, request, _) in &replay.normalize {
                        let _ = std::hint::black_box(poc::normalize_analysis_sql(
                            dialect,
                            request.clone(),
                        ));
                    }
                });
                samples.push(wall);
            }
            median(&mut samples)
        };
        println!(
            "normalize (1 thread) {normalize_seconds:.3}s for {} SQLs",
            replay.normalize.len()
        );
    }

    for thread_count in threads {
        let mut walls = Vec::new();
        let mut cpus = Vec::new();
        let mut loads = Vec::new();
        let mut phase_walls: Vec<Vec<f64>> = Vec::new();
        let mut critical = Vec::new();
        let mut unit_sum = Vec::new();
        for _ in 0..runs {
            loads.push(load_average());
            let run = run_analysis(&replay, thread_count, false);
            walls.push(run.wall);
            cpus.push(run.cpu);
            phase_walls.push(run.phase_walls.clone());
            unit_sum.push(run.unit_seconds.iter().sum::<f64>());
            if thread_count == 1 {
                critical.push(critical_path(&replay, &run.unit_seconds));
            }
        }
        let (n_wall, n_cpu) = side_phase(&replay, thread_count, runs, true);
        let (b_wall, b_cpu) = side_phase(&replay, thread_count, runs, false);
        let phases: Vec<String> = (0..replay.phases.len())
            .map(|p| {
                let mut values: Vec<f64> = phase_walls.iter().map(|w| w[p]).collect();
                format!("{:.3}", median(&mut values))
            })
            .collect();
        println!(
            "threads {thread_count}: analysis wall {:.3}s cpu {:.3}s (phases {}) unit-time sum {:.3}s{} | normalize wall {n_wall:.3} cpu {n_cpu:.3} | binding_results wall {b_wall:.3} cpu {b_cpu:.3} | load {:.2}-{:.2}",
            median(&mut walls),
            median(&mut cpus),
            phases.join("+"),
            median(&mut unit_sum),
            if critical.is_empty() {
                String::new()
            } else {
                format!(" critical path {:.3}s", median(&mut critical))
            },
            loads.iter().copied().fold(f64::INFINITY, f64::min),
            loads.iter().copied().fold(0.0, f64::max),
        );
    }
}

fn final_catalog(replay: &Replay) -> Catalog {
    let mut catalog = new_catalog(&replay.catalog_request);
    for phase in &replay.phases {
        for mutation in &phase.mutations {
            apply(&mut catalog, mutation);
        }
    }
    let shapes: Vec<(String, (Cols, Cols))> =
        replay.published.values().flatten().cloned().collect();
    catalog.update_analysis(shapes);
    catalog
}

/// Median wall/CPU of the normalization (or binding validation) phase on `threads`.
fn side_phase(replay: &Replay, threads: usize, runs: usize, normalize: bool) -> (f64, f64) {
    let thread_pool = pool(threads);
    let catalog = final_catalog(replay);
    let mut walls = Vec::new();
    let mut cpus = Vec::new();
    for _ in 0..runs {
        let (_, wall, cpu) = measure(|| {
            thread_pool.install(|| {
                if normalize {
                    replay
                        .normalize
                        .par_iter()
                        .for_each(|(dialect, request, _)| {
                            let _ = std::hint::black_box(poc::normalize_analysis_sql(
                                dialect,
                                request.clone(),
                            ));
                        });
                } else {
                    for (requests, _) in &replay.bindings {
                        let _ = std::hint::black_box(catalog.binding_results(requests.clone()));
                    }
                }
            });
        });
        walls.push(wall);
        cpus.push(cpu);
    }
    (median(&mut walls), median(&mut cpus))
}
