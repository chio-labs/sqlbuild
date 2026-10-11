use crate::effective::main::target_fields::target_fields;
use crate::effective::models::{FieldValue, MergeRule, TargetLayer};
use crate::effective::tests::test_types::Pairs;
use crate::effective::types::Entries;

pub(super) fn entries(pairs: Pairs) -> Entries<&'static str, i64> {
    pairs.to_vec()
}

/// A project layer: every scalar set to its field position, every map holding one entry.
pub(super) fn project_layer() -> TargetLayer<&'static str, i64> {
    TargetLayer {
        fields: target_fields()
            .iter()
            .enumerate()
            .map(|(position, field)| {
                let value: i64 = i64::try_from(position).expect("few fields");
                layer_value(field.rule, Some(value), "project")
            })
            .collect(),
    }
}

/// The field value of a rule's shape: a scalar, or a one-entry map under `key`.
fn layer_value(
    rule: MergeRule,
    value: Option<i64>,
    key: &'static str,
) -> FieldValue<&'static str, i64> {
    let shapes: [FieldValue<&'static str, i64>; 2] = [
        FieldValue::Scalar(value),
        FieldValue::Map(value.map(|value| vec![(key, value)])),
    ];
    shapes[usize::from(rule.is_map())].clone()
}

/// A local layer leaving every field unset except `set`; maps hold `("local", value)`.
pub(super) fn local_layer(set: &[(&str, i64)]) -> TargetLayer<&'static str, i64> {
    TargetLayer {
        fields: target_fields()
            .iter()
            .map(|field| {
                let value: Option<i64> = set
                    .iter()
                    .find(|(name, _)| *name == field.name)
                    .map(|(_, value)| *value);
                layer_value(field.rule, value, "local")
            })
            .collect(),
    }
}

/// The merged value of field `name`.
pub(super) fn field_value(
    layer: &TargetLayer<&'static str, i64>,
    name: &str,
) -> FieldValue<&'static str, i64> {
    let position: usize = target_fields()
        .iter()
        .position(|field| field.name == name)
        .expect("known field");
    layer.fields[position].clone()
}
