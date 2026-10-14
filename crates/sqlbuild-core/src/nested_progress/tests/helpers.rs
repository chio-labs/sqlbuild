use crate::nested_progress::models::NestedLayout;

pub(super) fn layout(columns: usize) -> NestedLayout {
    NestedLayout {
        label: "test".to_owned(),
        name_width: 20,
        columns,
    }
}
