//! Check of the forward pass against PyTorch: the model of the repository (`data/es-syntax.bin`) parses
//! the sentences of `data/check.conllu` the same way as the quantized PyTorch model in training
//! (`scripts/train.py`). The tolerance is 0.2 % of the words: the last bits of the sums differ between
//! processors (FMA), and almost equal scores can change places.

use std::path::PathBuf;

use essyntax::{Parser, Word};

fn data(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../data")
        .join(name)
}

/// Words of a sentence (form, UPOS, features) and the heads with relations of PyTorch
type Sentence = (Vec<(String, String, String)>, Vec<(usize, String)>);

/// Sentences of the check file
fn check() -> Vec<Sentence> {
    let text = std::fs::read_to_string(data("check.conllu")).expect("data/check.conllu");
    let mut out = Vec::new();
    let (mut words, mut parse) = (Vec::new(), Vec::new());
    for line in text.lines().chain([""]) {
        if line.is_empty() {
            if !words.is_empty() {
                out.push((std::mem::take(&mut words), std::mem::take(&mut parse)));
            }
            continue;
        }
        let cols: Vec<&str> = line.split('\t').collect();
        // A multiword token: its words follow it
        if cols[0].contains('-') {
            continue;
        }
        words.push((cols[1].to_owned(), cols[3].to_owned(), cols[5].to_owned()));
        parse.push((cols[6].parse().expect("head"), cols[7].to_owned()));
    }
    out
}

#[test]
fn model_matches_pytorch() {
    // The published crate has no directory data: without the check file the test is skipped, without
    // the model it fails
    if !data("check.conllu").exists() {
        eprintln!("no data/check.conllu: the check is skipped");
        return;
    }
    let parser = Parser::from_path(data("es-syntax.bin")).expect("data/es-syntax.bin");
    let sentences = check();
    let words: Vec<Vec<Word<'_>>> = sentences
        .iter()
        .map(|(words, _)| {
            words
                .iter()
                .map(|(form, upos, feats)| Word::new(form, upos, feats))
                .collect()
        })
        .collect();
    let many = parser.parse_many(&words);
    let (mut total, mut differ) = (0, 0);
    for ((words, (_, expected)), parse) in words.iter().zip(&sentences).zip(&many) {
        assert_eq!(parser.parse(words), *parse);
        for ((head, deprel), relation) in expected.iter().zip(parse) {
            total += 1;
            differ += usize::from(*head != relation.head || deprel != relation.deprel);
        }
    }
    assert!(total > 4000, "the check file has {total} words");
    assert!(
        differ * 500 <= total,
        "the parse differs from PyTorch at {differ} words of {total}"
    );
}
