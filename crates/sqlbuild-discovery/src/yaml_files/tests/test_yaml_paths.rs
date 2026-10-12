use crate::yaml_files::main::schema_yaml_paths::schema_yaml_paths;
use crate::yaml_files::main::source_yaml_paths::source_yaml_paths;
use crate::yaml_files::models::YamlPathFailure;
use crate::yaml_files::tests::helpers::{listed_paths, owned_paths};
use crate::yaml_files::tests::test_types::YamlPathsTestCase;

#[test]
fn given_sources_directory_when_listing_source_yaml_then_direct_yaml_children_are_sorted() {
    let test_cases = [
        YamlPathsTestCase {
            description: "yml and yaml files directly below sources/ in path order",
            files: &[
                "sources/b.yaml",
                "sources/a.yml",
                "sources/notes.txt",
                "sources/.yml",
                "sources/nested/c.yml",
            ],
            expected_paths: Ok(owned_paths(&["sources/a.yml", "sources/b.yaml"])),
        },
        YamlPathsTestCase {
            description: "no sources directory",
            files: &["models/orders.sql"],
            expected_paths: Ok(Vec::new()),
        },
    ];
    for test_case in test_cases {
        let listed = listed_paths(test_case.files, |tree| {
            source_yaml_paths(tree).map_err(YamlPathFailure::Stage)
        });
        assert_eq!(
            listed, test_case.expected_paths,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_models_and_seeds_when_listing_schema_yaml_then_unscoped_schemas_and_seed_files_are_kept() {
    let test_cases = [
        YamlPathsTestCase {
            description: "unscoped schema files then seed declarations, each in path order",
            files: &[
                "models/marts/schema.yml",
                "models/schema.yml",
                "models/marts/_sqlbuild/schemas/schema.yml",
                "models/other.yml",
                "seeds/products.yml",
                "seeds/customers/customers.yml",
            ],
            expected_paths: Ok(owned_paths(&[
                "models/marts/schema.yml",
                "models/schema.yml",
                "seeds/customers/customers.yml",
                "seeds/products.yml",
            ])),
        },
        YamlPathsTestCase {
            description: "a seed declaration using .yaml fails naming the first one",
            files: &["seeds/b.yaml", "seeds/a.yaml", "seeds/c.yml"],
            expected_paths: Err(YamlPathFailure::YamlSeedDeclaration(
                "seeds/a.yaml".to_owned(),
            )),
        },
    ];
    for test_case in test_cases {
        let listed = listed_paths(test_case.files, schema_yaml_paths);
        assert_eq!(
            listed, test_case.expected_paths,
            "{}",
            test_case.description
        );
    }
}
