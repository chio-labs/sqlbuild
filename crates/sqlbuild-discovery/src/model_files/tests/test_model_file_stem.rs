use crate::model_files::main::model_file_stem::model_file_stem;

#[test]
fn given_relative_paths_when_naming_models_then_stems_match_python() {
    let test_cases = [
        ("models/orders.sql", "orders"),
        ("models/marts/orders.v2.sql", "orders.v2"),
        ("models/.hidden", ".hidden"),
        ("orders.", "orders."),
        ("orders", "orders"),
    ];
    for (relative_path, expected) in test_cases {
        assert_eq!(model_file_stem(relative_path), expected, "{relative_path}");
    }
}
