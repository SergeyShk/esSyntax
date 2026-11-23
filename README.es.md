<h1 align="center">esSyntax</h1>

<p align="center">
  Analizador sintáctico de dependencias rápido del español escrito en Rust, con API para Python
</p>

<p align="center">
  <a href="https://sergeyshk.github.io/esSyntax/es/">Documentación</a> ·
  <a href="https://github.com/SergeyShk/esSyntax/blob/master/README.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/SergeyShk/esSyntax/actions/workflows/ci.yml"><img src="https://github.com/SergeyShk/esSyntax/actions/workflows/ci.yml/badge.svg" alt="Build"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://github.com/SergeyShk/esSyntax/blob/master/LICENSE.txt"><img src="https://img.shields.io/github/license/sergeyshk/essyntax.svg" alt="License"></a>
</p>

---

**esSyntax** es un analizador sintáctico de dependencias del español: un núcleo en Rust con API para Python. Para cada palabra de una oración el analizador encuentra la palabra de la que depende y la relación entre ambas en la anotación de [Universal Dependencies](https://universaldependencies.org/).

> [!WARNING]
> En desarrollo: la API puede cambiar hasta la versión 0.1.0. Las versiones `0.1.0.devN` se publican en TestPyPI.

## Instalación

Se requiere Python 3.11 o superior.

```bash
pip install essyntax
```

Hay paquetes precompilados para Linux (también Alpine), macOS y Windows y para Python 3.14t y 3.15t sin GIL; para instalarlos no hace falta Rust. En otras plataformas pip compila el paquete desde el código fuente, lo que requiere [Rust](https://www.rust-lang.org/tools/install) 1.88 o superior. Más detalles en la página de [instalación](https://sergeyshk.github.io/esSyntax/es/installation/).

## Inicio rápido

```python
from essyntax import Parser

parser = Parser()
document = parser.parse_text("Salió del cine.")
print([(word.form, word.head, word.deprel) for word in document.words])
# [('Salió', 0, 'root'), ('de', 4, 'case'), ('el', 4, 'det'), ('cine', 1, 'obl'), ('.', 1, 'punct')]
```

`parse_text` divide el texto en oraciones, tokens y palabras con el segmentador [anySeg](https://github.com/SergeyShk/anySeg), da a las palabras su lema, categoría gramatical y rasgos con el analizador morfológico [esMorph](https://github.com/SergeyShk/esMorph), que además divide un verbo con clíticos en sus palabras (`pónganselo` - `pongan`, `se`, `lo`), y encuentra la palabra de la que depende cada palabra (su número desde 1, 0 para la raíz) y la relación entre ambas; el documento conserva los tokens multipalabra (`del` - `de`, `el`). `parser.annotate(document)` analiza un documento de anySeg que ya tiene su morfología, `parser.parse(words, upos, feats)` analiza una oración con categorías gramaticales y rasgos propios, y `parser.parse_many(sentences)` analiza muchas oraciones a la vez.

El comando `essyntax` se instala con el paquete y analiza el texto de archivos o de la entrada estándar en [CoNLL-U](https://universaldependencies.org/format.html); la entrada también puede ser CoNLL-U con categorías gramaticales y rasgos propios (`essyntax -i conllu`), y `essyntax --help` muestra sus opciones:

```bash
echo "Salió del cine." | essyntax
essyntax texto.txt -o texto.conllu
```

## Desarrollo

El proyecto usa [uv](https://docs.astral.sh/uv/) para gestionar las dependencias, [maturin](https://www.maturin.rs/) para compilar el módulo de Rust y [ruff](https://docs.astral.sh/ruff/) para el análisis y el formato del código. Se requieren Python 3.11 o superior y Rust 1.88 o superior.

```bash
git clone https://github.com/SergeyShk/esSyntax.git
cd esSyntax

make deps        # crear el entorno, instalar las dependencias y compilar el módulo de Rust
make test        # ejecutar las pruebas de Python, los ejemplos de los docstrings (doctest) y las pruebas de Rust
make lint        # ruff, mypy, rustfmt y clippy
```

La lista completa de comandos está en `make help`. La documentación es bilingüe: las páginas en inglés `docs/*.md` con las páginas en español `docs/*.es.md` al lado; al editar una página, actualice las dos versiones.

Antes de enviar cambios, instale los hooks que ejecutan los linters al hacer commit y las pruebas al hacer push:

```bash
uv run pre-commit install
```

## Contribuir

Los informes de errores, las ideas y los pull requests son bienvenidos, en inglés o en español - las [issues](https://github.com/SergeyShk/esSyntax/issues) están abiertas. El flujo de trabajo y las comprobaciones previas a un pull request están en [CONTRIBUTING.md](https://github.com/SergeyShk/esSyntax/blob/master/CONTRIBUTING.md); las normas de conducta están en el [código de conducta](https://github.com/SergeyShk/esSyntax/blob/master/CODE_OF_CONDUCT.md).

<details>
<summary><b>Estructura del proyecto</b></summary>

<br>

*   **crates/essyntax** - el núcleo del analizador en Rust
*   **crates/essyntax-py** - el módulo de Python `essyntax._essyntax`, compilado con PyO3
*   **python/essyntax** - el paquete de Python y el comando `essyntax`
*   **data** - el modelo y la comprobación de su paso hacia adelante en Rust frente a PyTorch
*   **scripts** - la exportación de los treebanks de UD y el entrenamiento del modelo, la comprobación del paquete instalado antes de publicar y las licencias de los crates del módulo
*   **docs** - la documentación de MkDocs en inglés y en español
*   **tests** - las pruebas del paquete de Python

</details>

## Autores

*   Sergey Shkarin (kouki.sergey@gmail.com)

## Licencia

El código se distribuye bajo la licencia [MIT](https://github.com/SergeyShk/esSyntax/blob/master/LICENSE.txt). El modelo está entrenado con los treebanks [UD Spanish AnCora](https://github.com/UniversalDependencies/UD_Spanish-AnCora) y [UD Spanish GSD](https://github.com/UniversalDependencies/UD_Spanish-GSD) y se distribuye bajo la licencia [CC BY-SA 4.0](https://github.com/SergeyShk/esSyntax/blob/master/LICENSE-MODEL.txt).
