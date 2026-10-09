//! Python's topological analysis waves over the models a compile analyses.

use std::collections::{BTreeSet, HashMap};

use crate::assembly::analysis_session::models::ModelRequest;

/// Each model's analysed `ref` producers, or None when two models share a name.
pub(crate) fn producers(models: &[ModelRequest]) -> Option<Vec<Vec<usize>>> {
    let mut indexes: HashMap<&str, usize> = HashMap::with_capacity(models.len());
    for (index, model) in models.iter().enumerate() {
        if indexes.insert(model.name.as_str(), index).is_some() {
            return None;
        }
    }
    let mut producers: Vec<Vec<usize>> = Vec::with_capacity(models.len());
    for model in models {
        let mut model_producers: BTreeSet<usize> = BTreeSet::new();
        for reference in model
            .references
            .iter()
            .filter(|reference| reference.model_ref)
        {
            if let Some(index) = indexes.get(reference.analysis_name.as_str()) {
                model_producers.insert(*index);
            }
        }
        producers.push(model_producers.into_iter().collect());
    }
    Some(producers)
}

/// `TopologicalSorter` waves in request order, or None when the graph has a cycle.
pub(crate) fn waves(producers: &[Vec<usize>]) -> Option<Vec<Vec<usize>>> {
    let mut pending: Vec<usize> = producers.iter().map(Vec::len).collect();
    let mut consumers: Vec<Vec<usize>> = vec![Vec::new(); producers.len()];
    for (model, model_producers) in producers.iter().enumerate() {
        for producer in model_producers {
            consumers[*producer].push(model);
        }
    }
    let mut ready: Vec<usize> = (0..producers.len())
        .filter(|model| pending[*model] == 0)
        .collect();
    let mut waves: Vec<Vec<usize>> = Vec::new();
    let mut scheduled: usize = 0;
    while !ready.is_empty() {
        scheduled += ready.len();
        let mut next: Vec<usize> = Vec::new();
        for model in &ready {
            for consumer in &consumers[*model] {
                pending[*consumer] -= 1;
                if pending[*consumer] == 0 {
                    next.push(*consumer);
                }
            }
        }
        next.sort_unstable();
        waves.push(std::mem::replace(&mut ready, next));
    }
    (scheduled == producers.len()).then_some(waves)
}
