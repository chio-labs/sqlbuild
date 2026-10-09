//! Python's CTE fact recovery and filtered non-null outputs, over the wheel's expression view.

use std::cell::Cell;
use std::collections::HashSet;
use std::rc::Rc;

use polyglot_sql::Expression;
use polyglot_sql::traversal::ExpressionWalk;
use serde_json::{Map, Value};

use crate::assembly::analysis_session::_helpers::dict_walk::{
    PyValue, alias_or_name, arg, children, column_table_name, direct_tables, expression_args,
    find_all, is_star, kind, name, name_payload, output_name, parse_one, projected_expression,
    py_truthy, python_int, raw_name_payload, set_operation, to_dict, top_level_ctes,
    unwrap_annotations, where_clause,
};
use crate::assembly::analysis_session::constants::{
    BINARY_OPERAND_COUNT, BOOLEAN_RESULT_AST_KINDS, BOOLEAN_TYPE, CASE_AST_KIND, CAST_AST_KIND,
    CAST_AST_KINDS, COALESCE_AST_KIND, COLUMN_AST_KIND, CONCAT_AST_KIND, CONDITIONAL_RESULT_RULE,
    COUNT_AST_KIND, CUSTOM_TYPE_NAME, DECIMAL_TYPE, FIRST_ARG_RULE, FUNCTION_AST_KIND,
    IF_FUNC_AST_KIND, IS_NULL_AST_KIND, JOIN_FULL, JOIN_LEFT, JOIN_RIGHT, LITERAL_AST_KIND,
    NON_NULL_NULLABILITY, NULL_AST_KIND, NULL_SET_OPERATION_TYPE, NULLABLE_NULLABILITY,
    NULLIF_FUNCTION_NAME, POLYGLOT_TYPE_NAMES, SELECT_AST_KIND, SET_OPERATION_AST_KINDS,
    STRING_LITERAL_TYPE, SUBSTRING_AST_KIND, TABLE_AST_KIND, TEXT_TYPE, TIMESTAMP_TYPE_NAME,
    TIMESTAMP_TZ_TYPE, TRY_CAST_AST_KIND, TYPE_PASSTHROUGH_AST_KINDS, UNKNOWN_NULLABILITY,
    VARCHAR_DATA_TYPES, WILDCARD,
};
use crate::assembly::analysis_session::types::{Pairs, Shapes};
use crate::type_system::main::normalize_type::normalize_type;
use crate::type_system::models::{NormalizedType, TypeFamily};

/// A relation's column types; the `Rc` is the identity Python's `id()` dedup compares.
type Shape = Rc<Pairs>;
/// Relation facts in Python dict order.
type Relations = Vec<(String, Shape)>;
/// A relation's column nullabilities.
type NullShape = Rc<Vec<(String, &'static str)>>;
type NullRelations = Vec<(String, NullShape)>;
/// Python's `NonNullFilterContext`: the selected relations and the proven non-null columns.
type FilterContext = (Vec<(String, NullShape)>, HashSet<(String, String)>);
/// The result of one step, or the reason Python's result is not reproduced.
type Fact<T> = Result<T, String>;

/// The inference profile facts the recovery reads.
pub(crate) struct RecoveryProfile<'a> {
    pub(crate) dialect: &'a str,
    pub(crate) function_return_types: &'a Pairs,
    /// Adapter nullability rules by function name; None where a rule is not one Python ships.
    pub(crate) rules: Option<&'a Pairs>,
}

/// One enrichment's recovery request.
pub(crate) struct RecoveryInput<'a> {
    pub(crate) cleaned_sql: &'a str,
    pub(crate) input_schemas: &'a Shapes,
    /// Whether Python runs `_polyglot_cte_passthrough_facts` past its early return.
    pub(crate) recover: bool,
    /// Whether a filter reads NULL, so Python looks for filtered non-null outputs.
    pub(crate) null_filter: bool,
    pub(crate) profile: RecoveryProfile<'a>,
}

/// What Python's compact re-analysis takes from the parsed query.
#[derive(Debug, Default)]
pub(crate) struct Recovery {
    pub(crate) types: Vec<(String, String)>,
    pub(crate) nullability: Vec<(String, &'static str)>,
    pub(crate) direct_outputs: HashSet<String>,
    pub(crate) non_null_outputs: HashSet<String>,
}

/// Python's CTE pass-through facts and filtered non-null outputs, or why they defer.
pub(crate) fn recovery(input: &RecoveryInput<'_>) -> Fact<Recovery> {
    NON_ASCII_FOLDED.set(false);
    let recovered: Fact<Recovery> = recovered(input);
    if NON_ASCII_FOLDED.replace(false) {
        return Err("non-ASCII text Python casefolds or upper-cases differently".to_owned());
    }
    recovered
}

thread_local! {
    /// Whether this recovery folded non-ASCII text, where Python's `casefold`/`upper` may differ.
    static NON_ASCII_FOLDED: Cell<bool> = const { Cell::new(false) };
}

fn recovered(input: &RecoveryInput<'_>) -> Fact<Recovery> {
    let mut recovery: Recovery = Recovery::default();
    let mut parsed: Option<Option<Expression>> = None;
    if input.recover {
        let root: Option<Expression> = parse_one(input.cleaned_sql, input.profile.dialect)?;
        if let Some(root) = &root {
            recovery = passthrough_facts(root, input, recovery)?;
        }
        parsed = Some(root);
    }
    if input.null_filter {
        let root: Option<Expression> = match parsed {
            Some(root) => root,
            None => parse_one(input.cleaned_sql, input.profile.dialect)?,
        };
        if let Some(root) = &root {
            recovery.non_null_outputs = filtered_non_null(root, &input_nullability(input))?;
        }
    }
    Ok(recovery)
}

/// Python's enrichment types: the input shapes.
fn input_types(input: &RecoveryInput<'_>) -> Relations {
    input
        .input_schemas
        .iter()
        .map(|(table, shape)| (table.clone(), Rc::new(shape.clone())))
        .collect()
}

/// Python's enrichment nullability: every input column unknown.
fn input_nullability(input: &RecoveryInput<'_>) -> NullRelations {
    input
        .input_schemas
        .iter()
        .map(|(table, shape)| (table.clone(), Rc::new(unknown_columns(shape))))
        .collect()
}

fn unknown_columns(shape: &Pairs) -> Vec<(String, &'static str)> {
    shape
        .iter()
        .map(|(column, _)| (column.clone(), UNKNOWN_NULLABILITY))
        .collect()
}

/// Python's `_polyglot_cte_passthrough_facts` after a successful parse.
fn passthrough_facts(
    root: &Expression,
    input: &RecoveryInput<'_>,
    mut recovery: Recovery,
) -> Fact<Recovery> {
    let ctes: Vec<(&str, bool, &Expression)> = top_level_ctes(root);
    if ctes.is_empty() {
        return Ok(recovery);
    }
    if input.profile.rules.is_none() {
        return Err("an adapter nullability rule Python does not ship".to_owned());
    }
    let context = Context {
        profile: &input.profile,
    };
    recovery.types = context.passthrough_types(root, &input_types(input))?;
    recovery.nullability = context.passthrough_nullability(root, &input_nullability(input))?;
    let names: HashSet<String> = ctes.iter().map(|(name, _, _)| casefold(name)).collect();
    recovery.direct_outputs = direct_cte_outputs(root, &names);
    Ok(recovery)
}

/// Python's `_polyglot_direct_cte_output_names`.
fn direct_cte_outputs(root: &Expression, cte_names: &HashSet<String>) -> HashSet<String> {
    let reads_cte: bool = direct_tables(root)
        .iter()
        .any(|table| cte_names.contains(&casefold(table.get_name())));
    if !reads_cte {
        return HashSet::new();
    }
    let mut outputs: HashSet<String> = HashSet::new();
    for projection in root.get_expressions() {
        let projection: Option<&Expression> = unwrap_annotations(Some(projection));
        if kind(projected_expression(projection)) != COLUMN_AST_KIND {
            continue;
        }
        let output: &str = output_name(projection);
        if !output.is_empty() && output != WILDCARD {
            outputs.insert(output.to_owned());
        }
    }
    outputs
}

/// The profile every resolver reads.
struct Context<'a, 'b> {
    profile: &'a RecoveryProfile<'b>,
}

impl Context<'_, '_> {
    /// Python's `_polyglot_cte_passthrough_types_from_parsed`.
    fn passthrough_types(
        &self,
        root: &Expression,
        facts: &Relations,
    ) -> Fact<Vec<(String, String)>> {
        let ctes: Vec<(&str, bool, &Expression)> = top_level_ctes(root);
        if ctes.is_empty() {
            return Ok(Vec::new());
        }
        let mut relations: Relations = referenced_facts(root, facts);
        for (cte_name, has_column_aliases, body) in ctes {
            if has_column_aliases {
                continue;
            }
            let inferred: Vec<(String, String)> =
                self.select_output_types(Some(body), &relations)?;
            if !inferred.is_empty() {
                relations = dict_set(relations, cte_name, Rc::new(inferred));
            }
        }
        if SET_OPERATION_AST_KINDS.contains(&kind(Some(root))) {
            return self.set_operation_types(root, &relations);
        }
        self.direct_select_types(Some(root), &relations)
    }

    /// Python's `_polyglot_select_output_types`.
    fn select_output_types(
        &self,
        select: Option<&Expression>,
        relations: &Relations,
    ) -> Fact<Vec<(String, String)>> {
        let Some(select) = unwrap_annotations(select) else {
            return Err("Python reads CTEs of a missing expression".to_owned());
        };
        if !top_level_ctes(select).is_empty() {
            return self.passthrough_types(select, relations);
        }
        if SET_OPERATION_AST_KINDS.contains(&kind(Some(select))) {
            return self.set_operation_types(select, relations);
        }
        self.direct_select_types(Some(select), relations)
    }

    /// Python's `_polyglot_set_operation_output_types`.
    fn set_operation_types(
        &self,
        operation: &Expression,
        relations: &Relations,
    ) -> Fact<Vec<(String, String)>> {
        let Some((left, right, by_name)) = set_operation(operation) else {
            return Ok(Vec::new());
        };
        let mut output: Vec<(String, String)> = Vec::new();
        if by_name {
            let left_types: Vec<(String, String)> =
                self.select_output_types(Some(left), relations)?;
            let right_types: Vec<(String, String)> =
                self.select_output_types(Some(right), relations)?;
            for (name, left_type) in &left_types {
                let right_type: Option<&str> = ci_get(&right_types, name).map(String::as_str);
                if let Some(common) = self.common_type(Some(left_type), right_type)? {
                    output = dict_set(output, name, common);
                }
            }
            return Ok(output);
        }
        let left_slots: Vec<Slot> = self.type_slots(Some(left), relations)?;
        if left_slots.is_empty() {
            return Ok(Vec::new());
        }
        let right_slots: Vec<Slot> = self.type_slots(Some(right), relations)?;
        if right_slots.is_empty() || left_slots.len() != right_slots.len() {
            return Ok(Vec::new());
        }
        for ((name, left_type), (_, right_type)) in left_slots.iter().zip(&right_slots) {
            if let Some(common) = self.common_type(left_type.as_deref(), right_type.as_deref())? {
                output = dict_set(output, name, common);
            }
        }
        Ok(output)
    }

    /// Python's `_polyglot_select_output_type_slots`.
    fn type_slots(&self, select: Option<&Expression>, relations: &Relations) -> Fact<Vec<Slot>> {
        let select: Option<&Expression> = unwrap_annotations(select);
        if let Some((left, right, by_name)) = select.and_then(set_operation) {
            let left_slots: Vec<Slot> = self.type_slots(Some(left), relations)?;
            if left_slots.is_empty() {
                return Ok(Vec::new());
            }
            let right_slots: Vec<Slot> = self.type_slots(Some(right), relations)?;
            if right_slots.is_empty() {
                return Ok(Vec::new());
            }
            return self.combined_slots(&left_slots, &right_slots, by_name);
        }
        let Some(select) = select.filter(|select| kind(Some(select)) == SELECT_AST_KIND) else {
            return Ok(Vec::new());
        };
        let inferred: Vec<(String, String)> = self.direct_select_types(Some(select), relations)?;
        let mut slots: Vec<Slot> = Vec::new();
        for projection in select.get_expressions() {
            let projection: Option<&Expression> = unwrap_annotations(Some(projection));
            let output: &str = output_name(projection);
            if is_star(projection) || output.is_empty() || output == WILDCARD {
                return Ok(Vec::new());
            }
            let mut inferred_type: Option<String> = ci_get(&inferred, output).cloned();
            if inferred_type.is_none() && kind(projected_expression(projection)) == NULL_AST_KIND {
                inferred_type = Some(NULL_SET_OPERATION_TYPE.to_owned());
            }
            slots.push((output.to_owned(), inferred_type));
        }
        Ok(slots)
    }

    fn combined_slots(&self, left: &[Slot], right: &[Slot], by_name: bool) -> Fact<Vec<Slot>> {
        if by_name {
            let mut right_types: Vec<Slot> = Vec::new();
            for (name, slot_type) in right {
                right_types = dict_set(right_types, name, slot_type.clone());
            }
            let mut slots: Vec<Slot> = Vec::with_capacity(left.len());
            for (name, left_type) in left {
                let right_type: Option<&str> = ci_get_optional(&right_types, name);
                slots.push((
                    name.clone(),
                    self.common_type(left_type.as_deref(), right_type)?,
                ));
            }
            return Ok(slots);
        }
        if left.len() != right.len() {
            return Ok(Vec::new());
        }
        let mut slots: Vec<Slot> = Vec::with_capacity(left.len());
        for ((name, left_type), (_, right_type)) in left.iter().zip(right) {
            slots.push((
                name.clone(),
                self.common_type(left_type.as_deref(), right_type.as_deref())?,
            ));
        }
        Ok(slots)
    }

    /// Python's `_polyglot_common_set_operation_type`.
    fn common_type(&self, left: Option<&str>, right: Option<&str>) -> Fact<Option<String>> {
        let null: Option<&str> = Some(NULL_SET_OPERATION_TYPE);
        if left == null && right == null {
            return Ok(None);
        }
        if left == null {
            return Ok(right.map(str::to_owned));
        }
        if right == null {
            return Ok(left.map(str::to_owned));
        }
        let (Some(left), Some(right)) = (left, right) else {
            return Ok(None);
        };
        Ok(self.types_equal(left, right)?.then(|| left.to_owned()))
    }

    /// Python's `_polyglot_types_equal`.
    fn types_equal(&self, left: &str, right: &str) -> Fact<bool> {
        Ok(left == right || self.normalized(left)? == self.normalized(right)?)
    }

    /// Python's `normalize_type`, or a deferral where the native normalization defers.
    fn normalized(&self, type_sql: &str) -> Fact<NormalizedType> {
        normalize_type(type_sql, self.profile.dialect)
            .map(|normalization| normalization.normalized)
            .ok_or_else(|| format!("type normalization of {type_sql} defers"))
    }

    /// Python's `_polyglot_direct_select_output_types`.
    fn direct_select_types(
        &self,
        select: Option<&Expression>,
        relations: &Relations,
    ) -> Fact<Vec<(String, String)>> {
        let Some(select) = select.filter(|select| kind(Some(select)) == SELECT_AST_KIND) else {
            return Ok(Vec::new());
        };
        let mut by_alias: Relations = Vec::new();
        for table in direct_tables(select) {
            let table_name: &str = table.get_name();
            let Some(column_types) = ci_get(relations, table_name) else {
                continue;
            };
            let column_types: Shape = Rc::clone(column_types);
            by_alias = dict_set(by_alias, table_name, Rc::clone(&column_types));
            let alias: &str = alias_or_name(table);
            if !alias.is_empty() {
                by_alias = dict_set(by_alias, alias, column_types);
            }
        }
        let mut inferred: Vec<(String, String)> = Vec::new();
        for projection in select.get_expressions() {
            let projection: Option<&Expression> = unwrap_annotations(Some(projection));
            if let Some(star) = projection.filter(|projection| is_star(Some(projection))) {
                for (column, column_type) in star_types(star, &by_alias)? {
                    inferred = dict_set(inferred, &column, column_type);
                }
                continue;
            }
            let output: &str = output_name(projection);
            if output.is_empty() || output == WILDCARD {
                continue;
            }
            let expression: Option<&Expression> = projected_expression(projection);
            if let Some(inferred_type) = self.expression_type_in(expression, &by_alias)? {
                inferred = dict_set(inferred, output, inferred_type);
            }
        }
        Ok(inferred)
    }

    /// Python's `_polyglot_direct_expression_type`.
    fn expression_type_in(
        &self,
        expression: Option<&Expression>,
        by_alias: &Relations,
    ) -> Fact<Option<String>> {
        let expression: Option<&Expression> = unwrap_annotations(expression);
        let node_kind: &str = kind(expression);
        if let Some(inferred) = self.expression_type(expression)? {
            return Ok(Some(inferred));
        }
        let Some(node) = expression else {
            return Ok(None);
        };
        if node_kind == COLUMN_AST_KIND {
            return direct_column_type(node, by_alias);
        }
        if BOOLEAN_RESULT_AST_KINDS.contains(&node_kind) {
            return Ok(Some(BOOLEAN_TYPE.to_owned()));
        }
        if node_kind == CONCAT_AST_KIND {
            return self.concat_type(node, by_alias);
        }
        if node_kind == SUBSTRING_AST_KIND {
            return self.value_type(arg(Some(node), "this")?, by_alias);
        }
        if TYPE_PASSTHROUGH_AST_KINDS.contains(&node_kind) {
            if let Some(inner) = node.get_this() {
                return self.expression_type_in(Some(inner), by_alias);
            }
            return self.value_type(arg(Some(node), "this")?, by_alias);
        }
        let results: Vec<Option<Expression>> = result_expressions(node)?;
        if results.is_empty() {
            return Ok(None);
        }
        self.common_result_type(&results, by_alias)
    }

    /// The type of a converted payload value; a non-expression has none.
    fn value_type(&self, value: Option<PyValue>, by_alias: &Relations) -> Fact<Option<String>> {
        match value {
            Some(PyValue::Expr(inner)) => self.expression_type_in(Some(&inner), by_alias),
            _ => Ok(None),
        }
    }

    fn concat_type(&self, node: &Expression, by_alias: &Relations) -> Fact<Option<String>> {
        let operands: Vec<PyValue> = [arg(Some(node), "left")?, arg(Some(node), "right")?]
            .into_iter()
            .flatten()
            .collect();
        if operands.len() != BINARY_OPERAND_COUNT {
            return Ok(None);
        }
        let mut operand_types: Vec<String> = Vec::with_capacity(BINARY_OPERAND_COUNT);
        for operand in operands {
            let PyValue::Expr(operand) = operand else {
                return Ok(None);
            };
            if string_literal(&operand)? {
                operand_types.push(TEXT_TYPE.to_owned());
                continue;
            }
            let Some(operand_type) = self.expression_type_in(Some(&operand), by_alias)? else {
                return Ok(None);
            };
            operand_types.push(operand_type);
        }
        for operand_type in &operand_types {
            if self.normalized(operand_type)?.family != TypeFamily::String {
                return Ok(None);
            }
        }
        Ok(Some(TEXT_TYPE.to_owned()))
    }

    /// Python's `_polyglot_common_result_type`.
    fn common_result_type(
        &self,
        expressions: &[Option<Expression>],
        by_alias: &Relations,
    ) -> Fact<Option<String>> {
        let mut resolved: Vec<String> = Vec::new();
        for expression in expressions {
            let Some(expression) = expression else {
                return Ok(None);
            };
            let expression: Option<&Expression> = unwrap_annotations(Some(expression));
            if kind(expression) == NULL_AST_KIND {
                continue;
            }
            let Some(resolved_type) = self.expression_type_in(expression, by_alias)? else {
                return Ok(None);
            };
            resolved.push(resolved_type);
        }
        let Some((first, others)) = resolved.split_first() else {
            return Ok(None);
        };
        for other in others {
            if !self.types_equal(first, other)? {
                return Ok(None);
            }
        }
        Ok(Some(first.clone()))
    }

    /// Python's `_polyglot_expression_type`.
    fn expression_type(&self, expression: Option<&Expression>) -> Fact<Option<String>> {
        let node_kind: &str = kind(expression);
        let node_name: &str = name(expression);
        let function_name: &str = if node_name.is_empty() {
            node_kind
        } else {
            node_name
        };
        if node_kind != COLUMN_AST_KIND
            && let Some(declared) = self.function_return_type(function_name)?
        {
            return Ok(Some(declared));
        }
        if BOOLEAN_RESULT_AST_KINDS.contains(&node_kind) {
            return Ok(Some(BOOLEAN_TYPE.to_owned()));
        }
        let Some(node) = expression.filter(|_| CAST_AST_KINDS.contains(&node_kind)) else {
            return Ok(None);
        };
        let value: Value = to_dict(node)?;
        let target: Option<&Map<String, Value>> = value
            .get(node_kind)
            .and_then(Value::as_object)
            .and_then(|payload| payload.get("to"))
            .and_then(Value::as_object);
        Ok(target.and_then(cast_target_type))
    }

    /// Python's `ExpressionInferenceProfile.function_return_type`.
    fn function_return_type(&self, function_name: &str) -> Fact<Option<String>> {
        let upper: String = upper(function_name);
        Ok(self
            .profile
            .function_return_types
            .iter()
            .find(|(declared, _)| *declared == upper)
            .map(|(_, return_type)| return_type.clone()))
    }

    /// Python's `_polyglot_cte_passthrough_nullability_from_parsed`.
    fn passthrough_nullability(
        &self,
        root: &Expression,
        facts: &NullRelations,
    ) -> Fact<Vec<(String, &'static str)>> {
        let ctes: Vec<(&str, bool, &Expression)> = top_level_ctes(root);
        if ctes.is_empty() {
            return Ok(Vec::new());
        }
        let mut relations: NullRelations = referenced_facts(root, facts);
        for (cte_name, has_column_aliases, body) in ctes {
            if has_column_aliases {
                continue;
            }
            let inferred: Vec<(String, &'static str)> =
                self.direct_select_nullability(body, &relations)?;
            if !inferred.is_empty() {
                relations = dict_set(relations, cte_name, Rc::new(inferred));
            }
        }
        self.direct_select_nullability(root, &relations)
    }

    /// Python's `_polyglot_direct_select_output_nullability`.
    fn direct_select_nullability(
        &self,
        select: &Expression,
        relations: &NullRelations,
    ) -> Fact<Vec<(String, &'static str)>> {
        if kind(Some(select)) != SELECT_AST_KIND {
            return Ok(Vec::new());
        }
        let mut scoped: NullRelations = Vec::new();
        for table in direct_tables(select) {
            let table_name: &str = table.get_name();
            if let Some(facts) = ci_get(relations, table_name) {
                scoped = dict_set(scoped, table_name, Rc::new(facts.as_ref().clone()));
            }
        }
        let known: bool = scoped.iter().any(|(_, facts)| has_known_nullability(facts));
        let (aliases, scoped): (Vec<(String, &'static str)>, NullRelations) = if known {
            alias_nullability(select, scoped)?
        } else {
            (Vec::new(), scoped)
        };
        let filter: Option<FilterContext> = filter_context(select, &scoped)?;
        let mut inferred: Vec<(String, &'static str)> = Vec::new();
        for projection in select.get_expressions() {
            let projection: Option<&Expression> = unwrap_annotations(Some(projection));
            if is_star(projection) {
                continue;
            }
            let output: &str = output_name(projection);
            if output.is_empty() || output == WILDCARD {
                continue;
            }
            let expression: Option<&Expression> = projected_expression(projection);
            let nullability: &'static str = if non_null_after_filter(expression, filter.as_ref())? {
                NON_NULL_NULLABILITY
            } else if known {
                self.nullability(expression, &aliases, &scoped)?
            } else {
                self.shallow_nullability(expression)?
            };
            if nullability != UNKNOWN_NULLABILITY {
                inferred = dict_set(inferred, output, nullability);
            }
        }
        Ok(inferred)
    }

    /// Python's `_infer_polyglot_nullability`.
    fn nullability(
        &self,
        expression: Option<&Expression>,
        aliases: &[(String, &'static str)],
        scoped: &NullRelations,
    ) -> Fact<&'static str> {
        let node_kind: &str = kind(expression);
        match node_kind {
            NULL_AST_KIND => return Ok(NULLABLE_NULLABILITY),
            LITERAL_AST_KIND | COUNT_AST_KIND | IS_NULL_AST_KIND => {
                return Ok(NON_NULL_NULLABILITY);
            }
            TRY_CAST_AST_KIND => return Ok(UNKNOWN_NULLABILITY),
            _ => {}
        }
        if let Some(column) = expression.filter(|_| node_kind == COLUMN_AST_KIND) {
            return column_nullability(column, aliases, scoped);
        }
        if node_kind == CAST_AST_KIND {
            return match expression.and_then(Expression::get_this) {
                Some(inner) => self.nullability(Some(inner), aliases, scoped),
                None => Ok(UNKNOWN_NULLABILITY),
            };
        }
        let rule: Option<&str> = self.rule(node_kind)?;
        if node_kind != COALESCE_AST_KIND && rule.is_none() {
            return Ok(UNKNOWN_NULLABILITY);
        }
        let mut arguments: Vec<&'static str> = Vec::new();
        for child in expression_args(expression) {
            arguments.push(self.nullability(Some(child), aliases, scoped)?);
        }
        Ok(combined(node_kind, rule, &arguments))
    }

    /// Python's `_infer_polyglot_shallow_nullability`.
    fn shallow_nullability(&self, expression: Option<&Expression>) -> Fact<&'static str> {
        let node_kind: &str = kind(expression);
        match node_kind {
            NULL_AST_KIND => return Ok(NULLABLE_NULLABILITY),
            LITERAL_AST_KIND | COUNT_AST_KIND | IS_NULL_AST_KIND => {
                return Ok(NON_NULL_NULLABILITY);
            }
            COLUMN_AST_KIND | TRY_CAST_AST_KIND => return Ok(UNKNOWN_NULLABILITY),
            _ => {}
        }
        if node_kind == CAST_AST_KIND {
            return match expression.and_then(Expression::get_this) {
                Some(inner) => self.shallow_nullability(Some(inner)),
                None => Ok(UNKNOWN_NULLABILITY),
            };
        }
        let rule: Option<&str> = self.rule(node_kind)?;
        if node_kind != COALESCE_AST_KIND && rule.is_none() {
            return Ok(UNKNOWN_NULLABILITY);
        }
        let mut arguments: Vec<&'static str> = Vec::new();
        for child in expression_args(expression) {
            arguments.push(self.shallow_nullability(Some(child))?);
        }
        Ok(combined(node_kind, rule, &arguments))
    }

    /// `inference_profile.function_nullability_rule(kind)`.
    fn rule(&self, node_kind: &str) -> Fact<Option<&str>> {
        let rules: &Pairs = self
            .profile
            .rules
            .ok_or("an adapter nullability rule Python does not ship")?;
        let upper: String = upper(node_kind);
        Ok(rules
            .iter()
            .find(|(declared, _)| *declared == upper)
            .map(|(_, rule)| rule.as_str()))
    }
}

/// One set operation output slot: its name and type, None where unproven.
type Slot = (String, Option<String>);

/// COALESCE's or an adapter rule's nullability over the argument nullabilities.
fn combined(node_kind: &str, rule: Option<&str>, arguments: &[&'static str]) -> &'static str {
    if node_kind == COALESCE_AST_KIND {
        if arguments.contains(&NON_NULL_NULLABILITY) {
            return NON_NULL_NULLABILITY;
        }
        if !arguments.is_empty() && arguments.iter().all(|value| *value == NULLABLE_NULLABILITY) {
            return NULLABLE_NULLABILITY;
        }
        return UNKNOWN_NULLABILITY;
    }
    match rule {
        Some(FIRST_ARG_RULE) => arguments.first().copied().unwrap_or(UNKNOWN_NULLABILITY),
        Some(CONDITIONAL_RESULT_RULE) => conditional_result(arguments),
        _ => UNKNOWN_NULLABILITY,
    }
}

/// Python's `conditional_result_nullability`.
fn conditional_result(arguments: &[&'static str]) -> &'static str {
    let [_, when_true, when_false, ..] = arguments else {
        return UNKNOWN_NULLABILITY;
    };
    if *when_true == NON_NULL_NULLABILITY && *when_false == NON_NULL_NULLABILITY {
        return NON_NULL_NULLABILITY;
    }
    if *when_true == NULLABLE_NULLABILITY || *when_false == NULLABLE_NULLABILITY {
        return NULLABLE_NULLABILITY;
    }
    UNKNOWN_NULLABILITY
}

/// Python's `_infer_polyglot_column_nullability`.
fn column_nullability(
    column: &Expression,
    aliases: &[(String, &'static str)],
    scoped: &NullRelations,
) -> Fact<&'static str> {
    let column_name: &str = column.get_name();
    if column_name.is_empty() {
        return Ok(UNKNOWN_NULLABILITY);
    }
    let table_name: String = column_table_name(column)?;
    if !table_name.is_empty() {
        if dict_get(aliases, &table_name) == Some(&NULLABLE_NULLABILITY) {
            return Ok(NULLABLE_NULLABILITY);
        }
        return Ok(dict_get(scoped, &table_name)
            .and_then(|facts| dict_get(facts, column_name))
            .copied()
            .unwrap_or(UNKNOWN_NULLABILITY));
    }
    let matches: Vec<&'static str> = scoped
        .iter()
        .filter_map(|(_, facts)| dict_get(facts, column_name).copied())
        .collect();
    Ok(match matches.as_slice() {
        [only] => only,
        _ => UNKNOWN_NULLABILITY,
    })
}

/// Python's `_polyglot_alias_nullability_from_select`, copying facts to aliases in `scoped`.
fn alias_nullability(
    select: &Expression,
    mut scoped: NullRelations,
) -> Fact<(Vec<(String, &'static str)>, NullRelations)> {
    let mut aliases: Vec<(String, &'static str)> = Vec::new();
    let mut current: Vec<String> = Vec::new();
    let value: Value = to_dict(select)?;
    let Some(payload) = value.get("select").and_then(Value::as_object) else {
        return Ok((aliases, scoped));
    };
    let from: Option<&Vec<Value>> = payload
        .get("from")
        .and_then(Value::as_object)
        .and_then(|from| from.get("expressions"))
        .and_then(Value::as_array);
    if let Some([relation]) = from.map(Vec::as_slice)
        && let Some(table) = relation
            .get(TABLE_AST_KIND)
            .filter(|table| table.is_object())
    {
        let (alias, table_name) = table_alias_and_name(table);
        current.push(alias.clone());
        aliases = dict_set(aliases, &alias, UNKNOWN_NULLABILITY);
        scoped = copy_facts_to_alias(&alias, &table_name, scoped);
    }
    let Some(joins) = payload.get("joins").and_then(Value::as_array) else {
        return Ok((aliases, scoped));
    };
    for join in joins.iter().filter_map(Value::as_object) {
        let Some(table) = join
            .get("this")
            .filter(|this| this.is_object())
            .and_then(|this| this.get(TABLE_AST_KIND))
            .filter(|table| table.is_object())
        else {
            continue;
        };
        let (joined, joined_name) = table_alias_and_name(table);
        let side: String = match join.get("kind") {
            None | Some(Value::Null) => String::new(),
            Some(Value::String(side)) => upper(side),
            Some(_) => return Err("a join side Python stringifies".to_owned()),
        };
        let current_side: Option<&'static str> = match side.as_str() {
            JOIN_RIGHT | JOIN_FULL => Some(NULLABLE_NULLABILITY),
            _ => None,
        };
        if let Some(nullability) = current_side {
            for alias in &current {
                aliases = dict_set(aliases, alias, nullability);
            }
        }
        let joined_nullability: &'static str = match side.as_str() {
            JOIN_LEFT | JOIN_FULL => NULLABLE_NULLABILITY,
            _ => UNKNOWN_NULLABILITY,
        };
        aliases = dict_set(aliases, &joined, joined_nullability);
        current.push(joined.clone());
        scoped = copy_facts_to_alias(&joined, &joined_name, scoped);
    }
    Ok((aliases, scoped))
}

/// Python's `_polyglot_table_payload_alias_and_name`.
fn table_alias_and_name(table: &Value) -> (String, String) {
    let table_name: String = raw_name_payload(table.get("name"));
    let alias: String = raw_name_payload(table.get("alias"));
    (
        if alias.is_empty() {
            table_name.clone()
        } else {
            alias
        },
        table_name,
    )
}

/// Python's `_copy_table_facts_to_alias`.
fn copy_facts_to_alias(alias: &str, table_name: &str, mut scoped: NullRelations) -> NullRelations {
    if alias == table_name || dict_get(&scoped, alias).is_some() {
        return scoped;
    }
    if let Some(facts) = dict_get(&scoped, table_name).cloned() {
        scoped.push((alias.to_owned(), facts));
    }
    scoped
}

fn has_known_nullability(facts: &[(String, &'static str)]) -> bool {
    facts.iter().any(|(_, value)| *value != UNKNOWN_NULLABILITY)
}

/// Python's `_polyglot_non_null_filter_context`.
fn filter_context(select: &Expression, nullability: &NullRelations) -> Fact<Option<FilterContext>> {
    let Some(clause) = where_clause(select)? else {
        return Ok(None);
    };
    let Some(clause) = clause.as_object() else {
        return Ok(None);
    };
    let references: Vec<(String, String)> = non_null_conjuncts(clause.get("this"));
    if references.is_empty() {
        return Ok(None);
    }
    let mut relations: Vec<(String, NullShape)> = Vec::new();
    for table in direct_tables(select) {
        let table_name: &str = table.get_name();
        let alias: &str = alias_or_name(table);
        if let Some(columns) = ci_get(nullability, table_name) {
            let key: &str = if alias.is_empty() { table_name } else { alias };
            relations.push((key.to_owned(), Rc::clone(columns)));
        }
    }
    let columns: HashSet<(String, String)> = references
        .iter()
        .filter_map(|reference| resolved_column(reference, &relations))
        .collect();
    Ok((!columns.is_empty()).then_some((relations, columns)))
}

/// Python's `_polyglot_non_null_conjuncts`.
fn non_null_conjuncts(payload: Option<&Value>) -> Vec<(String, String)> {
    let Some(payload) = payload.and_then(Value::as_object) else {
        return Vec::new();
    };
    if let Some(paren) = payload.get("paren").and_then(Value::as_object) {
        return non_null_conjuncts(paren.get("this"));
    }
    if let Some(and) = payload.get("and").and_then(Value::as_object) {
        let mut references: Vec<(String, String)> = non_null_conjuncts(and.get("left"));
        references.extend(non_null_conjuncts(and.get("right")));
        return references;
    }
    let Some(is_null) = payload.get(IS_NULL_AST_KIND).and_then(Value::as_object) else {
        return Vec::new();
    };
    if is_null.is_empty() || is_null.get("not") != Some(&Value::Bool(true)) {
        return Vec::new();
    }
    let Some(column) = is_null
        .get("this")
        .and_then(Value::as_object)
        .and_then(|this| this.get(COLUMN_AST_KIND))
        .and_then(Value::as_object)
    else {
        return Vec::new();
    };
    let column_name: String = raw_name_payload(column.get("name"));
    let table_name: String = raw_name_payload(column.get("table"));
    if column_name.is_empty() {
        return Vec::new();
    }
    vec![(table_name, column_name)]
}

/// Python's `_polyglot_resolved_relation_column`.
fn resolved_column(
    reference: &(String, String),
    relations: &[(String, NullShape)],
) -> Option<(String, String)> {
    let (table_name, column_name) = reference;
    let matching: Vec<(String, String)> = relations
        .iter()
        .filter(|(alias, _)| table_name.is_empty() || casefold(alias) == casefold(table_name))
        .filter_map(|(alias, columns)| folded_column(alias, columns, column_name))
        .collect();
    match <[(String, String); 1]>::try_from(matching) {
        Ok([only]) => Some(only),
        Err(_) => None,
    }
}

fn folded_column(alias: &str, columns: &NullShape, column_name: &str) -> Option<(String, String)> {
    let key: &str = ci_key(columns, column_name)?;
    Some((casefold(alias), casefold(key)))
}

/// Python's `_polyglot_expression_is_non_null_after_filter`.
fn non_null_after_filter(
    expression: Option<&Expression>,
    context: Option<&FilterContext>,
) -> Fact<bool> {
    let Some((relations, columns)) = context else {
        return Ok(false);
    };
    let Some(reference) = direct_column_reference(expression)? else {
        return Ok(false);
    };
    Ok(resolved_column(&reference, relations).is_some_and(|resolved| columns.contains(&resolved)))
}

/// Python's `_polyglot_direct_column_reference`.
fn direct_column_reference(expression: Option<&Expression>) -> Fact<Option<(String, String)>> {
    let mut expression: Option<&Expression> = unwrap_annotations(expression);
    if kind(expression) == CAST_AST_KIND {
        expression = unwrap_annotations(expression.and_then(Expression::get_this));
    }
    if kind(expression) != COLUMN_AST_KIND {
        return Ok(None);
    }
    let column_name: &str = name(expression);
    if column_name.is_empty() {
        return Ok(None);
    }
    let table_name: String = name_payload(arg(expression, "table")?.as_ref());
    Ok(Some((table_name, column_name.to_owned())))
}

/// Python's `_polyglot_filtered_non_null_outputs` once its filter test passed.
fn filtered_non_null(root: &Expression, nullability: &NullRelations) -> Fact<HashSet<String>> {
    let select: Option<&Expression> = if kind(Some(root)) == SELECT_AST_KIND {
        Some(root)
    } else {
        root.dfs()
            .skip(1)
            .find(|node| node.variant_name() == SELECT_AST_KIND)
    };
    let Some(select) = select else {
        return Ok(HashSet::new());
    };
    let context: Option<FilterContext> = filter_context(select, nullability)?;
    let mut outputs: HashSet<String> = HashSet::new();
    for projection in select.get_expressions() {
        let projection: Option<&Expression> = unwrap_annotations(Some(projection));
        let output: &str = output_name(projection);
        if output.is_empty() || output == WILDCARD {
            continue;
        }
        if non_null_after_filter(projected_expression(projection), context.as_ref())? {
            outputs.insert(output.to_owned());
        }
    }
    Ok(outputs)
}

/// Python's `_polyglot_referenced_relation_facts`.
fn referenced_facts<V: Clone>(root: &Expression, facts: &[(String, V)]) -> Vec<(String, V)> {
    let mut referenced: Vec<(String, V)> = Vec::new();
    for table in find_all(root, TABLE_AST_KIND) {
        let table_name: &str = table.get_name();
        if let Some(column_facts) = dict_get(facts, table_name) {
            referenced = dict_set(referenced, table_name, column_facts.clone());
        }
    }
    referenced
}

/// Python's `_polyglot_direct_column_type`.
fn direct_column_type(column: &Expression, by_alias: &Relations) -> Fact<Option<String>> {
    let column_name: &str = column.get_name();
    let table_name: String = column_table_name(column)?;
    if !table_name.is_empty() {
        return Ok(ci_get(by_alias, &table_name)
            .and_then(|column_types| ci_get(column_types, column_name))
            .cloned());
    }
    let matching: Vec<&String> = distinct_shapes(by_alias)
        .into_iter()
        .filter_map(|column_types| ci_get(column_types, column_name))
        .collect();
    Ok(match matching.as_slice() {
        [only] => Some((*only).clone()),
        _ => None,
    })
}

/// The relations of `by_alias` in order, each `Rc` once, as Python's `id()` dedup keeps them.
fn distinct_shapes(by_alias: &Relations) -> Vec<&Shape> {
    let mut distinct: Vec<&Shape> = Vec::new();
    for (_, shape) in by_alias {
        if !distinct.iter().any(|seen| Rc::ptr_eq(seen, shape)) {
            distinct.push(shape);
        }
    }
    distinct
}

/// Python's `_polyglot_star_output_types`.
fn star_types(star: &Expression, by_alias: &Relations) -> Fact<Vec<(String, String)>> {
    if py_truthy(arg(Some(star), "rename")?.as_ref()) {
        return Ok(Vec::new());
    }
    let table_name: String = name_payload(arg(Some(star), "table")?.as_ref());
    let sources: Vec<&Shape> = if table_name.is_empty() {
        distinct_shapes(by_alias)
    } else {
        ci_get(by_alias, &table_name).into_iter().collect()
    };
    let excluded: HashSet<String> = listed_names(arg(Some(star), "except")?, false)?;
    let replaced: HashSet<String> = listed_names(arg(Some(star), "replace")?, true)?;
    let mut inferred: Vec<(String, String)> = Vec::new();
    let mut ambiguous: Vec<String> = Vec::new();
    for column_types in sources {
        for (column_name, column_type) in column_types.iter() {
            let folded: String = casefold(column_name);
            if excluded.contains(&folded) || replaced.contains(&folded) {
                continue;
            }
            if let Some((existing, _)) = inferred.iter().find(|(name, _)| casefold(name) == folded)
            {
                ambiguous.push(existing.clone());
                continue;
            }
            inferred.push((column_name.clone(), column_type.clone()));
        }
    }
    inferred.retain(|(name, _)| !ambiguous.contains(name));
    Ok(inferred)
}

/// The folded names of a star's `except` list, or of its `replace` aliases.
fn listed_names(value: Option<PyValue>, aliases: bool) -> Fact<HashSet<String>> {
    let items: Vec<Value> = match value {
        None => Vec::new(),
        Some(PyValue::Exprs(_)) => return Ok(HashSet::new()),
        Some(PyValue::Raw(Value::Array(items))) => items,
        Some(PyValue::Raw(raw)) if !py_truthy(Some(&PyValue::Raw(raw.clone()))) => Vec::new(),
        Some(_) => return Err("a star modifier Python iterates unusually".to_owned()),
    };
    Ok(items
        .iter()
        .filter(|item| !aliases || item.is_object())
        .map(|item| match aliases {
            true => raw_name_payload(item.get("alias")),
            false => raw_name_payload(Some(item)),
        })
        .filter(|name| !name.is_empty())
        .map(|name| casefold(&name))
        .collect())
}

/// Whether `node` is a literal whose `literal_type` arg is Python's `"string"`.
fn string_literal(node: &Expression) -> Fact<bool> {
    if node.variant_name() != LITERAL_AST_KIND {
        return Ok(false);
    }
    Ok(matches!(
        arg(Some(node), "literal_type")?,
        Some(PyValue::Raw(Value::String(literal_type))) if literal_type == STRING_LITERAL_TYPE
    ))
}

/// Python's `_polyglot_result_expressions`; None stands for a value that is not an expression.
fn result_expressions(node: &Expression) -> Fact<Vec<Option<Expression>>> {
    let node_kind: &str = node.variant_name();
    if node_kind == COALESCE_AST_KIND {
        return Ok(match arg(Some(node), "expressions")? {
            Some(PyValue::Exprs(values)) => values.into_iter().map(Some).collect(),
            Some(PyValue::Raw(Value::Array(values))) => values.iter().map(|_| None).collect(),
            _ => Vec::new(),
        });
    }
    if node_kind == IF_FUNC_AST_KIND {
        let mut values: Vec<Option<Expression>> = Vec::new();
        for key in ["true_value", "false_value"] {
            if let Some(value) = arg(Some(node), key)? {
                values.push(expression_value(value));
            }
        }
        return Ok(values);
    }
    if node_kind == CASE_AST_KIND {
        return case_results(node);
    }
    if node_kind == FUNCTION_AST_KIND && upper(node.get_name()) == NULLIF_FUNCTION_NAME {
        return Ok(match arg(Some(node), "args")? {
            Some(PyValue::Exprs(mut values)) if !values.is_empty() => {
                vec![Some(values.swap_remove(0))]
            }
            Some(PyValue::Raw(Value::Array(values))) if !values.is_empty() => vec![None],
            _ => Vec::new(),
        });
    }

    Ok(Vec::new())
}

fn expression_value(value: PyValue) -> Option<Expression> {
    match value {
        PyValue::Expr(expression) => Some(expression),
        _ => None,
    }
}

/// CASE's result branches by child position, as Python indexes `children()`.
fn case_results(node: &Expression) -> Fact<Vec<Option<Expression>>> {
    let node_children: Vec<&Expression> = children(node);
    let mut values: Vec<Option<Expression>> = Vec::new();
    let when_count: Option<usize> = match arg(Some(node), "whens")? {
        Some(PyValue::Exprs(whens)) => Some(whens.len()),
        Some(PyValue::Raw(Value::Array(whens))) => Some(whens.len()),
        _ => None,
    };
    if let Some(when_count) = when_count {
        let first: usize = usize::from(arg(Some(node), "operand")?.is_some());
        for index in 0..when_count {
            let child: &Expression = node_children
                .get(first + index * 2 + 1)
                .ok_or("Python indexes past CASE's children")?;
            values.push(Some(child.clone()));
        }
    }
    if arg(Some(node), "else_")?.is_some()
        && let Some(last) = node_children.last()
    {
        values.push(Some((*last).clone()));
    }
    Ok(values)
}

/// Python's cast-target rendering in `_polyglot_expression_type`.
fn cast_target_type(target: &Map<String, Value>) -> Option<String> {
    let raw_type: &str = target
        .get("data_type")
        .and_then(Value::as_str)
        .filter(|raw| !raw.is_empty())?;
    if upper(raw_type) == CUSTOM_TYPE_NAME
        && let Some(custom) = target
            .get("name")
            .and_then(Value::as_str)
            .filter(|custom| !custom.is_empty())
    {
        return Some(upper(custom));
    }
    let lower: String = casefold(raw_type);
    if lower == TIMESTAMP_TYPE_NAME && target.get("timezone") == Some(&Value::Bool(true)) {
        return Some(TIMESTAMP_TZ_TYPE.to_owned());
    }
    let type_name: String = POLYGLOT_TYPE_NAMES
        .iter()
        .find(|(raw, _)| *raw == raw_type)
        .map_or_else(
            || upper(&raw_type.replace('_', " ")),
            |(_, rendered)| (*rendered).to_owned(),
        );
    if VARCHAR_DATA_TYPES.contains(&lower.as_str())
        && let Some(length) = python_int(target.get("length"))
    {
        return Some(format!("VARCHAR({length})"));
    }
    if type_name == DECIMAL_TYPE
        && let Some(precision) = python_int(target.get("precision"))
    {
        return Some(match python_int(target.get("scale")) {
            Some(scale) => format!("DECIMAL({precision}, {scale})"),
            None => format!("DECIMAL({precision})"),
        });
    }
    Some(type_name)
}

/// Python's `str.casefold`, exact for ASCII; non-ASCII text marks the recovery deferred.
fn casefold(text: &str) -> String {
    flag_non_ascii(text);
    text.to_ascii_lowercase()
}

/// Python's `str.upper`, exact for ASCII; non-ASCII text marks the recovery deferred.
fn upper(text: &str) -> String {
    flag_non_ascii(text);
    text.to_ascii_uppercase()
}

fn flag_non_ascii(text: &str) {
    if !text.is_ascii() {
        NON_ASCII_FOLDED.set(true);
    }
}

fn dict_get<'a, V>(dict: &'a [(String, V)], key: &str) -> Option<&'a V> {
    dict.iter()
        .find(|(candidate, _)| candidate == key)
        .map(|(_, value)| value)
}

/// Python's `dict[key] = value`: replace in place, otherwise append.
fn dict_set<V>(mut dict: Vec<(String, V)>, key: &str, value: V) -> Vec<(String, V)> {
    match dict.iter_mut().find(|(candidate, _)| candidate == key) {
        Some((_, existing)) => *existing = value,
        None => dict.push((key.to_owned(), value)),
    }
    dict
}

/// Python's `_case_insensitive_mapping_get` over values that are never None.
fn ci_get<'a, V>(dict: &'a [(String, V)], key: &str) -> Option<&'a V> {
    if let Some(direct) = dict_get(dict, key) {
        return Some(direct);
    }
    unique_folded(dict, key)
}

/// Python's `_case_insensitive_mapping_get` over values that may be None.
fn ci_get_optional<'a>(dict: &'a [(String, Option<String>)], key: &str) -> Option<&'a str> {
    if let Some(Some(direct)) = dict_get(dict, key) {
        return Some(direct);
    }
    unique_folded(dict, key).and_then(Option::as_deref)
}

fn unique_folded<'a, V>(dict: &'a [(String, V)], key: &str) -> Option<&'a V> {
    let folded: String = casefold(key);
    let matches: Vec<&V> = dict
        .iter()
        .filter(|(candidate, _)| casefold(candidate) == folded)
        .map(|(_, value)| value)
        .collect();
    match matches.as_slice() {
        [only] => Some(only),
        _ => None,
    }
}

/// Python's `_case_insensitive_mapping_key`.
fn ci_key<'a, V>(dict: &'a [(String, V)], key: &str) -> Option<&'a str> {
    if let Some((candidate, _)) = dict.iter().find(|(candidate, _)| candidate == key) {
        return Some(candidate);
    }
    let folded: String = casefold(key);
    let matches: Vec<&str> = dict
        .iter()
        .filter(|(candidate, _)| casefold(candidate) == folded)
        .map(|(candidate, _)| candidate.as_str())
        .collect();
    match matches.as_slice() {
        [only] => Some(only),
        _ => None,
    }
}
