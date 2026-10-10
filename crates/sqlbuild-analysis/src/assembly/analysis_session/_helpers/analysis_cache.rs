//! The session's per-model analysis cache: keys over everything a model's analysis reads, and
//! the stored form of a finished native outcome.

use std::collections::{BTreeSet, HashMap};

use sha2::{Digest, Sha256};
use sqlbuild_cache::digest::types::ContentDigest;
use sqlbuild_cache::store::errors::StoreDecodeError;
use sqlbuild_cache::store::models::NativeStore;

use crate::assembly::analysis_session::constants::ANALYSIS_CACHE_FORMAT;
use crate::assembly::analysis_session::models::{
    AnalysisCache, AnalysisCacheStats, AnalysisSession, ColumnFact, DynamicFamily, LineageFacts,
    LineageRow, ModelAnalysis, ModelOutcome, ModelRequest, SessionRequest,
};
use crate::assembly::analysis_session::types::{Pairs, Shapes};
use crate::semantic_validation::types::DiagnosticRow;

const LINEAGE_NATIVE: u64 = 0;
const LINEAGE_FACTS: u64 = 1;

/// A stored outcome and the whole-table digest it requires, if it came from a legacy analysis.
pub(crate) type CachedOutcome = (ModelOutcome, Option<ContentDigest>);

impl AnalysisSession {
    /// Read and fill `store`; its environment already names the build and Python's settings.
    pub(crate) fn attach_cache(&mut self, store: NativeStore) {
        let models: usize = self.request.models.len();
        self.cache = Some(AnalysisCache {
            store,
            session_digest: session_digest(&self.request),
            keys: vec![None; models],
            hits: vec![false; models],
            uncacheable: vec![false; models],
            legacy_tables: vec![None; models],
            stats: AnalysisCacheStats::default(),
        });
    }

    /// The store with this session's stored outcomes, and what the cache did.
    pub(crate) fn take_cache(&mut self) -> Option<(NativeStore, AnalysisCacheStats)> {
        self.cache.take().map(|cache| (cache.store, cache.stats))
    }

    /// Whether `model`'s outcome came from the cache, so its later passes are already applied.
    pub(crate) fn cached(&self, model: usize) -> bool {
        self.cache
            .as_ref()
            .is_some_and(|cache| cache.hits.get(model).copied().unwrap_or(false))
    }

    /// The names whose relation facts `model`'s analysis may read, in sorted order.
    pub(crate) fn model_relation_names(&self, model: usize) -> BTreeSet<&str> {
        let request: &ModelRequest = &self.request.models[model];
        request
            .references
            .iter()
            .map(|reference| reference.analysis_name.as_str())
            .chain(request.required_names.iter().map(String::as_str))
            .chain(
                request
                    .lineage_references
                    .iter()
                    .map(|(name, _, _)| name.as_str()),
            )
            .collect()
    }

    /// Digest of the types, nullability, closed shape and catalog schema the session holds
    /// for `name` now.
    pub(crate) fn relation_digest(&self, name: &str) -> ContentDigest {
        let mut key: KeyHasher = KeyHasher::default();
        key.text(name);
        put_optional_pairs(&mut key, self.available_types.get(name));
        put_optional_pairs(&mut key, self.available_nullability.get(name));
        put_optional_pairs(&mut key, self.complete_shapes.get(name));
        put_optional_pairs(&mut key, self.catalog.known_schema(name));
        key.finish()
    }

    /// The key of `model` analysed with `schema`, given [`Self::relation_digest`] of every
    /// name [`Self::model_relation_names`] returns.
    pub(crate) fn model_key(
        &self,
        session_digest: &ContentDigest,
        model: usize,
        schema: &Shapes,
        relations: &HashMap<&str, ContentDigest>,
    ) -> ContentDigest {
        let mut key: KeyHasher = KeyHasher::default();
        key.bytes(session_digest);
        put_model(&mut key, &self.request.models[model]);
        put_shapes(&mut key, schema);
        let names: BTreeSet<&str> = self.model_relation_names(model);
        key.count(names.len());
        for name in names {
            match relations.get(name) {
                Some(digest) => key.bytes(digest),
                None => key.bytes(&self.relation_digest(name)),
            }
        }
        key.flag(self.dependency_ordered);
        key.finish()
    }

    /// Digest of every relation's types and nullability, which a legacy analysis reads whole.
    pub(crate) fn tables_digest(&self) -> ContentDigest {
        let mut key: KeyHasher = KeyHasher::default();
        for table in [&self.available_types, &self.available_nullability] {
            let ordered: Vec<(&str, &Pairs)> = table.ordered();
            key.count(ordered.len());
            for (name, shape) in ordered {
                key.text(name);
                put_pairs(&mut key, shape);
            }
        }
        key.finish()
    }
}

/// SHA-256 over length-prefixed fields, the shared store's digest scheme, without buffering.
#[derive(Default)]
struct KeyHasher(Sha256);

impl KeyHasher {
    fn bytes(&mut self, value: &[u8]) {
        self.0.update((value.len() as u64).to_le_bytes());
        self.0.update(value);
    }

    fn text(&mut self, value: &str) {
        self.bytes(value.as_bytes());
    }

    fn count(&mut self, value: usize) {
        self.0.update((value as u64).to_le_bytes());
    }

    fn flag(&mut self, value: bool) {
        self.count(usize::from(value));
    }

    fn finish(self) -> ContentDigest {
        self.0.finalize().into()
    }
}

/// Digest of the request facts every model's analysis may read.
fn session_digest(request: &SessionRequest) -> ContentDigest {
    let mut key: KeyHasher = KeyHasher::default();
    key.text(ANALYSIS_CACHE_FORMAT);
    key.text(&request.dialect);
    key.flag(request.case_sensitive_shapes);
    put_pairs(&mut key, &request.function_return_types);
    put_optional_pairs(&mut key, request.nullability_rules.as_ref());
    key.flag(request.rich_type_inference);
    for shapes in [
        &request.column_types,
        &request.column_nullability,
        &request.complete_schemas,
        &request.catalog_schemas,
    ] {
        put_shapes(&mut key, shapes);
    }
    key.count(request.dynamic_families_by_table.len());
    for (table, families) in &request.dynamic_families_by_table {
        key.text(table);
        put_families(&mut key, families);
    }
    key.finish()
}

fn put_model(key: &mut KeyHasher, model: &ModelRequest) {
    key.text(&model.name);
    key.text(&model.query_sql);
    put_pairs(key, &model.placeholders);
    key.count(model.references.len());
    for reference in &model.references {
        key.text(&reference.analysis_name);
        key.flag(reference.model_ref);
    }
    key.count(model.lineage_references.len());
    for (name, resource_type, resource) in &model.lineage_references {
        key.text(name);
        key.text(resource_type);
        key.text(resource);
    }
    key.count(model.required_names.len());
    for name in &model.required_names {
        key.text(name);
    }
    key.flag(model.recover_cte_facts);
    key.flag(model.has_set_operation);
    match &model.snapshot_columns {
        Some((valid_from, valid_to)) => {
            key.flag(true);
            key.text(valid_from);
            key.text(valid_to);
        }
        None => key.flag(false),
    }
    key.text(&model.pivot_sql);
    put_families(key, &model.dynamic_families);
}

fn put_families(key: &mut KeyHasher, families: &[DynamicFamily]) {
    key.count(families.len());
    for family in families {
        key.text(&family.name);
        key.text(&family.pivot_column);
        key.text(&family.value_column);
        key.text(&family.aggregate);
        key.text(&family.data_type);
        match family.name_pattern.as_deref() {
            Some(pattern) => {
                key.flag(true);
                key.text(pattern);
            }
            None => key.flag(false),
        }
    }
}

fn put_pairs(key: &mut KeyHasher, pairs: &Pairs) {
    key.count(pairs.len());
    for (name, value) in pairs {
        key.text(name);
        key.text(value);
    }
}

fn put_optional_pairs(key: &mut KeyHasher, pairs: Option<&Pairs>) {
    match pairs {
        Some(pairs) => {
            key.flag(true);
            put_pairs(key, pairs);
        }
        None => key.flag(false),
    }
}

fn put_shapes(key: &mut KeyHasher, shapes: &Shapes) {
    key.count(shapes.len());
    for (name, shape) in shapes {
        key.text(name);
        put_pairs(key, shape);
    }
}

/// Varint fields over a per-entry string table, so repeated names are stored once.
#[derive(Default)]
struct Encoder<'a> {
    strings: Vec<&'a str>,
    ids: HashMap<&'a str, u64>,
    body: Vec<u8>,
}

impl<'a> Encoder<'a> {
    fn uint(&mut self, value: u64) {
        put_varint(&mut self.body, value);
    }

    fn flag(&mut self, value: bool) {
        self.uint(u64::from(value));
    }

    fn text(&mut self, value: &'a str) {
        let next: u64 = self.strings.len() as u64;
        let id: u64 = *self.ids.entry(value).or_insert_with(|| {
            self.strings.push(value);
            next
        });
        self.uint(id);
    }

    fn optional_text(&mut self, value: Option<&'a str>) {
        match value {
            Some(value) => {
                self.flag(true);
                self.text(value);
            }
            None => self.flag(false),
        }
    }

    fn optional_uint(&mut self, value: Option<usize>) {
        match value {
            Some(value) => {
                self.flag(true);
                self.uint(value as u64);
            }
            None => self.flag(false),
        }
    }

    fn into_bytes(self) -> Vec<u8> {
        let mut bytes: Vec<u8> = Vec::with_capacity(self.body.len() + 16 * self.strings.len());
        put_varint(&mut bytes, self.strings.len() as u64);
        for value in &self.strings {
            put_varint(&mut bytes, value.len() as u64);
            bytes.extend_from_slice(value.as_bytes());
        }
        bytes.extend_from_slice(&self.body);
        bytes
    }
}

fn put_varint(bytes: &mut Vec<u8>, mut value: u64) {
    while value >= 0x80 {
        bytes.push((value as u8 & 0x7f) | 0x80);
        value >>= 7;
    }
    bytes.push(value as u8);
}

/// Reads what an [`Encoder`] wrote; anything else is a decode error.
struct Decoder<'a> {
    bytes: &'a [u8],
    position: usize,
    strings: Vec<&'a str>,
}

impl<'a> Decoder<'a> {
    fn new(bytes: &'a [u8]) -> Result<Self, StoreDecodeError> {
        let mut decoder: Self = Self {
            bytes,
            position: 0,
            strings: Vec::new(),
        };
        let count: u64 = decoder.uint()?;
        for _ in 0..count {
            let length: usize = usize::try_from(decoder.uint()?).map_err(|_| StoreDecodeError)?;
            let end: usize = decoder
                .position
                .checked_add(length)
                .ok_or(StoreDecodeError)?;
            let raw: &'a [u8] = bytes.get(decoder.position..end).ok_or(StoreDecodeError)?;
            decoder
                .strings
                .push(std::str::from_utf8(raw).map_err(|_| StoreDecodeError)?);
            decoder.position = end;
        }
        Ok(decoder)
    }

    fn uint(&mut self) -> Result<u64, StoreDecodeError> {
        let mut value: u64 = 0;
        for shift in (0..64).step_by(7) {
            let byte: u8 = *self.bytes.get(self.position).ok_or(StoreDecodeError)?;
            self.position += 1;
            value |= u64::from(byte & 0x7f) << shift;
            if byte & 0x80 == 0 {
                return Ok(value);
            }
        }
        Err(StoreDecodeError)
    }

    fn index(&mut self) -> Result<usize, StoreDecodeError> {
        usize::try_from(self.uint()?).map_err(|_| StoreDecodeError)
    }

    fn flag(&mut self) -> Result<bool, StoreDecodeError> {
        match self.uint()? {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(StoreDecodeError),
        }
    }

    fn text(&mut self) -> Result<String, StoreDecodeError> {
        let id: usize = self.index()?;
        self.strings
            .get(id)
            .map(|value| (*value).to_owned())
            .ok_or(StoreDecodeError)
    }

    fn optional_text(&mut self) -> Result<Option<String>, StoreDecodeError> {
        if self.flag()? {
            self.text().map(Some)
        } else {
            Ok(None)
        }
    }

    fn optional_index(&mut self) -> Result<Option<usize>, StoreDecodeError> {
        if self.flag()? {
            self.index().map(Some)
        } else {
            Ok(None)
        }
    }

    fn finish(&self) -> Result<(), StoreDecodeError> {
        if self.position == self.bytes.len() {
            Ok(())
        } else {
            Err(StoreDecodeError)
        }
    }
}

/// The stored bytes of a finished native outcome without its cleaned SQL, which is the query's
/// normalization; Python's answers are never stored.
pub(crate) fn encode_outcome(
    outcome: &ModelOutcome,
    legacy_tables: Option<&ContentDigest>,
) -> Option<Vec<u8>> {
    let analysis: &ModelAnalysis = &outcome.analysis;
    let (tag, rows) = match &analysis.lineage {
        LineageFacts::Native(rows) => (LINEAGE_NATIVE, rows),
        LineageFacts::NativeFacts(rows) => (LINEAGE_FACTS, rows),
        LineageFacts::PythonAnalysis | LineageFacts::PythonEnrichment => return None,
    };
    let mut encoder: Encoder<'_> = Encoder::default();
    match legacy_tables {
        Some(digest) => {
            encoder.flag(true);
            encoder.body.extend_from_slice(digest);
        }
        None => encoder.flag(false),
    }
    encoder.flag(analysis.analysis_succeeded);
    match &analysis.columns {
        Some(columns) => {
            encoder.flag(true);
            encoder.uint(columns.len() as u64);
            for column in columns {
                encoder.text(&column.name);
                encoder.optional_text(column.data_type.as_deref());
                encoder.text(&column.nullability);
            }
        }
        None => encoder.flag(false),
    }
    encoder.uint(tag);
    encoder.uint(rows.len() as u64);
    for row in rows {
        encoder.text(&row.output_column);
        encoder.uint(u64::from(row.transform_code));
        encoder.uint(u64::from(row.confidence_code));
        encoder.uint(row.sources.len() as u64);
        for (resource_type, name, column) in &row.sources {
            encoder.text(resource_type);
            encoder.text(name);
            encoder.text(column);
        }
    }
    encoder.flag(analysis.has_star);
    encoder.flag(analysis.star_resolved);
    encoder.uint(analysis.binding_diagnostics.len() as u64);
    for (code, message, line, column, start, end, severity) in &analysis.binding_diagnostics {
        encoder.text(code);
        encoder.text(message);
        for position in [line, column, start, end] {
            encoder.optional_uint(*position);
        }
        encoder.text(severity);
    }
    encoder.flag(analysis.binding_validated);
    Some(encoder.into_bytes())
}

/// The outcome [`encode_outcome`] stored, validated against `schema`, still without its cleaned
/// SQL, which is normalized again; other bytes do not decode.
pub(crate) fn decode_outcome(
    bytes: &[u8],
    schema: &Shapes,
) -> Result<CachedOutcome, StoreDecodeError> {
    let mut decoder: Decoder<'_> = Decoder::new(bytes)?;
    let legacy_tables: Option<ContentDigest> = if decoder.flag()? {
        let end: usize = decoder.position + 32;
        let digest: ContentDigest = bytes
            .get(decoder.position..end)
            .ok_or(StoreDecodeError)?
            .try_into()
            .map_err(|_| StoreDecodeError)?;
        decoder.position = end;
        Some(digest)
    } else {
        None
    };
    let analysis_succeeded: bool = decoder.flag()?;
    let columns: Option<Vec<ColumnFact>> = if decoder.flag()? {
        let count: usize = decoder.index()?;
        let mut columns: Vec<ColumnFact> = Vec::with_capacity(count.min(bytes.len()));
        for _ in 0..count {
            columns.push(ColumnFact {
                name: decoder.text()?,
                data_type: decoder.optional_text()?,
                nullability: decoder.text()?,
            });
        }
        Some(columns)
    } else {
        None
    };
    let tag: u64 = decoder.uint()?;
    let row_count: usize = decoder.index()?;
    let mut rows: Vec<LineageRow> = Vec::with_capacity(row_count.min(bytes.len()));
    for _ in 0..row_count {
        let output_column: String = decoder.text()?;
        let transform_code: u8 = u8::try_from(decoder.uint()?).map_err(|_| StoreDecodeError)?;
        let confidence_code: u8 = u8::try_from(decoder.uint()?).map_err(|_| StoreDecodeError)?;
        let source_count: usize = decoder.index()?;
        let mut sources: Vec<(String, String, String)> =
            Vec::with_capacity(source_count.min(bytes.len()));
        for _ in 0..source_count {
            sources.push((decoder.text()?, decoder.text()?, decoder.text()?));
        }
        rows.push(LineageRow {
            output_column,
            transform_code,
            confidence_code,
            sources,
        });
    }
    let lineage: LineageFacts = match tag {
        LINEAGE_NATIVE => LineageFacts::Native(rows),
        LINEAGE_FACTS => LineageFacts::NativeFacts(rows),
        _ => return Err(StoreDecodeError),
    };
    let has_star: bool = decoder.flag()?;
    let star_resolved: bool = decoder.flag()?;
    let diagnostic_count: usize = decoder.index()?;
    let mut binding_diagnostics: Vec<DiagnosticRow> = Vec::new();
    for _ in 0..diagnostic_count {
        binding_diagnostics.push((
            decoder.text()?,
            decoder.text()?,
            decoder.optional_index()?,
            decoder.optional_index()?,
            decoder.optional_index()?,
            decoder.optional_index()?,
            decoder.text()?,
        ));
    }
    let binding_validated: bool = decoder.flag()?;
    decoder.finish()?;
    let outcome = ModelOutcome {
        analysis: ModelAnalysis {
            analysis_succeeded,
            columns,
            lineage,
            has_star,
            star_resolved,
            binding_diagnostics,
            binding_validated,
        },
        cleaned_sql: String::new(),
        validated_schema: schema.clone(),
        fused_binding_validated: true,
    };
    Ok((outcome, legacy_tables))
}
