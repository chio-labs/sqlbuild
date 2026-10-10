use crate::macro_calls::main::macro_call_names::macro_call_names;
use crate::macro_calls::models::ScanError;
use crate::macro_calls::tests::helpers::python_312;

/// `(sql, top-level names, nested names)` as Python's `_scan_sqlbuild_call_names` returned them.
type NamesCase = (
    &'static str,
    Result<&'static [&'static str], ScanError>,
    Result<&'static [&'static str], ScanError>,
);

#[test]
fn given_sql_when_listing_macro_call_names_then_python_scan_agrees() {
    let test_cases: [NamesCase; 7] = [
        ("@enum(x) @a(1)", Ok(&["enum", "a"]), Ok(&["enum", "a"])),
        ("@ab c(1)", Err(ScanError::MissingParenthesis), Ok(&["ab"])),
        ("x@\u{f6}re FROM o", Ok(&[]), Ok(&[])),
        (
            "@\u{e9}(1) @b(",
            Err(ScanError::UnclosedParenthesis),
            Ok(&["\u{e9}", "b"]),
        ),
        ("'@q()' /* @c() */ @d ( 1 ) @@v", Ok(&[]), Ok(&[])),
        ("@a(@b(@c()))", Ok(&["a"]), Ok(&["a", "b", "c"])),
        (
            "@a(\"x\") 'oops",
            Err(ScanError::UnclosedQuote),
            Err(ScanError::UnclosedQuote),
        ),
    ];
    for (sql, top_level, nested) in test_cases {
        let owned = |names: Result<&'static [&'static str], ScanError>| {
            names.map(|names| {
                names
                    .iter()
                    .map(|name| (*name).to_owned())
                    .collect::<Vec<_>>()
            })
        };
        assert_eq!(
            (
                macro_call_names(python_312(), sql, false),
                macro_call_names(python_312(), sql, true)
            ),
            (owned(top_level), owned(nested)),
            "{sql}"
        );
    }
}
