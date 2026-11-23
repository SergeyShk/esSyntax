//! Python module `essyntax._essyntax`

use std::hash::{DefaultHasher, Hash, Hasher};
use std::io::ErrorKind;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock, Weak};
use std::time::SystemTime;

use pyo3::exceptions::{PyOSError, PyOverflowError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyMapping, PyString, PyTuple};
use pyo3::{IntoPyObjectExt, intern};

/// The model of the package: the weights `data/es-syntax.bin` (CC BY-SA 4.0, LICENSE-MODEL.txt)
/// are embedded in the module
static MODEL: &[u8] = include_bytes!("../../../data/es-syntax.bin");
/// Sentences parsed without the GIL between the checks of Ctrl+C
const CHUNK: usize = 256;
/// The UD parts of speech: the model does not know others and parses them badly
const UPOS: [&str; 17] = [
    "ADJ", "ADP", "ADV", "AUX", "CCONJ", "DET", "INTJ", "NOUN", "NUM", "PART", "PRON", "PROPN",
    "PUNCT", "SCONJ", "SYM", "VERB", "X",
];

/// Version of the crate as PEP 440 writes it: `0.1.0-dev.12` is `0.1.0.dev12`
fn package_version() -> String {
    env!("CARGO_PKG_VERSION").replace("-dev.", ".dev")
}

/// The model of the package is loaded once per process and shared by all parsers
fn bundled() -> PyResult<Arc<essyntax::Parser>> {
    static PARSER: OnceLock<Arc<essyntax::Parser>> = OnceLock::new();
    if let Some(parser) = PARSER.get() {
        return Ok(parser.clone());
    }
    let parser = essyntax::Parser::from_bytes(MODEL)
        .map_err(|err| PyValueError::new_err(format!("the model of the package: {err}")))?;
    let parser = Arc::new(parser);
    Ok(PARSER.get_or_init(|| parser).clone())
}

/// The model file: on Unix the device and the number of the file, which a hard link, a symbolic
/// link and another path to the same file do not change; on other systems the canonical path
#[cfg(unix)]
type FileId = (u64, u64);
#[cfg(not(unix))]
type FileId = PathBuf;

#[cfg(unix)]
fn file_id(_path: &Path, meta: &std::fs::Metadata) -> Option<FileId> {
    use std::os::unix::fs::MetadataExt;
    Some((meta.dev(), meta.ino()))
}

#[cfg(not(unix))]
fn file_id(path: &Path, _meta: &std::fs::Metadata) -> Option<FileId> {
    std::fs::canonicalize(path).ok()
}

/// The model file and its state: `FileId`, the size and the time of the change
type FileKey = (FileId, u64, Option<SystemTime>);

/// The key of the file `path`; `None` if it is not a regular file or has no metadata
fn file_key(path: &Path) -> Option<FileKey> {
    let meta = std::fs::metadata(path)
        .ok()
        .filter(std::fs::Metadata::is_file)?;
    Some((file_id(path, &meta)?, meta.len(), meta.modified().ok()))
}

/// A model from a file in the list of the loaded ones
struct Loaded {
    key: FileKey,
    parser: Weak<essyntax::Parser>,
}

/// Models loaded in the process: parsers of one file and copies from pickle share the model, and
/// the last loaded one is kept without parsers too (a parser in a loop or in the tasks of a pool
/// does not read the file again). The list is taken only with `try_lock` and only to look up and
/// to add: if a thread that is gone after fork holds it, the model is just loaded anew
struct Cache {
    loaded: Vec<Loaded>,
    last: Option<Arc<essyntax::Parser>>,
}

static LOADED: Mutex<Cache> = Mutex::new(Cache {
    loaded: Vec::new(),
    last: None,
});

/// The model of the file `path`: the one loaded in the process if the file is the same and has not
/// changed, otherwise a new one
fn load(path: &Path, key: Option<&FileKey>) -> Result<Arc<essyntax::Parser>, essyntax::Error> {
    if let Some(key) = key
        && let Ok(cache) = LOADED.try_lock()
        && let Some(parser) = (cache.loaded.iter())
            .filter(|entry| entry.key == *key)
            .find_map(|entry| entry.parser.upgrade())
    {
        return Ok(parser);
    }
    let parser = Arc::new(essyntax::Parser::from_path(path)?);
    if let Some(key) = key
        && let Ok(mut cache) = LOADED.try_lock()
    {
        (cache.loaded).retain(|entry| entry.parser.strong_count() > 0 && entry.key.0 != key.0);
        cache.loaded.push(Loaded {
            key: key.to_owned(),
            parser: Arc::downgrade(&parser),
        });
        cache.last = Some(parser.clone());
    }
    Ok(parser)
}

/// The path to the model: a string or os.PathLike of a string; absolute, so that pickle works in
/// another working directory
fn model_path(path: &Bound<'_, PyAny>) -> PyResult<PathBuf> {
    let py = path.py();
    let wrong = |value: &Bound<'_, PyAny>| {
        type_error(
            "The path to the model must be a string or os.PathLike",
            value,
        )
    };
    let text = match (py.import(intern!(py, "os"))?).call_method1(intern!(py, "fspath"), (path,)) {
        Ok(text) => text,
        Err(err) if err.is_instance_of::<PyTypeError>(py) => return Err(wrong(path)),
        Err(err) => return Err(err),
    };
    if !text.is_instance_of::<PyString>() {
        return Err(wrong(&text));
    }
    if text.contains("\0")? {
        return Err(PyValueError::new_err(
            "The path to the model has a NUL character",
        ));
    }
    let path: PathBuf = text.extract()?;
    Ok(std::path::absolute(&path).unwrap_or(path))
}

/// An error of loading the model with the path to the file: an OSError with errno and the file name,
/// as open gives
fn load_error(path: &Path, err: essyntax::Error) -> PyErr {
    let essyntax::Error::Io(err) = err else {
        return PyValueError::new_err(format!("{}: {err}", path.display()));
    };
    let message = match err.kind() {
        ErrorKind::NotFound => "No model file".to_owned(),
        ErrorKind::PermissionDenied => "No access to the model file".to_owned(),
        ErrorKind::IsADirectory => "The path to the model is a directory".to_owned(),
        _ => err.to_string(),
    };
    let filename = path.display().to_string();
    match err.raw_os_error() {
        #[cfg(windows)]
        Some(code) => PyOSError::new_err((0, message, filename, code)),
        #[cfg(not(windows))]
        Some(errno) => PyOSError::new_err((errno, message, filename)),
        None => PyOSError::new_err(format!("{message}: {filename}")),
    }
}

/// A Rust string from a Python string; lone surrogates are replaced with U+FFFD
fn lossy(text: &Bound<'_, PyString>) -> PyResult<String> {
    if let Ok(text) = text.to_str() {
        return Ok(text.to_owned());
    }
    let encoded = text.call_method1("encode", ("utf-16-le", "surrogatepass"))?;
    let bytes = encoded.extract::<Vec<u8>>()?;
    let units: Vec<u16> = (bytes.as_chunks::<2>().0.iter())
        .map(|&pair| u16::from_le_bytes(pair))
        .collect();
    Ok(String::from_utf16_lossy(&units))
}

/// A TypeError with the type of the value: "Expected a collection of sentences, not int"
fn type_error(message: &str, value: &Bound<'_, PyAny>) -> PyErr {
    let name = value
        .get_type()
        .name()
        .map_or_else(|_| "?".into(), |name| name.to_string());
    PyTypeError::new_err(format!("{message}, not {name}"))
}

/// The strings of the items of a collection: `item(number, item)`
fn collect(
    value: &Bound<'_, PyAny>,
    what: &str,
    mut item: impl FnMut(usize, Bound<'_, PyAny>) -> PyResult<String>,
) -> PyResult<Vec<String>> {
    if value.is_instance_of::<PyString>() {
        return Err(PyTypeError::new_err(format!(
            "{what}: expected a collection of strings, not a string: pass a list"
        )));
    }
    let items = value
        .try_iter()
        .map_err(|_| type_error(&format!("{what}: expected a collection of strings"), value))?;
    (items.enumerate())
        .map(|(number, element)| item(number, element?))
        .collect()
}

fn string(item: &Bound<'_, PyAny>, what: &str, number: usize) -> PyResult<String> {
    let text = item
        .cast::<PyString>()
        .map_err(|_| type_error(&format!("{what}: item {number} must be a string"), item))?;
    lossy(text)
}

/// The strings of a collection; `none` - what replaces `None` (if `None` is allowed)
fn strings(value: &Bound<'_, PyAny>, what: &str, none: Option<&str>) -> PyResult<Vec<String>> {
    collect(value, what, |number, item| match none {
        Some(none) if item.is_none() => Ok(none.to_owned()),
        _ => string(&item, what, number),
    })
}

/// The features of the words in the CoNLL-U notation: from a string, a mapping "feature - value"
/// (as `feats` of esMorph) or `None`
fn feats(value: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    collect(value, "feats", |number, item| {
        if item.is_none() {
            return Ok("_".to_owned());
        }
        if item.is_instance_of::<PyString>() {
            return string(&item, "feats", number);
        }
        let Ok(mapping) = item.cast::<PyMapping>() else {
            return Err(type_error(
                &format!("feats: item {number} must be a string, a mapping or None"),
                &item,
            ));
        };
        let mut pairs = Vec::new();
        for pair in mapping.items()?.iter() {
            let (name, value): (Bound<'_, PyAny>, Bound<'_, PyAny>) = pair.extract()?;
            match (name.cast::<PyString>(), value.cast::<PyString>()) {
                (Ok(name), Ok(value)) => pairs.push((lossy(name)?, lossy(value)?)),
                _ => {
                    return Err(PyTypeError::new_err(format!(
                        "feats: the features of word {number} and their values must be strings"
                    )));
                }
            }
        }
        if pairs.is_empty() {
            return Ok("_".to_owned());
        }
        // As in CoNLL-U: by the name of the feature, case aside
        pairs.sort_by_cached_key(|(name, _)| name.to_lowercase());
        let pairs: Vec<String> = (pairs.iter())
            .map(|(name, value)| format!("{name}={value}"))
            .collect();
        Ok(pairs.join("|"))
    })
}

/// A flag argument: bool (and numpy.bool_), otherwise a TypeError
fn flag(value: Option<&Bound<'_, PyAny>>, name: &str) -> PyResult<bool> {
    value.map_or(Ok(false), |value| {
        (value.extract::<bool>()).map_err(|_| type_error(&format!("{name} must be a bool"), value))
    })
}

/// " of sentence 3" - the number of the sentence in an error message of `parse_many`
fn of_sentence(sentence: Option<usize>) -> String {
    sentence.map_or_else(String::new, |number| format!(" of sentence {number}"))
}

/// Every part of speech is one of the 17 UD parts of speech in capitals; `sentence` - the number of
/// the sentence in `parse_many`
fn check_upos(upos: &[String], sentence: Option<usize>) -> PyResult<()> {
    match upos.iter().position(|tag| !UPOS.contains(&tag.as_str())) {
        None => Ok(()),
        Some(at) => Err(PyValueError::new_err(format!(
            "upos: unknown part of speech '{}' of word {at}{}: expected one of the 17 UD parts of \
             speech in capitals ({})",
            upos[at],
            of_sentence(sentence),
            UPOS.join(", ")
        ))),
    }
}

/// The words of one sentence: forms, parts of speech and features of one length
type Sentence = (Vec<String>, Vec<String>, Vec<String>);

/// The words of a sentence; `number` - the number of the sentence in `parse_many` for error messages
fn sentence(
    words: &Bound<'_, PyAny>,
    upos: &Bound<'_, PyAny>,
    feats: &Bound<'_, PyAny>,
    number: Option<usize>,
) -> PyResult<Sentence> {
    let words = strings(words, "words", None)?;
    let upos = strings(upos, "upos", None)?;
    let feats = self::feats(feats)?;
    if upos.len() != words.len() || feats.len() != words.len() {
        return Err(PyValueError::new_err(format!(
            "Every word{} must have a part of speech and features: {} words, {} parts of speech, \
             {} features",
            of_sentence(number),
            words.len(),
            upos.len(),
            feats.len()
        )));
    }
    check_upos(&upos, number)?;
    Ok((words, upos, feats))
}

/// Parsing of sentences without the GIL in chunks of `CHUNK`: Ctrl+C works between them. The output
/// is the head and the number of the relation of every word
fn parse_all<'p>(
    py: Python<'_>,
    parser: &'p essyntax::Parser,
    sentences: &[Sentence],
) -> PyResult<Vec<Vec<essyntax::Relation<'p>>>> {
    let mut out = Vec::with_capacity(sentences.len());
    for chunk in sentences.chunks(CHUNK) {
        let parsed = py.detach(|| {
            let words: Vec<Vec<essyntax::Word<'_>>> = chunk
                .iter()
                .map(|(forms, upos, feats)| {
                    (forms.iter().zip(upos).zip(feats))
                        .map(|((form, upos), feats)| essyntax::Word::new(form, upos, feats))
                        .collect()
                })
                .collect();
            parser.parse_many(&words)
        });
        out.extend(parsed);
        py.check_signals()?;
    }
    Ok(out)
}

/// The object is a document by the protocol of anySeg
fn is_document(value: &Bound<'_, PyAny>) -> PyResult<bool> {
    let py = value.py();
    for name in [
        intern!(py, "column"),
        intern!(py, "sentences"),
        intern!(py, "set_columns"),
    ] {
        if !value.hasattr(name)? {
            return Ok(false);
        }
    }
    Ok(true)
}

/// Dependency parser of Spanish
///
/// Description:
///     Finds the head (the number of a word from 1, 0 for the root) and the Universal
///     Dependencies relation of every word of a sentence. The input is words with their UD part
///     of speech and features (as esMorph gives them); parse_text goes from text (anySeg and
///     esMorph). Without path - the model of the package, trained on the UD treebanks AnCora
///     and GSD (CC BY-SA 4.0). Parsing does not change the parser: it can be shared between
///     threads
///
/// Arguments:
///     path (str | os.PathLike | None): esSyntax model file; None - the model of the package.
///         Parsers of one file share the loaded model
///
/// Raises:
///     OSError: If the model file cannot be read
///     ValueError: If the file is not an esSyntax model, has another format version or is damaged
///     TypeError: If the path is neither a string nor os.PathLike
///
/// Example:
///     >>> from essyntax import Parser
///     >>> parser = Parser()
///     >>> parser.parse(
///     ...     ["La", "niña", "lee", "un", "libro"],
///     ...     ["DET", "NOUN", "VERB", "DET", "NOUN"],
///     ...     [
///     ...         "Definite=Def|Gender=Fem|Number=Sing|PronType=Art",
///     ...         "Gender=Fem|Number=Sing",
///     ...         "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin",
///     ...         "Definite=Ind|Gender=Masc|Number=Sing|PronType=Art",
///     ...         "Gender=Masc|Number=Sing",
///     ...     ],
///     ... )
///     [(2, 'det'), (3, 'nsubj'), (0, 'root'), (5, 'det'), (3, 'obj')]
#[pyclass(frozen, weakref, module = "essyntax")]
struct Parser {
    parser: Arc<essyntax::Parser>,
    path: Option<PathBuf>,
    /// The model file at loading, for equality: another path and links to the same file give the
    /// same key, a changed file another one; `None` - the model of the package or a file without
    /// metadata (then the path decides)
    key: Option<FileKey>,
    /// The relations of the model as Python strings: the relation of a word is not made anew
    relations: Vec<Py<PyString>>,
    /// The anySeg segmenter of parse_text: made on the first call without an own one
    segmenter: OnceLock<Py<PyAny>>,
    /// The esMorph analyzer of parse_text: made on the first call without an own one
    analyzer: OnceLock<Py<PyAny>>,
}

/// The object of `cell` or, the first time, the one `make` gives; it is made outside the cell, as
/// making runs Python code
fn kept<'py>(
    py: Python<'py>,
    cell: &OnceLock<Py<PyAny>>,
    make: impl FnOnce() -> PyResult<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    if let Some(value) = cell.get() {
        return Ok(value.bind(py).clone());
    }
    let value = make()?;
    Ok(cell.get_or_init(|| value.unbind()).bind(py).clone())
}

impl Parser {
    fn segmenter<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        kept(py, &self.segmenter, || {
            py.import("anyseg")?.getattr("Segmenter")?.call1(("es",))
        })
    }

    fn analyzer<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        kept(py, &self.analyzer, || {
            py.import("esmorph")?.getattr("Analyzer")?.call0()
        })
    }

    /// The relations of a sentence for Python: the head and the relation, with `probs` also their
    /// probabilities
    fn named<'py>(
        &self,
        py: Python<'py>,
        relations: &[essyntax::Relation<'_>],
        probs: bool,
    ) -> PyResult<Bound<'py, PyList>> {
        let items = relations.iter().map(|relation| {
            let deprel = self.relations[relation.label].clone_ref(py);
            if probs {
                let (head_prob, deprel_prob) = (relation.head_prob, relation.deprel_prob);
                (
                    relation.head,
                    deprel,
                    f64::from(head_prob),
                    f64::from(deprel_prob),
                )
                    .into_bound_py_any(py)
            } else {
                (relation.head, deprel).into_bound_py_any(py)
            }
        });
        PyList::new(py, items.collect::<PyResult<Vec<_>>>()?)
    }
}

#[pymethods]
impl Parser {
    #[new]
    #[pyo3(signature = (path = None))]
    fn new(py: Python<'_>, path: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        let path = path.map(model_path).transpose()?;
        let key = path.as_deref().and_then(file_key);
        let parser = match &path {
            None => bundled()?,
            Some(path) => py
                .detach(|| load(path, key.as_ref()))
                .map_err(|err| load_error(path, err))?,
        };
        let relations = (parser.relations().iter())
            .map(|relation| PyString::new(py, relation).unbind())
            .collect();
        Ok(Parser {
            parser,
            path,
            key,
            relations,
            segmenter: OnceLock::new(),
            analyzer: OnceLock::new(),
        })
    }

    /// Parsers are equal if their model comes from one file (or both are the model of the package)
    fn __eq__(&self, other: PyRef<'_, Self>) -> bool {
        match (&self.key, &other.key) {
            (Some(key), Some(other)) => key == other,
            _ => self.path == other.path,
        }
    }

    fn __hash__(&self) -> u64 {
        let mut hasher = DefaultHasher::new();
        match &self.key {
            Some(key) => key.hash(&mut hasher),
            None => self.path.hash(&mut hasher),
        }
        hasher.finish()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        match &self.path {
            None => Ok("Parser()".to_owned()),
            Some(path) => Ok(format!(
                "Parser({})",
                PyString::new(py, &path.to_string_lossy()).repr()?
            )),
        }
    }

    fn __copy__(slf: Bound<'_, Self>) -> Bound<'_, Self> {
        slf
    }

    fn __deepcopy__<'py>(slf: Bound<'py, Self>, _memo: &Bound<'py, PyAny>) -> Bound<'py, Self> {
        slf
    }

    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>)> {
        let py = slf.py();
        let args = PyTuple::new(py, [slf.get().path.clone().into_bound_py_any(py)?])?;
        Ok((slf.get_type().into_any(), args))
    }

    /// The absolute path to the model file; None - the model of the package
    #[getter]
    fn path(&self) -> Option<PathBuf> {
        self.path.clone()
    }

    /// The relations the model gives
    #[getter]
    fn relations(&self) -> Vec<String> {
        self.parser.relations().to_vec()
    }

    /// Description of the model: the checksum crc32 (it tells one model from another) and the
    /// description of the training from the file - the UD release, the treebanks, the LAS on dev
    /// and so on
    #[getter]
    fn sources<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let sources = match self.parser.sources() {
            Some(text) => py
                .import("json")?
                .call_method1("loads", (text,))?
                .cast_into::<PyDict>()
                .map_err(|_| {
                    PyValueError::new_err("the description of the training is not a JSON object")
                })?,
            None => PyDict::new(py),
        };
        sources.set_item("crc32", format!("{:08x}", self.parser.checksum()))?;
        Ok(sources)
    }

    /// Parsing of a sentence
    ///
    /// Description:
    ///     The head and the relation of every word in the same order; an empty sentence gives an
    ///     empty list. The parts of speech and the features are UD tags, as esMorph gives them;
    ///     features unknown to the model are skipped. Parsing goes without the GIL
    ///
    /// Arguments:
    ///     words (Iterable[str]): The forms of the words
    ///     upos (Iterable[str]): UD parts of speech - one of the 17, in capitals
    ///     feats (Iterable[str | Mapping[str, str] | None]): Features in the CoNLL-U notation
    ///         (Gender=Fem|Number=Sing) or a mapping, as feats of esMorph; `_`, an empty string,
    ///         an empty mapping and None are no features
    ///     probs (bool): Add the probabilities of the head and the relation by the model
    ///
    /// Returns:
    ///     list[tuple[int, str]]: The number of the head (0 for the root) and the relation of every
    ///         word; with probs, quadruples: also the probability of the head among all the words
    ///         of the sentence and the root (in sentences longer than 1024 words, among 64 words on
    ///         each side, the root and the head given by the assembly of the tree) and the
    ///         probability of the relation with this head among the relations except root (1 for
    ///         root, which a rule gives to the word with head 0)
    ///
    /// Raises:
    ///     ValueError: If the lengths of words, upos and feats differ or a part of speech is not
    ///         one of the 17 UD parts of speech
    ///     TypeError: If an input is not a collection of strings or probs is not a bool
    ///
    /// Example:
    ///     >>> parser = Parser()
    ///     >>> parser.parse(["¡", "Hola", "!"], ["PUNCT", "INTJ", "PUNCT"], [None, None, None])
    ///     [(2, 'punct'), (0, 'root'), (2, 'punct')]
    ///     >>> [(head, deprel, round(p, 1), round(q, 1)) for head, deprel, p, q in
    ///     ...  parser.parse(["¡", "Hola", "!"], ["PUNCT", "INTJ", "PUNCT"], [None, None, None], probs=True)]
    ///     [(2, 'punct', 1.0, 1.0), (0, 'root', 1.0, 1.0), (2, 'punct', 1.0, 1.0)]
    #[pyo3(
        signature = (words, upos, feats, *, probs = None),
        text_signature = "($self, words, upos, feats, *, probs=False)"
    )]
    fn parse<'py>(
        &self,
        py: Python<'py>,
        words: &Bound<'py, PyAny>,
        upos: &Bound<'py, PyAny>,
        feats: &Bound<'py, PyAny>,
        probs: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyList>> {
        let probs = flag(probs, "probs")?;
        let sentence = sentence(words, upos, feats, None)?;
        let relations = parse_all(py, &self.parser, &[sentence])?;
        self.named(py, relations.first().map_or(&[], Vec::as_slice), probs)
    }

    /// Parsing of several sentences
    ///
    /// Description:
    ///     The same as parse for every sentence, but faster: sentences of close length are
    ///     parsed four at once. Parsing goes without the GIL
    ///
    /// Arguments:
    ///     sentences (Iterable[tuple[Iterable[str], Iterable[str], Iterable[str | Mapping[str, str] | None]]]):
    ///         Sentences - triples (forms, parts of speech, features), as parse takes them
    ///     probs (bool): Add the probabilities of the head and the relation, as parse does
    ///
    /// Returns:
    ///     list[list[tuple[int, str]]]: The heads and the relations of every sentence; with probs,
    ///         quadruples, as parse gives them
    ///
    /// Raises:
    ///     ValueError: If a sentence is not three collections, their lengths differ or a part of
    ///         speech is not one of the 17 UD parts of speech
    ///     TypeError: If an input is not a collection of strings or probs is not a bool
    ///
    /// Example:
    ///     >>> Parser().parse_many([(["¡", "Hola", "!"], ["PUNCT", "INTJ", "PUNCT"], ["_", "_", "_"])])
    ///     [[(2, 'punct'), (0, 'root'), (2, 'punct')]]
    #[pyo3(
        signature = (sentences, *, probs = None),
        text_signature = "($self, sentences, *, probs=False)"
    )]
    fn parse_many<'py>(
        &self,
        py: Python<'py>,
        sentences: &Bound<'py, PyAny>,
        probs: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Vec<Bound<'py, PyList>>> {
        let probs = flag(probs, "probs")?;
        let items = sentences
            .try_iter()
            .map_err(|_| type_error("Expected a collection of sentences", sentences))?;
        let mut parsed = Vec::new();
        for (number, item) in items.enumerate() {
            let item = item?;
            let parts: Vec<Bound<'_, PyAny>> = match item.try_iter() {
                Ok(parts) if !item.is_instance_of::<PyString>() => {
                    parts.collect::<PyResult<_>>()?
                }
                _ => {
                    return Err(type_error(
                        &format!("Sentence {number} must be a triple"),
                        &item,
                    ));
                }
            };
            let [words, upos, feats] = parts.as_slice() else {
                return Err(PyValueError::new_err(format!(
                    "Sentence {number}: expected a triple (forms, parts of speech, features), got \
                     {} items",
                    parts.len()
                )));
            };
            parsed.push(sentence(words, upos, feats, Some(number))?);
        }
        (parse_all(py, &self.parser, &parsed)?.iter())
            .map(|relations| self.named(py, relations, probs))
            .collect()
    }

    /// Parsing of a document of the anySeg segmenter
    ///
    /// Description:
    ///     Fills the columns head and deprel of the words of the document; the earlier values are
    ///     replaced. The parts of speech and the features come from the columns upos and feats:
    ///     the document must have its morphology, for example from esmorph.Analyzer().annotate,
    ///     which returns the document with the words of the tokens it splits. The words of
    ///     multiword tokens are parsed as the other words. The document is an anyseg.Document or
    ///     an object with the same column, sentences (a sentence has words, a word has index)
    ///     and set_columns. The enhanced graph (the column deps) and empty nodes do not change.
    ///     Parsing goes without the GIL
    ///
    /// Arguments:
    ///     document (anyseg.Document): The document
    ///
    /// Raises:
    ///     ValueError: If a word has no part of speech, a part of speech is not one of the 17 UD
    ///         parts of speech or the sentences of the document do not follow each other over all
    ///         its words
    ///     TypeError: If it is not a document, a column of the document is not of strings or the
    ///         index of a word is not an integer
    ///
    /// Example:
    ///     >>> from anyseg import Segmenter
    ///     >>> from esmorph import Analyzer
    ///     >>> document = Analyzer().annotate(Segmenter("es").segment("La niña lee un libro."))
    ///     >>> Parser().annotate(document)
    ///     >>> [(word.form, word.head, word.deprel) for word in document.words]
    ///     [('La', 2, 'det'), ('niña', 3, 'nsubj'), ('lee', 0, 'root'), ('un', 5, 'det'), ('libro', 3, 'obj'), ('.', 3, 'punct')]
    fn annotate(&self, py: Python<'_>, document: &Bound<'_, PyAny>) -> PyResult<()> {
        if document.is_instance_of::<PyString>() {
            return Err(PyTypeError::new_err(
                "Expected an anySeg document, not a string: parse_text parses text",
            ));
        }
        if !document.hasattr(intern!(py, "column"))?
            || !document.hasattr(intern!(py, "set_columns"))?
        {
            return Err(type_error(
                "Expected an anySeg document or an object with column, sentences and set_columns",
                document,
            ));
        }
        let column = |name: &str| document.call_method1(intern!(py, "column"), (name,));
        let forms = strings(&column("form")?, "form", None)?;
        // The column is read once: column may return a generator
        let upos = strings(&column("upos")?, "upos", Some(""))?;
        if upos.iter().any(|tag| tag.is_empty() || tag == "_") {
            return Err(PyValueError::new_err(
                "The words of the document have no parts of speech: annotate it first, for \
                 example document = esmorph.Analyzer().annotate(document)",
            ));
        }
        check_upos(&upos, None)?;
        let feats = feats(&column("feats")?)?;
        if upos.len() != forms.len() || feats.len() != forms.len() {
            return Err(PyValueError::new_err(format!(
                "The columns of the document have different lengths: form {}, upos {}, feats {}",
                forms.len(),
                upos.len(),
                feats.len()
            )));
        }
        // The sentences follow each other and cover all the words
        let unordered = || {
            PyValueError::new_err(
                "The sentences of the document do not follow each other over all its words",
            )
        };
        let mut sentences = Vec::new();
        let mut next = 0;
        let all = document.getattr(intern!(py, "sentences"))?;
        let all = (all.try_iter())
            .map_err(|_| type_error("The sentences of the document must be a collection", &all))?;
        for sentence in all {
            let words = sentence?.getattr(intern!(py, "words"))?;
            let words = words
                .try_iter()
                .map_err(|_| type_error("The words of a sentence must be a collection", &words))?;
            let (mut start, mut count) = (next, 0);
            for word in words {
                if count == 0 {
                    let index = word?.getattr(intern!(py, "index"))?;
                    // An integer out of range is a number beyond the document, not a type error
                    start = match index.extract::<isize>() {
                        Ok(index) => usize::try_from(index).map_err(|_| unordered())?,
                        Err(err) if err.is_instance_of::<PyOverflowError>(py) => {
                            return Err(unordered());
                        }
                        Err(_) => {
                            return Err(type_error(
                                "The index of a word must be an integer",
                                &index,
                            ));
                        }
                    };
                }
                count += 1;
            }
            if start != next || start + count > forms.len() {
                return Err(unordered());
            }
            let range = start..start + count;
            sentences.push((
                forms[range.clone()].to_vec(),
                upos[range.clone()].to_vec(),
                feats[range].to_vec(),
            ));
            next = start + count;
        }
        if next != forms.len() {
            return Err(unordered());
        }
        let (mut heads, mut deprels) = (Vec::new(), Vec::new());
        for relations in parse_all(py, &self.parser, &sentences)? {
            for relation in relations {
                heads.push(relation.head);
                deprels.push(self.relations[relation.label].clone_ref(py));
            }
        }
        let columns = PyDict::new(py);
        columns.set_item("head", heads)?;
        columns.set_item("deprel", deprels)?;
        document.call_method(intern!(py, "set_columns"), (), Some(&columns))?;
        Ok(())
    }

    /// Parsing of a text
    ///
    /// Description:
    ///     The anySeg segmenter splits the text into sentences, tokens and their words (`del` -
    ///     `de`, `el`), esMorph gives the words their lemma, part of speech and features in
    ///     context and splits into words the tokens the segmenter leaves whole (`pónganselo` -
    ///     `pongan`, `se`, `lo`), then every word gets its head and relation (annotate); the
    ///     document keeps the multiword tokens. The default segmenter and analyzer are made on
    ///     the first call without an own one and used again; own ones - for example, with own
    ///     abbreviations or words - are given in the arguments
    ///
    /// Arguments:
    ///     text (str): The text
    ///     segmenter (anyseg.Segmenter | None): anySeg segmenter or an object with the method
    ///         segment; None - Segmenter("es")
    ///     analyzer (esmorph.Analyzer | None): esMorph morphological analyzer or an object with
    ///         the method annotate, which returns the annotated document or None if it filled the
    ///         given one; None - Analyzer()
    ///
    /// Returns:
    ///     anyseg.Document: The document with the columns lemma, upos, feats, head and deprel
    ///
    /// Raises:
    ///     TypeError: If the text is not a string, the segmenter has no segment, segment does not
    ///         return a document, the analyzer has no annotate or annotate returns something else
    ///         than a document or None
    ///     ValueError: If the analyzer did not give the words their parts of speech
    ///
    /// Example:
    ///     >>> document = Parser().parse_text("Salió del cine.")
    ///     >>> [(word.form, word.upos, word.head, word.deprel) for word in document.words]
    ///     [('Salió', 'VERB', 0, 'root'), ('de', 'ADP', 4, 'case'), ('el', 'DET', 4, 'det'), ('cine', 'NOUN', 1, 'obl'), ('.', 'PUNCT', 1, 'punct')]
    #[pyo3(signature = (text, *, segmenter = None, analyzer = None))]
    fn parse_text<'py>(
        &self,
        py: Python<'py>,
        text: &Bound<'py, PyAny>,
        segmenter: Option<Bound<'py, PyAny>>,
        analyzer: Option<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        if !text.is_instance_of::<PyString>() {
            return Err(type_error("The text must be a string", text));
        }
        for (tool, method, what) in [
            (
                &segmenter,
                "segment",
                "segmenter: expected an anySeg segmenter (with the method segment)",
            ),
            (
                &analyzer,
                "annotate",
                "analyzer: expected an esMorph analyzer (with the method annotate)",
            ),
        ] {
            if let Some(tool) = tool
                && !tool.hasattr(method)?
            {
                return Err(type_error(what, tool));
            }
        }
        let segmenter = match segmenter {
            Some(segmenter) => segmenter,
            None => self.segmenter(py)?,
        };
        let analyzer = match analyzer {
            Some(analyzer) => analyzer,
            None => self.analyzer(py)?,
        };
        let document = segmenter.call_method1(intern!(py, "segment"), (text,))?;
        if !is_document(&document)? {
            return Err(type_error(
                "segmenter: segment must return an anySeg document",
                &document,
            ));
        }
        // esMorph returns a new document when it splits a token into words
        let annotated = analyzer.call_method1(intern!(py, "annotate"), (&document,))?;
        let document = if annotated.is_none() {
            document
        } else if is_document(&annotated)? {
            annotated
        } else {
            return Err(type_error(
                "analyzer: annotate must return an anySeg document or None",
                &annotated,
            ));
        };
        self.annotate(py, &document)?;
        Ok(document)
    }
}

#[pymodule(gil_used = false)]
fn _essyntax(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", package_version())?;
    m.add_class::<Parser>()?;
    Ok(())
}
