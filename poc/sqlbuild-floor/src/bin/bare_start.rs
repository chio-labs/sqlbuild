//! Bare native CLI start-up reference: print a version string and exit.

fn main() {
    println!("sqb-floor {}", env!("CARGO_PKG_VERSION"));
}
