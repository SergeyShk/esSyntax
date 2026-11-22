# essyntax

Fast Spanish dependency parser written in Rust, the core of the
[esSyntax](https://github.com/SergeyShk/esSyntax) library for Python: the head and the
[Universal Dependencies](https://universaldependencies.org/) relation of every word of a sentence.

- The input is the words of a sentence with their UD part of speech and features, for example from the morphological
  analyzer [esMorph](https://crates.io/crates/esmorph); the output is the number of the head of every word (0 for the root)
  and its relation.
- The model is a BiLSTM over the words, their endings and tags; the heads come from a biaffine score and the tree of the
  maximum weight with one root (non-projective trees too), the relations from the pair "dependent - head". In degenerate
  sentences (more than 16 cycles or 8 root candidates among the best heads) and in sentences longer than 1024 words the
  tree is assembled faster: the extra roots and the nodes of cycles are attached to the best root; in long sentences the
  head is looked for among 64 words on each side and the root, and the time grows linearly with the length.
- The part of speech is one of the 17 UD parts of speech in capitals (an unknown one is parsed as `X`), the features are
  in the CoNLL-U notation. A `Relation` has the head, the relation, its number in `Parser::relations` and the
  probabilities of the head and the relation by the model (`head_prob`, `deprel_prob`); `Parser::checksum` is the CRC32
  of the model.
- Sentences of close length are parsed four at once: `Parser::parse_many`.

The model is not part of the crate: the parser reads it from a file.

## Example

```rust,no_run
use essyntax::{Parser, Word};

fn main() -> Result<(), essyntax::Error> {
    let parser = Parser::from_path("es-syntax.bin")?;
    let words = [
        Word::new("La", "DET", "Definite=Def|Gender=Fem|Number=Sing|PronType=Art"),
        Word::new("niña", "NOUN", "Gender=Fem|Number=Sing"),
        Word::new("lee", "VERB", "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin"),
        Word::new("un", "DET", "Definite=Ind|Gender=Masc|Number=Sing|PronType=Art"),
        Word::new("libro", "NOUN", "Gender=Masc|Number=Sing"),
        Word::new(".", "PUNCT", "_"),
    ];
    for (word, relation) in words.iter().zip(parser.parse(&words)) {
        println!("{} -> {} {}", word.form, relation.head, relation.deprel);
    }
    Ok(())
}
```

The model is loaded and checked on every call of `Parser::from_path` and `Parser::from_bytes`: create the parser once
and parse all the text with it, from several threads too.

## Model file

The header is the signature `ESSYNTAX`, the format version and the CRC32 of the rest of the file; then come entries by
name: lists of strings, matrices of f32 or of int8 by rows with a scale per row, numbers. A file of another format
version, a damaged one or one with weights of disagreeing sizes is not loaded: `Error::Format`.

## License

The code is distributed under the [MIT](https://github.com/SergeyShk/esSyntax/blob/master/LICENSE.txt) license.
