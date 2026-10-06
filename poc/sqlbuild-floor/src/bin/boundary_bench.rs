//! Boundary cost: Rust -> Python -> Rust per macro call, and embedded-interpreter start-up.
//!
//! Usage:
//!   boundary_bench calls [--iterations N] [--site-packages DIR]
//!   boundary_bench startup [--site-packages DIR] [--macros PROJECT_DIR] [--import-sqlbuild]
//!
//! `startup` exits right after the requested work so the process can be timed externally.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use sqlbuild_floor::median;
use std::ffi::CString;
use std::time::Instant;

const PY_BENCH: &str = r#"
import types

def identity(value):
    return value

def with_mapping(value, mapping):
    return value + mapping["k0"]

def with_ctx(ctx, value):
    return value + str(ctx.constants["c0"])

def python_loop(function, iterations, value):
    for _ in range(iterations):
        function(value)

def make_ctx(constants, variables):
    return types.SimpleNamespace(adapter_name="duckdb", target_name="dev", vars=variables,
                                 constants=constants, enums={}, sql_analysis_enabled=True)

def today_setup():
    from pathlib import Path
    from sqlbuild.compiler.compile.models import LoadedMacro, MacroContext
    from sqlbuild.compiler.compile._helpers.render.macros import expand_sql_macros_result
    def order_total(expression):
        return f"({expression} + 0)"
    macro = LoadedMacro(name="order_total", file_path=Path("macros/orders.py"),
                        relative_path=Path("macros/orders.py"), raw_source="",
                        function=order_total)
    context = MacroContext(adapter_name="duckdb", sql_analysis_enabled=True, target_name="dev",
                           vars={f"v{i}": str(i) for i in range(5)})
    loaded = {"order_total": macro}
    path = Path("models/orders.sql")
    def expand(sql):
        return expand_sql_macros_result(sql=sql, file_path=path, loaded_macros=loaded,
                                        macro_context=context).sql
    return expand
"#;

fn time_per_call(iterations: usize, mut call: impl FnMut()) -> f64 {
    let mut samples = Vec::new();
    for _ in 0..5 {
        let start = Instant::now();
        for _ in 0..iterations {
            call();
        }
        samples.push(start.elapsed().as_secs_f64() * 1e9 / iterations as f64);
    }
    median(&mut samples)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let flag = |name: &str| {
        args.iter()
            .position(|a| a == name)
            .and_then(|i| args.get(i + 1))
            .cloned()
    };
    let mode = args.get(1).cloned().unwrap_or_default();
    let start = Instant::now();
    Python::initialize();
    let init = start.elapsed().as_secs_f64();
    Python::attach(|py| -> PyResult<()> {
        if let Some(site) = flag("--site-packages") {
            py.import("site")?.call_method1("addsitedir", (site,))?;
        }
        let bench = PyModule::from_code(py, &CString::new(PY_BENCH).unwrap_or_default(), c"_bench.py", c"_bench")?;
        if mode == "startup" {
            let t = Instant::now();
            let mut loaded = 0usize;
            if args.iter().any(|a| a == "--stub-sqlbuild") {
                // What a lightweight public typing module would cost: annotation-only imports.
                py.run(
                    c"import sys, types\nfor name, attrs in (('sqlbuild', ()), ('sqlbuild.compiler', ()), ('sqlbuild.compiler.compile', ()), ('sqlbuild.compiler.compile.models', ('MacroContext',)), ('sqlbuild.refs', ('SqlResourceRef',))):\n    module = types.ModuleType(name)\n    for attr in attrs:\n        setattr(module, attr, type(attr, (), {}))\n    sys.modules[name] = module\n",
                    None,
                    None,
                )?;
            }
            if let Some(project) = flag("--macros") {
                let paths: Vec<String> = walkdir::WalkDir::new(&project)
                    .into_iter()
                    .flatten()
                    .filter(|e| {
                        let p = e.path().to_string_lossy();
                        p.ends_with(".py") && p.contains("macros") && !p.contains("/target/")
                    })
                    .map(|e| e.path().to_string_lossy().into_owned())
                    .collect();
                for (index, path) in paths.iter().enumerate() {
                    let util = py.import("importlib.util")?;
                    let name = format!("_poc_macro_{index}");
                    let spec = util.call_method1("spec_from_file_location", (&name, path))?;
                    let module = util.call_method1("module_from_spec", (&spec,))?;
                    py.import("sys")?.getattr("modules")?.set_item(&name, &module)?;
                    spec.getattr("loader")?.call_method1("exec_module", (&module,))?;
                    loaded += 1;
                }
            }
            if args.iter().any(|a| a == "--import-sqlbuild") {
                py.import("sqlbuild.compiler.compile.models")?;
                py.import("sqlbuild.compiler.compile._helpers.render.macros")?;
            }
            let modules: usize = py.import("sys")?.getattr("modules")?.len()?;
            println!(
                "startup: initialize {:.4}s, extra imports {:.4}s ({loaded} macro files), sys.modules {modules}, in-process total {:.4}s",
                init,
                t.elapsed().as_secs_f64(),
                start.elapsed().as_secs_f64()
            );
            return Ok(());
        }
        let iterations: usize = flag("--iterations").and_then(|v| v.parse().ok()).unwrap_or(200_000);
        let identity = bench.getattr("identity")?;
        let with_mapping = bench.getattr("with_mapping")?;
        let with_ctx = bench.getattr("with_ctx")?;
        let argument = "COALESCE(orders.amount, 0) + CAST(orders.id AS DOUBLE)";
        let a = time_per_call(iterations, || {
            let result = identity.call1((argument,)).and_then(|v| v.extract::<String>());
            std::hint::black_box(result.ok());
        });
        let pairs: Vec<(String, String)> = (0..5).map(|i| (format!("k{i}"), format!("value_{i}"))).collect();
        let b = time_per_call(iterations, || {
            let mapping = PyDict::new(py);
            for (k, v) in &pairs {
                let _ = mapping.set_item(k, v);
            }
            let result = with_mapping.call1((argument, mapping)).and_then(|v| v.extract::<String>());
            std::hint::black_box(result.ok());
        });
        let constants: Vec<(String, i64)> = (0..20).map(|i| (format!("c{i}"), i)).collect();
        let make_ctx = bench.getattr("make_ctx")?;
        let c = time_per_call(iterations / 4, || {
            let constant_map = PyDict::new(py);
            for (k, v) in &constants {
                let _ = constant_map.set_item(k, v);
            }
            let variables = PyDict::new(py);
            for (k, v) in &pairs {
                let _ = variables.set_item(k, v);
            }
            let ctx = make_ctx.call1((constant_map, variables));
            let result = ctx.and_then(|ctx| with_ctx.call1((ctx, argument))).and_then(|v| v.extract::<String>());
            std::hint::black_box(result.ok());
        });
        let python_loop = bench.getattr("python_loop")?;
        let e = {
            let mut samples = Vec::new();
            for _ in 0..5 {
                let t = Instant::now();
                python_loop.call1((&identity, iterations, argument))?;
                samples.push(t.elapsed().as_secs_f64() * 1e9 / iterations as f64);
            }
            median(&mut samples)
        };
        let today = bench.getattr("today_setup")?.call0();
        let d = match today {
            Ok(expand) => {
                let sql = format!("SELECT @order_total(\"{argument}\") AS total");
                time_per_call(iterations / 10, || {
                    let result = expand.call1((sql.as_str(),)).and_then(|v| v.extract::<String>());
                    std::hint::black_box(result.ok());
                })
            }
            Err(error) => {
                println!("today's path unavailable: {error}");
                f64::NAN
            }
        };
        let _ = PyTuple::empty(py);
        println!("per call (ns, median of 5 x {iterations}):");
        println!("  python->python loop, identity(str)                 {e:>9.0}");
        println!("  rust->python->rust, identity(str) -> String        {a:>9.0}");
        println!("  rust->python->rust, (str, dict[5]) -> String       {b:>9.0}");
        println!("  rust->python->rust, ctx(20 consts, 5 vars) per call {c:>9.0}");
        println!("  rust->today's expand_sql_macros_result, one call   {d:>9.0}");
        Ok(())
    })
    .expect("python");
}
