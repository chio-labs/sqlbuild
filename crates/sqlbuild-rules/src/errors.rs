/// Why a natively built rules request produced no evaluation.
#[derive(Debug)]
pub enum RowsError {
    Rules(String),
    Io(std::io::Error),
}
