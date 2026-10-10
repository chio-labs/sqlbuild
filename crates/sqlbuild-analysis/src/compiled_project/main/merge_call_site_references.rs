/// The expanded SQL's references, then each macro argument reference once; unchanged without any.
pub fn merge_call_site_references<T: PartialEq>(references: Vec<T>, arguments: Vec<T>) -> Vec<T> {
    crate::compiled_project::_helpers::splice::merge_call_site_references(references, arguments)
}
