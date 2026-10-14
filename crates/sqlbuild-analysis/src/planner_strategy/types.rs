//! Planner strategy callback types.

use crate::planner_strategy::models::{ProducerFacts, ReferenceIdentity};

/// Whether the second model name is downstream of the first.
pub type Reaches<'a, E> = dyn Fn(&str, &str) -> Result<bool, E> + 'a;

/// A timeline of cursor moments the caller owns: one batch step and the ordering.
pub trait Timeline {
    type Moment: Clone;
    type Error;

    /// The moment one batch after `moment`.
    fn advance(&self, moment: &Self::Moment) -> Result<Self::Moment, Self::Error>;

    /// Whether `left` sorts before `right`.
    fn precedes(&self, left: &Self::Moment, right: &Self::Moment) -> Result<bool, Self::Error>;
}

/// The project's SQL references as the caller holds them.
pub trait ReferenceGraph {
    type Reference: Clone;
    type Error;

    /// The kind and name of a reference.
    fn identity(&self, reference: &Self::Reference) -> Result<ReferenceIdentity, Self::Error>;

    /// The references of a model, when the project has it.
    fn model_references(&self, name: &str) -> Result<Option<Vec<Self::Reference>>, Self::Error>;

    /// The references of a SQL function, when the project has it.
    fn function_references(&self, name: &str) -> Result<Option<Vec<Self::Reference>>, Self::Error>;

    /// Whether a model is a microbatch model and caps its batches.
    fn producer_facts(&self, name: &str) -> Result<ProducerFacts, Self::Error>;

    /// The watermark input names of a model.
    fn watermark_inputs(&self, name: &str) -> Result<Vec<String>, Self::Error>;
}
