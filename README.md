<p align="center">
  <img src="https://raw.githubusercontent.com/SergeyShk/esSyntax/master/docs/img/essyntax.png" alt="esSyntax" width="480">
</p>

<h1 align="center">esSyntax</h1>

<p align="center">
  A fast Spanish dependency parser written in Rust with a Python API
</p>

<p align="center">
  <a href="https://sergeyshk.github.io/esSyntax/">Documentation</a> ·
  <a href="https://github.com/SergeyShk/esSyntax/blob/master/README.es.md">Español</a>
</p>

<p align="center">
  <a href="https://github.com/SergeyShk/esSyntax/actions/workflows/ci.yml"><img src="https://github.com/SergeyShk/esSyntax/actions/workflows/ci.yml/badge.svg" alt="Build"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://github.com/SergeyShk/esSyntax/blob/master/LICENSE.txt"><img src="https://img.shields.io/github/license/sergeyshk/essyntax.svg" alt="License"></a>
</p>

---

**esSyntax** is a dependency parser of Spanish: a Rust core with a Python API. For every word of a sentence the parser finds its head and the relation between them in the [Universal Dependencies](https://universaldependencies.org/) annotation. The [anySeg](https://sergeyshk.github.io/anySeg/) segmenter splits the text into sentences and words, and the [esMorph](https://sergeyshk.github.io/esMorph/) morphological analyzer gives the parts of speech and features; the model is trained on the treebanks UD Spanish AnCora and GSD and follows the UD guidelines and the conventions of AnCora.

* **[Parser](https://sergeyshk.github.io/esSyntax/parser/)** - the head and the relation of every word of a text, of an anySeg document or of a sentence with its own parts of speech and features; many sentences at once, without the GIL
* **[Probabilities](https://sergeyshk.github.io/esSyntax/parser/#probs)** - the probabilities of the head and the relation of every word, which tell reliable relations from doubtful ones
* **[The essyntax command](https://sergeyshk.github.io/esSyntax/cli/)** - CoNLL-U from text or from CoNLL-U with parts of speech and features, files and streams by paragraphs
* **[Model](https://sergeyshk.github.io/esSyntax/model/)** - a BiLSTM over the words and their esMorph tags, biaffine heads and a tree with one root; 2.9 MB built into the package
* **[Comparison](https://sergeyshk.github.io/esSyntax/performance/)** - quality and speed compared with other parsers of Spanish

> [!WARNING]
> Work in progress: the API may change until version 0.1.0. Versions `0.1.0.devN` are published on TestPyPI.

## Installation

Python 3.11 or newer is required.

```bash
pip install essyntax
```

Wheels are built for Linux (Alpine included), macOS and Windows and for the free-threaded Python 3.14t and 3.15t; Rust is not needed to install them, and the model is in the package. On other platforms pip builds the package from source, which requires [Rust](https://www.rust-lang.org/tools/install) 1.88 or newer. See the [Installation](https://sergeyshk.github.io/esSyntax/installation/) page.

## Quick start

```python
>>> from essyntax import Parser

>>> parser = Parser()
>>> document = parser.parse_text("Mi madre lava la ropa.")
>>> [(word.form, word.head, word.deprel) for word in document.words]
[('Mi', 2, 'det'), ('madre', 3, 'nsubj'), ('lava', 0, 'root'), ('la', 5, 'det'), ('ropa', 3, 'obj'), ('.', 3, 'punct')]
>>> parser.parse(["Ella", "canta"], ["PRON", "VERB"], ["Case=Nom|Person=3", "Mood=Ind|Person=3"])
[(2, 'nsubj'), (0, 'root')]
```

`parse_text` splits the text into sentences, tokens and words with anySeg, gives the words their lemma, part of speech and features with esMorph, which also splits a verb with clitics into its words (`pónganselo` - `pongan`, `se`, `lo`), and finds the head (the word number from 1, 0 for the root) and the relation of every word; the document keeps the multiword tokens (`del` - `de`, `el`). `parser.annotate(document)` parses an anySeg document that already has its morphology, `parser.parse(words, upos, feats)` parses a sentence with your own parts of speech and features, and `parser.parse_many(sentences)` parses many sentences at once. See the [Parser](https://sergeyshk.github.io/esSyntax/parser/) page.

The `essyntax` command comes with the package and parses text from files or the standard input into [CoNLL-U](https://universaldependencies.org/format.html); its input can also be CoNLL-U with your own parts of speech and features (`essyntax -i conllu`):

```bash
echo "Mi madre lava la ropa." | essyntax
```

```
# newdoc
# newpar
# sent_id = 1
# text = Mi madre lava la ropa.
1	Mi	mi	DET	_	Number=Sing|Person=1|Poss=Yes|PronType=Prs	2	det	_	_
2	madre	madre	NOUN	_	Gender=Fem|Number=Sing	3	nsubj	_	_
3	lava	lavar	VERB	_	Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin	0	root	_	_
4	la	el	DET	_	Definite=Def|Gender=Fem|Number=Sing|PronType=Art	5	det	_	_
5	ropa	ropa	NOUN	_	Gender=Fem|Number=Sing	3	obj	_	SpaceAfter=No
6	.	.	PUNCT	_	PunctType=Peri	3	punct	_	_
```

The options, the input and the output of the command are on the [essyntax command](https://sergeyshk.github.io/esSyntax/cli/) page.

<!-- comparison: the section "Quality and speed" with the table of LAS on AnCora, GSD, PUD and COSER test and words per second against other parsers (docs/performance.md) goes here -->

## Development

The project uses [uv](https://docs.astral.sh/uv/) to manage dependencies, [maturin](https://www.maturin.rs/) to build the Rust module and [ruff](https://docs.astral.sh/ruff/) for linting and formatting. Python 3.11 or newer and Rust 1.88 or newer are required.

```bash
git clone https://github.com/SergeyShk/esSyntax.git
cd esSyntax

make deps        # create the environment, install the dependencies and build the Rust module
make model       # download the UD treebanks and train the model
make test        # run the Python tests, the docstring examples (doctest) and the Rust tests
make lint        # ruff, mypy, rustfmt and clippy
```

The full list of commands is `make help`. The documentation is bilingual: English pages `docs/*.md` with Spanish `docs/*.es.md` next to them; update both versions when editing a page.

Before submitting changes, install the hooks that run the linters on commit and the tests on push:

```bash
uv run pre-commit install
```

## Contributing

Bug reports, ideas and pull requests are welcome, in English or Spanish - the [issues](https://github.com/SergeyShk/esSyntax/issues) are open. The workflow and the checks to run before submitting a pull request are in [CONTRIBUTING.md](https://github.com/SergeyShk/esSyntax/blob/master/CONTRIBUTING.md); the rules of conduct are in the [code of conduct](https://github.com/SergeyShk/esSyntax/blob/master/CODE_OF_CONDUCT.md).

<details>
<summary><b>Project structure</b></summary>

<br>

*   **crates/essyntax** - the parser core in Rust
*   **crates/essyntax-py** - the Python module `essyntax._essyntax` built with PyO3
*   **python/essyntax** - the Python package and the `essyntax` command
*   **data** - the model and the check of its forward pass in Rust against PyTorch
*   **scripts** - exporting the UD treebanks and training the model, checking the installed package before publishing and the licenses of the crates of the module
*   **docs** - MkDocs documentation in English and Spanish
*   **tests** - tests of the Python package

</details>

## Authors

*   Sergey Shkarin (kouki.sergey@gmail.com)

## License

The code is distributed under the [MIT](https://github.com/SergeyShk/esSyntax/blob/master/LICENSE.txt) license. The model is trained on the treebanks [UD Spanish AnCora](https://github.com/UniversalDependencies/UD_Spanish-AnCora) and [UD Spanish GSD](https://github.com/UniversalDependencies/UD_Spanish-GSD) and is distributed under the [CC BY-SA 4.0](https://github.com/SergeyShk/esSyntax/blob/master/LICENSE-MODEL.txt) license.
