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

**esSyntax** is a dependency parser of Spanish: a Rust core with a Python API. For every word of a sentence the parser finds its head and the relation between them in the [Universal Dependencies](https://universaldependencies.org/) annotation.

> [!WARNING]
> Work in progress: so far the package contains only the scaffolding; the parser comes in the next versions. Versions `0.1.0.devN` are published on TestPyPI.

## Installation

Python 3.11 or newer is required.

```bash
pip install essyntax
```

Wheels are built for Linux (Alpine included), macOS and Windows and for the free-threaded Python 3.14t and 3.15t; Rust is not needed to install them. On other platforms pip builds the package from source, which requires [Rust](https://www.rust-lang.org/tools/install) 1.88 or newer. See the [Installation](https://sergeyshk.github.io/esSyntax/installation/) page.

## Development

The project uses [uv](https://docs.astral.sh/uv/) to manage dependencies, [maturin](https://www.maturin.rs/) to build the Rust module and [ruff](https://docs.astral.sh/ruff/) for linting and formatting. Python 3.11 or newer and Rust 1.88 or newer are required.

```bash
git clone https://github.com/SergeyShk/esSyntax.git
cd esSyntax

make deps        # create the environment, install the dependencies and build the Rust module
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
*   **python/essyntax** - the Python package
*   **data** - the model and the check of its forward pass in Rust against PyTorch
*   **scripts** - exporting the UD treebanks and training the model, checking the installed package before publishing and the licenses of the crates of the module
*   **docs** - MkDocs documentation in English and Spanish
*   **tests** - tests of the Python package

</details>

## Authors

*   Sergey Shkarin (kouki.sergey@gmail.com)

## License

The code is distributed under the [MIT](https://github.com/SergeyShk/esSyntax/blob/master/LICENSE.txt) license. The model is trained on the treebanks [UD Spanish AnCora](https://github.com/UniversalDependencies/UD_Spanish-AnCora) and [UD Spanish GSD](https://github.com/UniversalDependencies/UD_Spanish-GSD) and is distributed under the [CC BY-SA 4.0](https://github.com/SergeyShk/esSyntax/blob/master/LICENSE-MODEL.txt) license.
