<p align="center">
  <img src="https://raw.githubusercontent.com/SergeyShk/esSyntax/master/docs/img/essyntax.png" alt="esSyntax" width="480">
</p>

<h1 align="center">esSyntax</h1>

<p align="center">
  Analizador sintáctico de dependencias rápido del español escrito en Rust, con API para Python
</p>

<p align="center">
  <a href="https://sergeyshk.github.io/esSyntax/es/">Documentación</a> ·
  <a href="https://pypi.org/project/essyntax/">PyPI</a> ·
  <a href="https://crates.io/crates/essyntax">crates.io</a> ·
  <a href="https://github.com/SergeyShk/esSyntax/blob/master/README.md">English</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/essyntax/"><img src="https://img.shields.io/pypi/v/essyntax?logo=pypi&logoColor=FFE873" alt="Versión"></a>
  <a href="https://pypi.org/project/essyntax/"><img src="https://img.shields.io/pypi/pyversions/essyntax.svg?logo=python&logoColor=FFE873" alt="Versiones de Python compatibles"></a>
  <a href="https://crates.io/crates/essyntax"><img src="https://img.shields.io/crates/v/essyntax?logo=rust" alt="Crate"></a>
  <a href="https://github.com/SergeyShk/esSyntax/actions/workflows/ci.yml"><img src="https://github.com/SergeyShk/esSyntax/actions/workflows/ci.yml/badge.svg" alt="Build"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://github.com/SergeyShk/esSyntax/blob/master/LICENSE.txt"><img src="https://img.shields.io/github/license/sergeyshk/essyntax.svg" alt="Licencia"></a>
</p>

---

**esSyntax** es un analizador sintáctico de dependencias del español: un núcleo en Rust con API para Python. Para cada palabra de una oración el analizador encuentra la palabra de la que depende y la relación entre ambas en la anotación de [Universal Dependencies](https://universaldependencies.org/). El segmentador [anySeg](https://sergeyshk.github.io/anySeg/) divide el texto en oraciones y palabras, y el analizador morfológico [esMorph](https://sergeyshk.github.io/esMorph/es/) da las categorías gramaticales y los rasgos; el modelo está entrenado con los treebanks UD Spanish AnCora y GSD y sigue la guía de UD y las convenciones de AnCora.

* **[Analizador](https://sergeyshk.github.io/esSyntax/es/parser/)** - el núcleo y la relación de cada palabra de un texto, de un documento de anySeg o de una oración con sus propias categorías gramaticales y rasgos; muchas oraciones a la vez, sin el GIL
* **[Probabilidades](https://sergeyshk.github.io/esSyntax/es/parser/#probs)** - las probabilidades del núcleo y de la relación de cada palabra, que distinguen las relaciones fiables de las dudosas
* **[El comando essyntax](https://sergeyshk.github.io/esSyntax/es/cli/)** - CoNLL-U a partir de texto o de CoNLL-U con categorías gramaticales y rasgos, archivos y flujos por párrafos
* **[Modelo](https://sergeyshk.github.io/esSyntax/es/model/)** - una BiLSTM sobre las palabras y sus etiquetas de esMorph, núcleos biafines y un árbol con una sola raíz; 2.9 MB dentro del paquete
* **[Comparación](https://sergeyshk.github.io/esSyntax/es/performance/)** - calidad y velocidad frente a otros analizadores sintácticos del español

## Instalación

Se requiere Python 3.11 o superior.

```bash
pip install essyntax
```

Hay paquetes precompilados para Linux (también Alpine), macOS y Windows y para Python 3.14t y 3.15t sin GIL; para instalarlos no hace falta Rust, y el modelo va en el paquete. En otras plataformas pip compila el paquete desde el código fuente, lo que requiere [Rust](https://www.rust-lang.org/tools/install) 1.88 o superior. Más detalles en la página de [instalación](https://sergeyshk.github.io/esSyntax/es/installation/).

## Inicio rápido

```python
>>> from essyntax import Parser

>>> parser = Parser()
>>> document = parser.parse_text("Mi madre lava la ropa.")
>>> [(word.form, word.head, word.deprel) for word in document.words]
[('Mi', 2, 'det'), ('madre', 3, 'nsubj'), ('lava', 0, 'root'), ('la', 5, 'det'), ('ropa', 3, 'obj'), ('.', 3, 'punct')]
>>> parser.parse(["Ella", "canta"], ["PRON", "VERB"], ["Case=Nom|Person=3", "Mood=Ind|Person=3"])
[(2, 'nsubj'), (0, 'root')]
```

`parse_text` divide el texto en oraciones, tokens y palabras con anySeg, da a las palabras su lema, categoría gramatical y rasgos con esMorph, que además divide un verbo con clíticos en sus palabras (`pónganselo` - `pongan`, `se`, `lo`), y encuentra la palabra de la que depende cada palabra (su número desde 1, 0 para la raíz) y la relación entre ambas; el documento conserva los tokens multipalabra (`del` - `de`, `el`). `parser.annotate(document)` analiza un documento de anySeg que ya tiene su morfología, `parser.parse(words, upos, feats)` analiza una oración con categorías gramaticales y rasgos propios, y `parser.parse_many(sentences)` analiza muchas oraciones a la vez. Más detalles en la página del [analizador](https://sergeyshk.github.io/esSyntax/es/parser/).

El comando `essyntax` se instala con el paquete y analiza el texto de archivos o de la entrada estándar en [CoNLL-U](https://universaldependencies.org/format.html); la entrada también puede ser CoNLL-U con categorías gramaticales y rasgos propios (`essyntax -i conllu`):

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

Las opciones, la entrada y la salida del comando están en la página del [comando essyntax](https://sergeyshk.github.io/esSyntax/es/cli/).

## Calidad y velocidad

LAS desde el texto en bruto en las partes de prueba de los treebanks de UD 2.19 (script oficial de CoNLL 2018, con la puntuación), %, y velocidad en un hilo:

| Sistema | AnCora | GSD | PUD | COSER | Palabras/s |
| :------ | -----: | --: | --: | ----: | ---------: |
| esSyntax | 89.25 | 80.95 | 81.97 | 65.52 | 31 253 |
| spaCy es_core_news_sm | 79.77 | 70.48 | 72.82 | 59.24 | 34 069 |
| spaCy es_dep_news_trf | 85.01 | 74.45 | 75.85 | 62.73 | 1332 |
| Stanza | 89.19 | 84.89 | 83.99 | 65.43 | 1143 |
| Stanza ancora | **90.90** | 80.20 | 81.41 | **66.76** | 1146 |
| Stanza accurate | 90.67 | **87.14** | **85.17** | 66.47 | 424 |
| UDPipe 1 | 78.73 | 68.48 | 72.19 | 58.24 | 6155 |

El modelo de esSyntax está entrenado con AnCora y GSD y analiza con las convenciones de AnCora; Stanza y Stanza accurate, con AnCora y GSD, cuyas convenciones comparte PUD, y los demás modelos, con AnCora. Velocidad: un hilo, las palabras de referencia de la parte de prueba de AnCora, junto con el etiquetado (en esSyntax, el de esMorph); los demás sistemas, las métricas y las condiciones de la medición están en la página de [comparación](https://sergeyshk.github.io/esSyntax/es/performance/).

## Desarrollo

El proyecto usa [uv](https://docs.astral.sh/uv/) para gestionar las dependencias, [maturin](https://www.maturin.rs/) para compilar el módulo de Rust y [ruff](https://docs.astral.sh/ruff/) para el análisis y el formato del código. Se requieren Python 3.11 o superior y Rust 1.88 o superior.

```bash
git clone https://github.com/SergeyShk/esSyntax.git
cd esSyntax

make deps        # crear el entorno, instalar las dependencias y compilar el módulo de Rust
make model       # descargar los treebanks de UD y entrenar el modelo
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
*   **scripts** - la exportación de los treebanks de UD y el entrenamiento del modelo, la comparación con otros analizadores, las figuras de la documentación, la comprobación del paquete instalado antes de publicar y las licencias de los crates del módulo
*   **docs** - la documentación de MkDocs en inglés y en español
*   **tests** - las pruebas del paquete de Python

</details>

## Autores

*   Sergey Shkarin (kouki.sergey@gmail.com)

## Licencia

El código se distribuye bajo la licencia [MIT](https://github.com/SergeyShk/esSyntax/blob/master/LICENSE.txt). El modelo está entrenado con los treebanks [UD Spanish AnCora](https://github.com/UniversalDependencies/UD_Spanish-AnCora) y [UD Spanish GSD](https://github.com/UniversalDependencies/UD_Spanish-GSD) y se distribuye bajo la licencia [CC BY-SA 4.0](https://github.com/SergeyShk/esSyntax/blob/master/LICENSE-MODEL.txt).
