# Analizador

``` {.python .signature}
Parser(path=None)
```

Analizador sintáctico de dependencias del español: para cada palabra de una oración encuentra su núcleo - la palabra de la que depende - y la relación de [Universal Dependencies](https://universaldependencies.org/u/dep/). El núcleo es el número de una palabra en la oración empezando por 1; la raíz de la oración tiene 0. Sin `path` se usa el [modelo](model.md) del paquete: va dentro del módulo y se carga una vez por proceso, en unos 5 ms, así que un analizador nuevo se crea al instante. Los analizadores de un mismo archivo de modelo también lo comparten, aunque lleguen a él por otra ruta o por un enlace: mientras el archivo no cambia, se carga una sola vez, y el último cargado se queda en memoria también sin analizadores.

Excepciones:

- `FileNotFoundError` - el archivo del modelo no existe;
- `OSError` - el archivo del modelo no se puede leer: sin acceso, la ruta es un directorio;
- `ValueError` - el archivo no es un modelo de esSyntax, el modelo es de otra versión del formato o el archivo está dañado (la suma de comprobación no coincide);
- `TypeError` - la ruta no es una cadena ni `os.PathLike`.

=== "Código"

    ``` python
    from essyntax import Parser

    parser = Parser()
    document = parser.parse_text("La gata que vi ayer dormía en el porche.")
    [(word.form, word.head, word.deprel) for word in document.words]
    ```

=== "Resultado"

    ```
    [('La', 2, 'det'), ('gata', 6, 'nsubj'), ('que', 4, 'obj'), ('vi', 2, 'acl:relcl'), ('ayer', 4, 'advmod'), ('dormía', 0, 'root'), ('en', 9, 'case'), ('el', 9, 'det'), ('porche', 6, 'obl'), ('.', 6, 'punct')]
    ```

<!-- figure: the parse of a sentence as arcs from the head to the dependent (docs/img/arcs.svg, arcs.es.svg) -->

## Parámetros { #parameters }

| Parámetro | Tipo | Por defecto | Descripción |
| :-------- | :--- | :---------- | :---------- |
| `path` | `str` / `PathLike` | `None` | Un archivo de modelo de esSyntax; por defecto, el modelo del paquete |

Propiedades de solo lectura:

| Propiedad | Tipo | Descripción |
| :-------- | :--- | :---------- |
| `path` | `Path` / `None` | La ruta absoluta al archivo del modelo; `None` para el modelo del paquete |
| `relations` | `list[str]` | Las 45 relaciones del modelo con sus subtipos: `nsubj`, `obl:arg`, `root` y otras |
| `sources` | `dict` | Sobre el modelo: la suma de comprobación `crc32` (el CRC32 del archivo del modelo tras su cabecera, que distingue un modelo de otro) y cómo se entrenó el modelo - la versión de UD, los treebanks y sus commits, la versión de esMorph de las etiquetas, el LAS en dev |

## Métodos

<div class="metric-card" markdown>

### Análisis de un texto { #parse_text }

`parse_text` · `anyseg.Document`
{ .metric-meta }

``` {.python .signature}
parse_text(text, *, segmenter=None, analyzer=None)
```

Divide el texto en oraciones, tokens y sus palabras con el segmentador [anySeg](https://sergeyshk.github.io/anySeg/) (`del` es `de` + `el`), da a las palabras su lema, categoría gramatical y rasgos en contexto con el analizador morfológico [esMorph](https://sergeyshk.github.io/esMorph/es/), que además divide en palabras un token que el segmentador deja entero (`pónganselo` es `pongan` + `se` + `lo`), y encuentra el núcleo y la relación de cada palabra. Devuelve un documento de anySeg (`anyseg.Document`) con las columnas `lemma`, `upos`, `feats`, `head` y `deprel`: sus palabras, oraciones y su salida en CoNLL-U se describen en la [documentación de anySeg](https://sergeyshk.github.io/anySeg/document/). El documento conserva los tokens multipalabra; sus palabras se analizan como las demás. El segmentador y el analizador por defecto se crean en la primera llamada y se reutilizan después; los propios - un segmentador con sus abreviaturas o un analizador con sus palabras, por ejemplo - se pasan como parámetros. El analizador no cambia los límites de las oraciones de anySeg.

| Parámetro | Tipo | Por defecto | Descripción |
| :-------- | :--- | :---------- | :---------- |
| `text` | `str` | - | El texto |
| `segmenter` | `anyseg.Segmenter` | `None` | Un segmentador o un objeto con el método `segment`; por defecto, `Segmenter("es")` |
| `analyzer` | `esmorph.Analyzer` | `None` | Un analizador morfológico o un objeto con el método `annotate`, que devuelve el documento anotado o `None` si rellenó el dado; por defecto, `Analyzer()` |

Excepciones: `TypeError` - el texto no es una cadena, el segmentador no tiene el método `segment`, `segment` no devolvió un documento, el analizador no tiene el método `annotate` o `annotate` no devolvió ni un documento ni `None`; `ValueError` - el analizador no dio categorías gramaticales a las palabras.

=== "Código"

    ``` python
    document = parser.parse_text("Los niños salieron del colegio.")
    print(document.to_conllu())
    ```

=== "Resultado"

    ```
    # newdoc
    # newpar
    # sent_id = 1
    # text = Los niños salieron del colegio.
    1	Los	el	DET	_	Definite=Def|Gender=Masc|Number=Plur|PronType=Art	2	det	_	_
    2	niños	niño	NOUN	_	Gender=Masc|Number=Plur	3	nsubj	_	_
    3	salieron	salir	VERB	_	Mood=Ind|Number=Plur|Person=3|Tense=Past|VerbForm=Fin	0	root	_	_
    4-5	del	_	_	_	_	_	_	_	_
    4	de	de	ADP	_	_	6	case	_	_
    5	el	el	DET	_	Definite=Def|Gender=Masc|Number=Sing|PronType=Art	6	det	_	_
    6	colegio	colegio	NOUN	_	Gender=Masc|Number=Sing	3	obl	_	SpaceAfter=No
    7	.	.	PUNCT	_	PunctType=Peri	3	punct	_	_
    ```

Una abreviatura que el segmentador no conoce termina la oración; un segmentador propio la conoce:

=== "Código"

    ``` python
    from anyseg import Segmenter

    text = "Llamó el subtte. Pérez."
    len(parser.parse_text(text).sentences)
    document = parser.parse_text(text, segmenter=Segmenter("es", abbreviations=["subtte."]))
    [(word.form, word.head, word.deprel) for word in document.words]
    ```

=== "Resultado"

    ```
    2
    [('Llamó', 0, 'root'), ('el', 3, 'det'), ('subtte.', 1, 'obj'), ('Pérez', 3, 'appos'), ('.', 1, 'punct')]
    ```

Una palabra que esMorph no conoce recibe un análisis estimado; un analizador con sus palabras le da los análisis de una palabra modelo:

=== "Código"

    ``` python
    from esmorph import Analyzer

    text = "Ella tiktokea cada mañana."
    parser.parse_text(text).words[1].upos
    analyzer = Analyzer(words={"tiktokear": "bloguear"})
    document = parser.parse_text(text, analyzer=analyzer)
    [(word.form, word.upos, word.head, word.deprel) for word in document.words]
    ```

=== "Resultado"

    ```
    'NOUN'
    [('Ella', 'PRON', 2, 'nsubj'), ('tiktokea', 'VERB', 0, 'root'), ('cada', 'DET', 4, 'det'), ('mañana', 'NOUN', 2, 'obl'), ('.', 'PUNCT', 2, 'punct')]
    ```

</div>

<div class="metric-card" markdown>

### Análisis de un documento { #annotate }

`annotate` · `None`
{ .metric-meta }

``` {.python .signature}
annotate(document)
```

Rellena las columnas `head` y `deprel` de un documento de anySeg; los valores anteriores se sustituyen. Las categorías gramaticales y los rasgos se toman de las columnas `upos` y `feats`, así que antes el documento recibe su morfología, normalmente con `esmorph.Analyzer().annotate(document)`: devuelve un documento nuevo cuando divide un token en palabras, y es ese documento el que se analiza. Las palabras de los tokens multipalabra se analizan como las demás. El documento es un `anyseg.Document` o un objeto con la misma interfaz: `column(name)`, `sentences` (una oración tiene `words`, una palabra tiene `index`) y `set_columns`. El grafo mejorado (la columna `deps`) y los nodos vacíos de un documento CoNLL-U no cambian. El análisis se hace sin el GIL.

| Parámetro | Tipo | Por defecto | Descripción |
| :-------- | :--- | :---------- | :---------- |
| `document` | `anyseg.Document` | - | El documento con categorías gramaticales y rasgos |

Excepciones:

- `ValueError` - una palabra no tiene categoría gramatical, una categoría no es una de las 17 categorías de UD, o las oraciones del documento no se suceden a lo largo de todas sus palabras;
- `TypeError` - no es un documento (`parse_text` analiza un texto), una columna del documento no es de cadenas, o el número de una palabra no es un entero.

=== "Código"

    ``` python
    from anyseg import Segmenter
    from esmorph import Analyzer

    document = Segmenter("es").segment("Mi madre lava la ropa.")
    document = Analyzer().annotate(document)
    parser.annotate(document)
    document.column("head"), document.column("deprel")
    ```

=== "Resultado"

    ```
    ([2, 3, 0, 5, 3, 3], ['det', 'nsubj', 'root', 'det', 'obj', 'punct'])
    ```

</div>

<div class="metric-card" markdown>

### Análisis de una oración { #parse }

`parse` · `list[tuple[int, str]]`
{ .metric-meta }

``` {.python .signature}
parse(words, upos, feats, *, probs=False)
```

El núcleo y la relación de cada palabra de la oración en el mismo orden; una oración vacía da una lista vacía. Las palabras llegan con su categoría gramatical y sus rasgos en la anotación de UD, como los da esMorph. La categoría es una de las 17 categorías de UD en mayúsculas (`NOUN`, `VERB`, `X`): con otras etiquetas, en minúsculas o las etiquetas EAGLES de AnCora por ejemplo, el modelo analizaría casi al azar, así que son un error. Los rasgos son un campo de CoNLL-U (`Gender=Fem|Number=Sing`) o un diccionario, como `feats` de un análisis de esMorph; `_`, una cadena vacía, un diccionario vacío o `None` significan sin rasgos. Los rasgos que el modelo no conoce se omiten. El modelo está entrenado con las etiquetas de esMorph quitando una parte de los rasgos, así que se las arregla sin algunos de ellos: sin ningún rasgo el LAS en AnCora dev baja unos 0.9 puntos. El análisis se hace sin el GIL.

| Parámetro | Tipo | Por defecto | Descripción |
| :-------- | :--- | :---------- | :---------- |
| `words` | `Iterable[str]` | - | Las formas de las palabras |
| `upos` | `Iterable[str]` | - | Las categorías gramaticales de UD |
| `feats` | `Iterable[str \| Mapping[str, str] \| None]` | - | Los rasgos de UD de cada palabra |
| `probs` | `bool` | `False` | Añadir las [probabilidades](#probs) del núcleo y de la relación: cuádruplas en lugar de pares |

Excepciones:

- `ValueError` - las longitudes de `words`, `upos` y `feats` difieren, o una categoría no es una de las 17 categorías de UD;
- `TypeError` - la entrada no es una colección de cadenas (una cadena en lugar de una lista también es un error) o `probs` no es un bool.

=== "Código"

    ``` python
    parser.parse(
        ["Ella", "canta", "una", "canción"],
        ["PRON", "VERB", "DET", "NOUN"],
        [
            "Case=Nom|Gender=Fem|Number=Sing|Person=3|PronType=Prs",
            "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin",
            "Definite=Ind|Gender=Fem|Number=Sing|PronType=Art",
            "Gender=Fem|Number=Sing",
        ],
    )
    ```

=== "Resultado"

    ```
    [(2, 'nsubj'), (0, 'root'), (4, 'det'), (2, 'obj')]
    ```

Si el texto ya está dividido en palabras, esMorph les da la morfología en contexto: el primer análisis de cada palabra es el que eligió su modelo de contexto.

=== "Código"

    ``` python
    from esmorph import Analyzer

    words = ["Los", "niños", "juegan", "en", "el", "parque", "."]
    best = [analyses[0] for analyses in Analyzer().analyze_sentence(words)]
    parser.parse(words, [a.pos for a in best], [a.feats for a in best])
    ```

=== "Resultado"

    ```
    [(2, 'det'), (3, 'nsubj'), (0, 'root'), (6, 'case'), (6, 'det'), (3, 'obl'), (3, 'punct')]
    ```

</div>

<div class="metric-card" markdown>

### Análisis de muchas oraciones { #parse_many }

`parse_many` · `list[list[tuple[int, str]]]`
{ .metric-meta }

``` {.python .signature}
parse_many(sentences, *, probs=False)
```

Lo mismo que `parse` para cada oración, pero más rápido: las oraciones de longitudes cercanas se analizan de cuatro en cuatro. Una oración es un trío (formas, categorías gramaticales, rasgos); `probs=True` añade las [probabilidades](#probs), como en `parse`. El análisis se hace sin el GIL en bloques de 256 oraciones; Ctrl+C funciona entre ellos.

| Parámetro | Tipo | Por defecto | Descripción |
| :-------- | :--- | :---------- | :---------- |
| `sentences` | `Iterable[tuple[Iterable[str], Iterable[str], Iterable[str \| Mapping[str, str] \| None]]]` | - | Las oraciones, como las toma `parse` |
| `probs` | `bool` | `False` | Añadir las probabilidades del núcleo y de la relación |

Excepciones: `ValueError` - una oración no son tres colecciones, sus longitudes difieren, o una categoría no es una de las 17 categorías de UD; `TypeError` - la entrada no es una colección de cadenas o `probs` no es un bool.

=== "Código"

    ``` python
    parser.parse_many(
        [
            (["¡", "Hola", "!"], ["PUNCT", "INTJ", "PUNCT"], [None, None, None]),
            (["Llueve", "mucho"], ["VERB", "ADV"], [{"Mood": "Ind", "Person": "3"}, "_"]),
        ]
    )
    ```

=== "Resultado"

    ```
    [[(2, 'punct'), (0, 'root'), (2, 'punct')], [(0, 'root'), (1, 'advmod')]]
    ```

</div>

## Probabilidades { #probs }

Con `probs=True` cada palabra tiene, además de su núcleo y su relación, dos probabilidades del modelo: `head_prob` del núcleo entre todas las palabras de la oración y la raíz (en una oración de más de 1024 palabras, entre los candidatos de la [ventana](#tree) y el núcleo que da la construcción del árbol), y `deprel_prob` de la relación con ese núcleo entre las relaciones distintas de `root`; la relación `root` de la raíz la fija la [regla](#tree), y su probabilidad es 1. Su producto es la probabilidad de que la relación sea correcta en conjunto. Las probabilidades distinguen las relaciones fiables de las dudosas: en AnCora dev el núcleo es correcto en el 98.7 % de las palabras con `head_prob` desde 0.99 (el 74 % de las palabras) y en el 38 % de las palabras por debajo de 0.5 (el 2 %). Las probabilidades son locales - por palabra, no por árbol - y algo altas: en AnCora dev la media de `head_prob` está 2.8 puntos por encima de la proporción de núcleos correctos, y la media del producto 2.9 puntos por encima de la proporción de relaciones correctas con sus subtipos. En GSD dev, que el modelo analiza con las convenciones de AnCora, la diferencia es mayor: 6.0 y 10.2 puntos.

=== "Código"

    ``` python
    words = ["Vi", "a", "la", "niña", "con", "el", "telescopio", "."]
    best = [analyses[0] for analyses in Analyzer().analyze_sentence(words)]
    relations = parser.parse(words, [a.pos for a in best], [a.feats for a in best], probs=True)
    [
        (word, head, deprel, round(p, 2), round(q, 2))
        for word, (head, deprel, p, q) in zip(words, relations)
    ]
    ```

=== "Resultado"

    ```
    [('Vi', 0, 'root', 1.0, 1.0), ('a', 4, 'case', 1.0, 1.0), ('la', 4, 'det', 1.0, 1.0), ('niña', 1, 'obj', 1.0, 0.49), ('con', 7, 'case', 1.0, 1.0), ('el', 7, 'det', 1.0, 1.0), ('telescopio', 1, 'obl', 0.81, 0.9), ('.', 1, 'punct', 1.0, 1.0)]
    ```

El telescopio puede ser de la niña: el núcleo de `telescopio` es `Vi` con probabilidad 0.81, y la relación `obj` de `niña` tiene solo 0.49.

## El árbol del análisis { #tree }

Cada palabra tiene un núcleo, una oración tiene una raíz y no hay ciclos; se admiten árboles no proyectivos (relaciones que se cruzan). El analizador elige el árbol con la mayor suma de puntuaciones de los núcleos (el algoritmo de Chu - Liu - Edmonds). En oraciones degeneradas, donde los mejores núcleos dan más de 16 ciclos u 8 candidatos a raíz, el árbol se construye más rápido: las raíces sobrantes y los nodos de los ciclos se unen a la mejor raíz. El árbol de una oración de más de 1024 palabras se construye igual - un texto sin puntuación, por ejemplo, que el segmentador no divide en oraciones; el núcleo de una palabra se busca entre 64 palabras a cada lado y la raíz, así que el tiempo de análisis crece linealmente con la longitud. Las relaciones llevan subtipos, como en la anotación de UD de AnCora (`nsubj:pass`, `obl:arg`, `expl:pv`); solo la raíz tiene la relación `root`; la evaluación de CoNLL 2018 compara la relación sin el subtipo.

## Hilos y procesos { #threads }

El analizador no cambia al analizar: un mismo analizador se puede compartir entre hilos, y el análisis se hace sin el GIL, así que los hilos analizan en paralelo. En Python 3.14t y 3.15t sin GIL el módulo no activa el GIL. El analizador pasa a otro proceso con pickle: se guarda la ruta absoluta al modelo o la marca del modelo del paquete. `copy.copy` y `copy.deepcopy` devuelven el mismo objeto. Dos analizadores son iguales si su modelo viene del mismo archivo (también por otra ruta o un enlace) que no cambió entre su creación, o si ambos usan el modelo del paquete; un analizador se puede guardar en una referencia débil (`weakref`).

=== "Código"

    ``` python
    from concurrent.futures import ThreadPoolExecutor

    texts = ["Llueve.", "Mi madre lava la ropa."]
    with ThreadPoolExecutor(2) as pool:
        documents = list(pool.map(parser.parse_text, texts))
    [document.column("deprel") for document in documents]
    ```

=== "Resultado"

    ```
    [['root', 'punct'], ['det', 'nsubj', 'root', 'det', 'obj', 'punct']]
    ```
