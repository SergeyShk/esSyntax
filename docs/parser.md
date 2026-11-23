# Parser

``` {.python .signature}
Parser(path=None)
```

A dependency parser of Spanish: for every word of a sentence it finds the head - the word it depends on - and the [Universal Dependencies](https://universaldependencies.org/u/dep/) relation. The head is the number of a word in the sentence starting from 1; the root of the sentence has 0. Without `path` the package [model](model.md) is used: it is built into the module and loaded once per process, in about 5 ms, so a new parser is created at once. Parsers of one model file share the model too, also when they reach the file by another path or a link: while the file does not change, it is loaded once, and the last loaded model stays in memory without parsers too.

Exceptions:

- `FileNotFoundError` - there is no model file;
- `OSError` - the model file cannot be read: no access, the path points to a directory;
- `ValueError` - the file is not an esSyntax model, the model has another format version or the file is damaged (the checksum does not match);
- `TypeError` - the path is neither a string nor `os.PathLike`.

=== "Code"

    ``` python
    from essyntax import Parser

    parser = Parser()
    document = parser.parse_text("La gata que vi ayer dormía en el porche.")
    [(word.form, word.head, word.deprel) for word in document.words]
    ```

=== "Result"

    ```
    [('La', 2, 'det'), ('gata', 6, 'nsubj'), ('que', 4, 'obj'), ('vi', 2, 'acl:relcl'), ('ayer', 4, 'advmod'), ('dormía', 0, 'root'), ('en', 9, 'case'), ('el', 9, 'det'), ('porche', 6, 'obl'), ('.', 6, 'punct')]
    ```

<!-- figure: the parse of a sentence as arcs from the head to the dependent (docs/img/arcs.svg, arcs.es.svg) -->

## Parameters { #parameters }

| Parameter | Type | Default | Description |
| :-------- | :--- | :------ | :---------- |
| `path` | `str` / `PathLike` | `None` | An esSyntax model file; the package model by default |

Read-only properties:

| Property | Type | Description |
| :------- | :--- | :---------- |
| `path` | `Path` / `None` | The absolute path to the model file; `None` for the package model |
| `relations` | `list[str]` | The 45 relations of the model with subtypes: `nsubj`, `obl:arg`, `root` and others |
| `sources` | `dict` | About the model: the checksum `crc32` (the CRC32 of the model file after its header, which tells one model from another) and how the model was trained - the UD release, the treebanks and their commits, the esMorph version of the tags, LAS on dev |

## Methods

<div class="metric-card" markdown>

### Parsing a text { #parse_text }

`parse_text` · `anyseg.Document`
{ .metric-meta }

``` {.python .signature}
parse_text(text, *, segmenter=None, analyzer=None)
```

Splits the text into sentences, tokens and their words with the [anySeg](https://sergeyshk.github.io/anySeg/) segmenter (`del` is `de` + `el`), gives the words their lemma, part of speech and features in context with the [esMorph](https://sergeyshk.github.io/esMorph/) morphological analyzer, which also splits into words a token that the segmenter leaves whole (`pónganselo` is `pongan` + `se` + `lo`), and finds the head and the relation of every word. Returns an anySeg document (`anyseg.Document`) with the columns `lemma`, `upos`, `feats`, `head` and `deprel`: its words, sentences and CoNLL-U output are described in the [anySeg documentation](https://sergeyshk.github.io/anySeg/document/). The document keeps the multiword tokens; their words are parsed as the other words. The default segmenter and analyzer are created on the first call and reused afterwards; your own - a segmenter with your abbreviations or an analyzer with your words, for example - are passed as parameters. The parser does not change the sentence boundaries of anySeg.

| Parameter | Type | Default | Description |
| :-------- | :--- | :------ | :---------- |
| `text` | `str` | - | The text |
| `segmenter` | `anyseg.Segmenter` | `None` | A segmenter or an object with the `segment` method; by default `Segmenter("es")` |
| `analyzer` | `esmorph.Analyzer` | `None` | A morphological analyzer or an object with the `annotate` method, which returns the annotated document or `None` if it filled the given one; by default `Analyzer()` |

Exceptions: `TypeError` - the text is not a string, the segmenter has no `segment` method, `segment` returned no document, the analyzer has no `annotate` method or `annotate` returned neither a document nor `None`; `ValueError` - the analyzer gave the words no parts of speech.

=== "Code"

    ``` python
    document = parser.parse_text("Los niños salieron del colegio.")
    print(document.to_conllu())
    ```

=== "Result"

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

An abbreviation that the segmenter does not know ends the sentence; your own segmenter knows it:

=== "Code"

    ``` python
    from anyseg import Segmenter

    text = "Llamó el subtte. Pérez."
    len(parser.parse_text(text).sentences)
    document = parser.parse_text(text, segmenter=Segmenter("es", abbreviations=["subtte."]))
    [(word.form, word.head, word.deprel) for word in document.words]
    ```

=== "Result"

    ```
    2
    [('Llamó', 0, 'root'), ('el', 3, 'det'), ('subtte.', 1, 'obj'), ('Pérez', 3, 'appos'), ('.', 1, 'punct')]
    ```

A word that esMorph does not know gets a guessed analysis; an analyzer with your words gives it the analyses of a sample word:

=== "Code"

    ``` python
    from esmorph import Analyzer

    text = "Ella tiktokea cada mañana."
    parser.parse_text(text).words[1].upos
    analyzer = Analyzer(words={"tiktokear": "bloguear"})
    document = parser.parse_text(text, analyzer=analyzer)
    [(word.form, word.upos, word.head, word.deprel) for word in document.words]
    ```

=== "Result"

    ```
    'NOUN'
    [('Ella', 'PRON', 2, 'nsubj'), ('tiktokea', 'VERB', 0, 'root'), ('cada', 'DET', 4, 'det'), ('mañana', 'NOUN', 2, 'obl'), ('.', 'PUNCT', 2, 'punct')]
    ```

</div>

<div class="metric-card" markdown>

### Parsing a document { #annotate }

`annotate` · `None`
{ .metric-meta }

``` {.python .signature}
annotate(document)
```

Fills the `head` and `deprel` columns of an anySeg document; the previous values are replaced. The parts of speech and features come from the `upos` and `feats` columns, so the document gets its morphology first, usually with `esmorph.Analyzer().annotate(document)`: it returns a new document when it splits a token into words, and that document is the one to parse. The words of multiword tokens are parsed as the other words. The document is an `anyseg.Document` or an object with the same interface: `column(name)`, `sentences` (a sentence has `words`, a word has `index`) and `set_columns`. The enhanced graph (the `deps` column) and the empty nodes of a CoNLL-U document are not changed. Parsing runs without the GIL.

| Parameter | Type | Default | Description |
| :-------- | :--- | :------ | :---------- |
| `document` | `anyseg.Document` | - | The document with parts of speech and features |

Exceptions:

- `ValueError` - a word has no part of speech, a part of speech is not one of the 17 UD parts of speech, or the sentences of the document do not follow each other over all its words;
- `TypeError` - this is not a document (`parse_text` parses a text), a column of the document is not of strings, or a word number is not an integer.

=== "Code"

    ``` python
    from anyseg import Segmenter
    from esmorph import Analyzer

    document = Segmenter("es").segment("Mi madre lava la ropa.")
    document = Analyzer().annotate(document)
    parser.annotate(document)
    document.column("head"), document.column("deprel")
    ```

=== "Result"

    ```
    ([2, 3, 0, 5, 3, 3], ['det', 'nsubj', 'root', 'det', 'obj', 'punct'])
    ```

</div>

<div class="metric-card" markdown>

### Parsing a sentence { #parse }

`parse` · `list[tuple[int, str]]`
{ .metric-meta }

``` {.python .signature}
parse(words, upos, feats, *, probs=False)
```

The head and the relation of every word of the sentence in the same order; an empty sentence gives an empty list. The words come with their part of speech and features in the UD annotation, as esMorph gives them. The part of speech is one of the 17 UD parts of speech in capitals (`NOUN`, `VERB`, `X`): with other tags, lowercase or the EAGLES tags of AnCora for example, the model would parse almost at random, so they are an error. The features are a CoNLL-U field (`Gender=Fem|Number=Sing`) or a dictionary, like `feats` of an esMorph analysis; `_`, an empty string, an empty dictionary or `None` mean no features. Features unknown to the model are skipped. The model is trained on the tags of esMorph with a part of the features dropped, so it does without some of them: without any features LAS on AnCora dev is about 0.9 points lower. Parsing runs without the GIL.

| Parameter | Type | Default | Description |
| :-------- | :--- | :------ | :---------- |
| `words` | `Iterable[str]` | - | The word forms |
| `upos` | `Iterable[str]` | - | The UD parts of speech |
| `feats` | `Iterable[str \| Mapping[str, str] \| None]` | - | The UD features of every word |
| `probs` | `bool` | `False` | Add the [probabilities](#probs) of the head and the relation: quadruples instead of pairs |

Exceptions:

- `ValueError` - the lengths of `words`, `upos` and `feats` differ, or a part of speech is not one of the 17 UD parts of speech;
- `TypeError` - the input is not a collection of strings (a string instead of a list is an error too) or `probs` is not a bool.

=== "Code"

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

=== "Result"

    ```
    [(2, 'nsubj'), (0, 'root'), (4, 'det'), (2, 'obj')]
    ```

If the text is already split into words, esMorph gives them the morphology in context: the first analysis of every word is the one its context model chose.

=== "Code"

    ``` python
    from esmorph import Analyzer

    words = ["Los", "niños", "juegan", "en", "el", "parque", "."]
    best = [analyses[0] for analyses in Analyzer().analyze_sentence(words)]
    parser.parse(words, [a.pos for a in best], [a.feats for a in best])
    ```

=== "Result"

    ```
    [(2, 'det'), (3, 'nsubj'), (0, 'root'), (6, 'case'), (6, 'det'), (3, 'obl'), (3, 'punct')]
    ```

</div>

<div class="metric-card" markdown>

### Parsing many sentences { #parse_many }

`parse_many` · `list[list[tuple[int, str]]]`
{ .metric-meta }

``` {.python .signature}
parse_many(sentences, *, probs=False)
```

The same as `parse` for every sentence, but faster: sentences of close lengths are parsed four at a time. A sentence is a triple (forms, parts of speech, features); `probs=True` adds the [probabilities](#probs), as in `parse`. Parsing runs without the GIL in chunks of 256 sentences; Ctrl+C works between them.

| Parameter | Type | Default | Description |
| :-------- | :--- | :------ | :---------- |
| `sentences` | `Iterable[tuple[Iterable[str], Iterable[str], Iterable[str \| Mapping[str, str] \| None]]]` | - | The sentences, as `parse` takes them |
| `probs` | `bool` | `False` | Add the probabilities of the head and the relation |

Exceptions: `ValueError` - a sentence is not three collections, their lengths differ, or a part of speech is not one of the 17 UD parts of speech; `TypeError` - the input is not a collection of strings or `probs` is not a bool.

=== "Code"

    ``` python
    parser.parse_many(
        [
            (["¡", "Hola", "!"], ["PUNCT", "INTJ", "PUNCT"], [None, None, None]),
            (["Llueve", "mucho"], ["VERB", "ADV"], [{"Mood": "Ind", "Person": "3"}, "_"]),
        ]
    )
    ```

=== "Result"

    ```
    [[(2, 'punct'), (0, 'root'), (2, 'punct')], [(0, 'root'), (1, 'advmod')]]
    ```

</div>

## Probabilities { #probs }

With `probs=True` every word has, besides its head and relation, two probabilities from the model: `head_prob` of the head among all the words of the sentence and the root (in a sentence longer than 1024 words, among the candidates of the [window](#tree) and the head given by building the tree), and `deprel_prob` of the relation given this head among the relations other than `root`; the `root` relation of the root is set by the [rule](#tree), and its probability is 1. Their product is the probability that the relation is right as a whole. The probabilities tell reliable relations from doubtful ones: on AnCora dev the head is right for 98.7 % of the words with `head_prob` from 0.99 (74 % of the words) and for 38 % of the words below 0.5 (2 %). The probabilities are local - per word, not per tree - and somewhat high: on AnCora dev the mean `head_prob` is 2.8 points above the share of right heads, and the mean product 2.9 points above the share of right relations with their subtypes. On GSD dev, which the model parses with the conventions of AnCora, the gap is wider: 6.0 and 10.2 points.

=== "Code"

    ``` python
    words = ["Vi", "a", "la", "niña", "con", "el", "telescopio", "."]
    best = [analyses[0] for analyses in Analyzer().analyze_sentence(words)]
    relations = parser.parse(words, [a.pos for a in best], [a.feats for a in best], probs=True)
    [
        (word, head, deprel, round(p, 2), round(q, 2))
        for word, (head, deprel, p, q) in zip(words, relations)
    ]
    ```

=== "Result"

    ```
    [('Vi', 0, 'root', 1.0, 1.0), ('a', 4, 'case', 1.0, 1.0), ('la', 4, 'det', 1.0, 1.0), ('niña', 1, 'obj', 1.0, 0.49), ('con', 7, 'case', 1.0, 1.0), ('el', 7, 'det', 1.0, 1.0), ('telescopio', 1, 'obl', 0.81, 0.9), ('.', 1, 'punct', 1.0, 1.0)]
    ```

The telescope may be the girl's: the head of `telescopio` is `Vi` with probability 0.81, and the relation `obj` of `niña` has only 0.49.

## The parse tree { #tree }

Every word has one head, a sentence has one root, and there are no cycles; non-projective trees (crossing relations) are allowed. The parser picks the tree with the highest sum of head scores (the Chu - Liu - Edmonds algorithm). For degenerate sentences, where the best heads give more than 16 cycles or 8 root candidates, the tree is built faster: the extra roots and the nodes of cycles are attached to the best root. The tree of a sentence longer than 1024 words is built the same way - a text without punctuation, for example, which the segmenter does not split into sentences; the head of a word in it is looked for among 64 words on each side and the root, so the parsing time grows linearly with the length. The relations come with subtypes, as in the UD annotation of AnCora (`nsubj:pass`, `obl:arg`, `expl:pv`); only the root has the `root` relation; the CoNLL 2018 evaluation compares the relation without the subtype.

## Threads and processes { #threads }

The parser does not change while parsing: one parser can be shared between threads, and parsing runs without the GIL, so the threads parse in parallel. On Python 3.14t and 3.15t without the GIL the module does not enable the GIL. The parser moves to another process with pickle: the absolute path to the model, or the mark of the package model, is saved. `copy.copy` and `copy.deepcopy` return the same object. Parsers are equal if their model comes from the same file (also by another path or link) that did not change between their creation, or both use the package model; a parser can be held by a weak reference (`weakref`).

=== "Code"

    ``` python
    from concurrent.futures import ThreadPoolExecutor

    texts = ["Llueve.", "Mi madre lava la ropa."]
    with ThreadPoolExecutor(2) as pool:
        documents = list(pool.map(parser.parse_text, texts))
    [document.column("deprel") for document in documents]
    ```

=== "Result"

    ```
    [['root', 'punct'], ['det', 'nsubj', 'root', 'det', 'obj', 'punct']]
    ```
