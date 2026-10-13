pub(crate) fn owned(value: Option<&str>) -> Option<String> {
    value.map(str::to_owned)
}
