use std::fmt;

/// Error of loading a model
#[derive(Debug)]
#[non_exhaustive]
pub enum Error {
    /// Input or output error when reading the model file
    Io(std::io::Error),
    /// The data is not an esSyntax model or is damaged
    Format(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Io(err) => write!(f, "cannot read the model file: {err}"),
            Error::Format(msg) => write!(f, "wrong model format: {msg}"),
        }
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Error::Io(err) => Some(err),
            Error::Format(_) => None,
        }
    }
}

impl From<std::io::Error> for Error {
    fn from(err: std::io::Error) -> Self {
        Error::Io(err)
    }
}
