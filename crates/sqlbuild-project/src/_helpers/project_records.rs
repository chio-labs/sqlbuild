//! What the compiled project answers and records without the host.

use sqlbuild_analysis::compiled_project::main::model_facts::model_facts;
use sqlbuild_analysis::compiled_project::main::record_model::record_model;
use sqlbuild_analysis::compiled_project::models::{
    CompiledModelFacts, CompiledProjectFacts, ModelSchemaFact,
};

use crate::models::{
    AuditRecord, CompiledProject, FunctionRecord, ModelInputRecord, SeedRecord, SourceRecord,
};
use crate::types::ProjectHost;

impl<H: ProjectHost> Default for CompiledProject<H> {
    fn default() -> Self {
        Self::with_facts(CompiledProjectFacts::default())
    }
}

impl<H: ProjectHost> CompiledProject<H> {
    /// A project holding only `facts`, which analyses can be recorded into apart from the compile's.
    pub fn with_facts(facts: CompiledProjectFacts) -> Self {
        Self {
            facts,
            inputs: Vec::new(),
            graph_builds: 0,
            seeds: Vec::new(),
            sources: Vec::new(),
            functions: Vec::new(),
            audits: Vec::new(),
        }
    }

    /// Retain facts a producer finished natively.
    pub fn retain(&mut self, facts: CompiledModelFacts) {
        record_model(&mut self.facts, facts);
    }

    /// Retain a finished model's input record; return its index for the model's view.
    pub fn retain_input(&mut self, record: ModelInputRecord<H>) -> usize {
        self.inputs.push(record);
        self.inputs.len() - 1
    }

    /// The schema fact recorded for an input record's model.
    pub fn input_schema_fact(&self, record: &ModelInputRecord<H>) -> Option<&ModelSchemaFact> {
        model_facts(&self.facts, &record.name).and_then(|facts| facts.schema.as_ref())
    }

    /// The input record at `index`, or `None` past the last model.
    #[inline]
    pub fn input(&self, index: usize) -> Option<&ModelInputRecord<H>> {
        self.inputs.get(index)
    }

    /// Every attached audit, in attachment order.
    #[inline]
    pub fn audits(&self) -> &[AuditRecord<H>] {
        &self.audits
    }

    /// Every attached function, in attachment order.
    #[inline]
    pub fn functions(&self) -> &[FunctionRecord<H>] {
        &self.functions
    }

    /// Every attached source, in attachment order.
    #[inline]
    pub fn sources(&self) -> &[SourceRecord<H>] {
        &self.sources
    }

    /// Every attached seed, in attachment order.
    #[inline]
    pub fn seeds(&self) -> &[SeedRecord<H>] {
        &self.seeds
    }
}
