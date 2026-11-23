//! Format of the model file: a header (signature, format version, CRC32 of the rest of the file) and
//! entries by name.
//!
//! An entry is a name (u16 length and UTF-8), a kind and data, numbers little-endian. Kinds: 0 - strings,
//! 1 - a matrix of f32, 2 - a matrix of int8 by rows (an f32 scale per row), 3 - u32 numbers.

use std::collections::HashMap;

use crate::Error;
use crate::kernels::Matrix;

/// Signature of the model file
pub(crate) const MAGIC: &[u8; 8] = b"ESSYNTAX";
/// Format version the crate reads
pub(crate) const FORMAT: u32 = 1;
/// Length of the header: signature, version, CRC32
pub(crate) const HEADER: usize = 16;
const MAX_DIM: usize = 4096;
const MAX_ROWS: usize = 1 << 22;
const MAX_ENTRIES: usize = 256;

pub(crate) fn invalid(message: &str) -> Error {
    Error::Format(message.to_owned())
}

/// Value of an entry
pub(crate) enum Value<'a> {
    Strings(Vec<&'a str>),
    Matrix(Matrix),
    Numbers(Vec<u32>),
}

/// Reading with checked bounds
struct Reader<'a> {
    data: &'a [u8],
    at: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, count: usize) -> Result<&'a [u8], Error> {
        let end = self
            .at
            .checked_add(count)
            .filter(|&end| end <= self.data.len())
            .ok_or_else(|| invalid("the model file is truncated"))?;
        let bytes = &self.data[self.at..end];
        self.at = end;
        Ok(bytes)
    }

    fn u32(&mut self) -> Result<u32, Error> {
        let bytes = self.take(4)?;
        Ok(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
    }

    fn count(&mut self, limit: usize) -> Result<usize, Error> {
        let count = self.u32()? as usize;
        if count > limit {
            return Err(invalid("an entry is larger than allowed"));
        }
        Ok(count)
    }

    fn f32s(&mut self, count: usize) -> Result<Vec<f32>, Error> {
        let size = count
            .checked_mul(4)
            .ok_or_else(|| invalid("size of an entry"))?;
        let bytes = self.take(size)?;
        let values: Vec<f32> = (bytes.as_chunks::<4>().0.iter())
            .map(|&chunk| f32::from_le_bytes(chunk))
            .collect();
        if values.iter().any(|value| !value.is_finite()) {
            return Err(invalid("the weights have NaN or infinity"));
        }
        Ok(values)
    }

    fn value(&mut self) -> Result<Value<'a>, Error> {
        let kind = self.take(1)?[0];
        match kind {
            0 => {
                let count = self.count(MAX_ROWS)?;
                let mut strings = Vec::with_capacity(count.min(1 << 16));
                for _ in 0..count {
                    let len = self.count(1 << 16)?;
                    let text = std::str::from_utf8(self.take(len)?)
                        .map_err(|_| invalid("a string is not UTF-8"))?;
                    strings.push(text);
                }
                Ok(Value::Strings(strings))
            }
            1 | 2 => {
                let (rows, cols) = (self.count(MAX_ROWS)?, self.count(MAX_DIM)?);
                let size = rows
                    .checked_mul(cols)
                    .ok_or_else(|| invalid("size of an entry"))?;
                let data = if kind == 1 {
                    self.f32s(size)?
                } else {
                    let scales = self.f32s(rows)?;
                    let values = self.take(size)?;
                    let data: Vec<f32> = (values.chunks_exact(cols.max(1)).zip(&scales))
                        .flat_map(|(row, &scale)| {
                            row.iter().map(move |&q| f32::from(q as i8) * scale)
                        })
                        .collect();
                    // A finite row scale gives infinity if it is larger than f32::MAX / 127
                    if data.iter().any(|value| !value.is_finite()) {
                        return Err(invalid(
                            "the int8 weights have infinity after the row scale",
                        ));
                    }
                    data
                };
                Ok(Value::Matrix(Matrix { rows, cols, data }))
            }
            3 => {
                let count = self.count(64)?;
                (0..count)
                    .map(|_| self.u32())
                    .collect::<Result<_, _>>()
                    .map(Value::Numbers)
            }
            _ => Err(invalid(&format!("unknown kind of entry {kind}"))),
        }
    }
}

/// Entries of the file by name
pub(crate) struct Entries<'a>(HashMap<&'a str, Value<'a>>);

impl<'a> Entries<'a> {
    fn take(&mut self, name: &str) -> Result<Value<'a>, Error> {
        self.0
            .remove(name)
            .ok_or_else(|| invalid(&format!("no entry {name}")))
    }

    pub(crate) fn matrix(&mut self, name: &str, rows: usize, cols: usize) -> Result<Matrix, Error> {
        match self.take(name)? {
            Value::Matrix(matrix) if matrix.rows == rows && matrix.cols == cols => Ok(matrix),
            Value::Matrix(matrix) => Err(invalid(&format!(
                "{name}: size {}×{}, expected {rows}×{cols}",
                matrix.rows, matrix.cols
            ))),
            _ => Err(invalid(&format!("{name} is not a matrix"))),
        }
    }

    pub(crate) fn vector(&mut self, name: &str, size: usize) -> Result<Vec<f32>, Error> {
        Ok(self.matrix(name, 1, size)?.data)
    }

    pub(crate) fn numbers(&mut self, name: &str) -> Result<Vec<u32>, Error> {
        match self.take(name)? {
            Value::Numbers(numbers) => Ok(numbers),
            _ => Err(invalid(&format!("{name} are not numbers"))),
        }
    }

    pub(crate) fn strings(&mut self, name: &str) -> Result<Vec<&'a str>, Error> {
        match self.take(name)? {
            Value::Strings(strings) => Ok(strings),
            _ => Err(invalid(&format!("{name} are not strings"))),
        }
    }

    /// Optional entry of one string
    pub(crate) fn text(&mut self, name: &str) -> Result<Option<&'a str>, Error> {
        match self.0.remove(name) {
            None => Ok(None),
            Some(Value::Strings(strings)) if strings.len() == 1 => Ok(Some(strings[0])),
            Some(_) => Err(invalid(&format!("{name} is not one string"))),
        }
    }

    /// Numbers of the rows of a table by the strings of the entry `name` from the number `first`;
    /// a repeated string is an error: otherwise a number would leave the table
    pub(crate) fn index(&mut self, name: &str, first: u32) -> Result<HashMap<String, u32>, Error> {
        let strings = self.strings(name)?;
        let index: HashMap<String, u32> = (strings.iter().enumerate())
            .map(|(number, text)| ((*text).to_owned(), number as u32 + first))
            .collect();
        if index.len() != strings.len() {
            return Err(invalid(&format!("{name} repeat a string")));
        }
        Ok(index)
    }

    /// Entries the model has not read: an extra entry is a sign of a file of another training version
    pub(crate) fn finish(self) -> Result<(), Error> {
        match self.0.keys().min() {
            None => Ok(()),
            Some(name) => Err(invalid(&format!("extra entry {name}"))),
        }
    }
}

/// Checksum from the header of a file already checked by `read`
pub(crate) fn checksum(data: &[u8]) -> u32 {
    (data.get(MAGIC.len() + 4..HEADER))
        .and_then(|bytes| bytes.try_into().ok())
        .map_or(0, u32::from_le_bytes)
}

/// Entries of the file: the signature, the format version, the checksum and the bounds of the entries
/// are checked
pub(crate) fn read(data: &[u8]) -> Result<Entries<'_>, Error> {
    if data.get(..MAGIC.len()) != Some(MAGIC.as_slice()) {
        return Err(invalid("no signature of an esSyntax model file"));
    }
    if data.len() < HEADER {
        return Err(invalid("the model file is truncated"));
    }
    let mut reader = Reader {
        data,
        at: MAGIC.len(),
    };
    let format = reader.u32()?;
    if format != FORMAT {
        return Err(invalid(&format!(
            "format version {format}, supported {FORMAT}"
        )));
    }
    let checksum = reader.u32()?;
    if crc32fast::hash(&data[HEADER..]) != checksum {
        return Err(invalid("the checksum does not match: the file is damaged"));
    }
    let count = reader.count(MAX_ENTRIES)?;
    let mut entries = HashMap::new();
    for _ in 0..count {
        let len = reader.take(2)?;
        let len = usize::from(u16::from_le_bytes([len[0], len[1]]));
        let name = std::str::from_utf8(reader.take(len)?)
            .map_err(|_| invalid("the name of an entry is not UTF-8"))?;
        if entries.insert(name, reader.value()?).is_some() {
            return Err(invalid(&format!("entry {name} is repeated")));
        }
    }
    if reader.at != data.len() {
        return Err(invalid("data after the entries"));
    }
    Ok(Entries(entries))
}

/// Writing of a model file: for the tests of the crate (the training writes the same format in Python)
#[cfg(test)]
pub(crate) mod write {
    use super::{FORMAT, HEADER, MAGIC};

    pub(crate) enum Item<'a> {
        Strings(Vec<&'a str>),
        F32(usize, usize, Vec<f32>),
        Int8(usize, usize, Vec<f32>),
        Numbers(Vec<u32>),
    }

    pub(crate) fn file(items: &[(&str, Item<'_>)]) -> Vec<u8> {
        let mut body = (items.len() as u32).to_le_bytes().to_vec();
        for (name, item) in items {
            body.extend((name.len() as u16).to_le_bytes());
            body.extend(name.as_bytes());
            match item {
                Item::Strings(strings) => {
                    body.push(0);
                    body.extend((strings.len() as u32).to_le_bytes());
                    for text in strings {
                        body.extend((text.len() as u32).to_le_bytes());
                        body.extend(text.as_bytes());
                    }
                }
                Item::F32(rows, cols, data) => {
                    body.push(1);
                    body.extend((*rows as u32).to_le_bytes());
                    body.extend((*cols as u32).to_le_bytes());
                    data.iter()
                        .for_each(|value| body.extend(value.to_le_bytes()));
                }
                Item::Int8(rows, cols, data) => {
                    body.push(2);
                    body.extend((*rows as u32).to_le_bytes());
                    body.extend((*cols as u32).to_le_bytes());
                    let scales: Vec<f32> = (data.chunks_exact((*cols).max(1)))
                        .map(|row| {
                            row.iter().fold(0.0f32, |m, v| m.max(v.abs())).max(1e-12) / 127.0
                        })
                        .collect();
                    scales
                        .iter()
                        .for_each(|value| body.extend(value.to_le_bytes()));
                    for (row, scale) in data.chunks_exact((*cols).max(1)).zip(&scales) {
                        body.extend(
                            row.iter()
                                .map(|v| (v / scale).round().clamp(-127.0, 127.0) as i8 as u8),
                        );
                    }
                }
                Item::Numbers(numbers) => {
                    body.push(3);
                    body.extend((numbers.len() as u32).to_le_bytes());
                    numbers
                        .iter()
                        .for_each(|value| body.extend(value.to_le_bytes()));
                }
            }
        }
        let mut out = Vec::with_capacity(HEADER + body.len());
        out.extend(MAGIC);
        out.extend(FORMAT.to_le_bytes());
        out.extend(crc32fast::hash(&body).to_le_bytes());
        out.extend(body);
        out
    }
}
