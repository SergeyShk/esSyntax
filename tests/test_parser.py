import copy
import os
import pickle
import re
import shutil
import sys
import threading
import weakref
import zlib
from pathlib import Path

import pytest
from anyseg import Document, Segmenter, read_conllu
from esmorph import Analyzer

from essyntax import Parser

ROOT = Path(__file__).parents[1]
MODEL = ROOT / "data" / "es-syntax.bin"
WORDS = ["La", "niña", "lee", "un", "libro", "."]
UPOS = ["DET", "NOUN", "VERB", "DET", "NOUN", "PUNCT"]
# Features as esMorph gives them: with cut features the model parses worse
FEATS = [
    "Definite=Def|Gender=Fem|Number=Sing|PronType=Art",
    "Gender=Fem|Number=Sing",
    "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin",
    "Definite=Ind|Gender=Masc|Number=Sing|PronType=Art",
    "Gender=Masc|Number=Sing",
    None,
]


@pytest.fixture(scope="module")
def parser():
    return Parser()


def is_tree(relations):
    heads = [relation[0] for relation in relations]
    if heads.count(0) != 1 or any(not 0 <= head <= len(heads) for head in heads):
        return False
    for start in range(1, len(heads) + 1):
        node, steps = start, 0
        while node and steps <= len(heads):
            node, steps = heads[node - 1], steps + 1
        if node:
            return False
    return True


def sentence_relations(document):
    heads, deprels = document.column("head"), document.column("deprel")
    return [
        [(heads[word.index], deprels[word.index]) for word in sentence.words]
        for sentence in document.sentences
    ]


def test_parse(parser):
    relations = parser.parse(WORDS, UPOS, FEATS)
    assert relations == [
        (2, "det"),
        (3, "nsubj"),
        (0, "root"),
        (5, "det"),
        (3, "obj"),
        (3, "punct"),
    ]
    assert all(deprel in parser.relations for _, deprel in relations)


def test_parse_empty_and_unknown_feats(parser):
    assert parser.parse([], [], []) == []
    relations = parser.parse(["Ñandú", "", "zzz"], ["NOUN", "X", "X"], ["Bar=Baz", "", "_"])
    assert is_tree(relations)


def test_parse_feats_mapping(parser):
    expected = parser.parse(WORDS, UPOS, FEATS)
    # The same features as a mapping with the keys in reverse order: the notation is ordered
    feats = [
        dict(reversed([pair.split("=") for pair in text.split("|")])) if text else {}
        for text in FEATS
    ]
    assert list(feats[0]) == ["PronType", "Number", "Gender", "Definite"]
    assert parser.parse(WORDS, UPOS, feats) == expected
    with pytest.raises(TypeError, match="the features of word 0 and their values must be strings"):
        parser.parse(["niña"], ["NOUN"], [{"Number": 1}])
    with pytest.raises(TypeError, match="item 0 must be a string, a mapping or None, not int"):
        parser.parse(["niña"], ["NOUN"], [5])


def test_parse_esmorph_analyses(parser):
    # Ready words: the tags of esMorph in context, the features as a mapping
    words = ["El", "gato", "duerme", "en", "el", "sofá", "."]
    best = [analyses[0] for analyses in Analyzer().analyze_sentence(words)]
    relations = parser.parse(words, [a.pos for a in best], [a.feats for a in best])
    document = parser.parse_text("El gato duerme en el sofá.")
    assert relations == list(zip(document.column("head"), document.column("deprel"), strict=True))


def test_root_relation_only_at_root(parser):
    for text in ["!!! ??? ... --- *** +++", "La niña lee un libro."]:
        document = parser.parse_text(text)
        heads, deprels = document.column("head"), document.column("deprel")
        assert all(
            (head == 0) == (deprel == "root") for head, deprel in zip(heads, deprels, strict=True)
        )


def test_long_sentence(parser):
    # A sentence longer than 1024 words: the head is looked for in a window, the time grows linearly
    words = (["la", "niña", "lee", "un", "libro", "y", "el", "niño", "come", "pan"] * 400)[:4000]
    upos = ["DET", "NOUN", "VERB", "DET", "NOUN", "CCONJ", "DET", "NOUN", "VERB", "NOUN"] * 400
    relations = parser.parse(words, upos[:4000], [None] * 4000)
    assert len(relations) == 4000
    assert is_tree(relations)


def test_parse_accepts_tuples_and_generators(parser):
    expected = parser.parse(WORDS, UPOS, FEATS)
    assert parser.parse(tuple(WORDS), (u for u in UPOS), FEATS) == expected


def test_parse_probs(parser):
    plain = parser.parse(WORDS, UPOS, FEATS)
    scored = parser.parse(WORDS, UPOS, FEATS, probs=True)
    assert [(head, deprel) for head, deprel, _, _ in scored] == plain
    for head, _, head_prob, deprel_prob in scored:
        assert isinstance(head_prob, float) and isinstance(deprel_prob, float)
        assert 0 < head_prob <= 1 and 0 < deprel_prob <= 1
        # The relation root of the root comes from a rule
        assert head != 0 or deprel_prob == 1
    assert parser.parse_many([(WORDS, UPOS, FEATS)] * 2, probs=True) == [scored, scored]
    assert parser.parse([], [], [], probs=True) == []
    # A doubtful head: "con el telescopio" goes with "vi" or with "niña"
    words = ["Vi", "a", "la", "niña", "con", "el", "telescopio"]
    upos = ["VERB", "ADP", "DET", "NOUN", "ADP", "DET", "NOUN"]
    feats = ["Tense=Past", None, "Gender=Fem", "Gender=Fem", None, "Gender=Masc", "Gender=Masc"]
    assert parser.parse(words, upos, feats, probs=True)[6][2] < 0.9


def test_probs_type(parser):
    for value in (1, "yes"):
        name = type(value).__name__
        with pytest.raises(TypeError, match=f"probs must be a bool, not {name}"):
            parser.parse(WORDS, UPOS, FEATS, probs=value)
        with pytest.raises(TypeError, match="probs must be a bool"):
            parser.parse_many([(WORDS, UPOS, FEATS)], probs=value)
    assert parser.parse(WORDS, UPOS, FEATS, probs=False) == parser.parse(WORDS, UPOS, FEATS)


def test_parse_many_matches_parse(parser):
    sentences = [
        (WORDS, UPOS, FEATS),
        ([], [], []),
        (["¡", "Hola", "!"], ["PUNCT", "INTJ", "PUNCT"], ["_", "_", "_"]),
        (["casa"] * 40, ["NOUN"] * 40, ["Gender=Fem|Number=Sing"] * 40),
    ]
    many = parser.parse_many(sentences)
    assert many == [parser.parse(*sentence) for sentence in sentences]
    assert parser.parse_many([]) == []
    assert parser.parse_many(iter(sentences[:1])) == many[:1]


@pytest.mark.parametrize(
    ("args", "error", "message"),
    [
        (("La niña", ["NOUN"], ["_"]), TypeError, "not a string"),
        ((["niña"], ["NOUN", "VERB"], ["_"]), ValueError, "1 words, 2 parts of speech"),
        (([1], ["NOUN"], ["_"]), TypeError, "item 0 must be a string, not int"),
        ((["niña"], [None], ["_"]), TypeError, "must be a string, not NoneType"),
        ((5, [], []), TypeError, "expected a collection of strings, not int"),
        ((["niña"], ["noun"], ["_"]), ValueError, "unknown part of speech 'noun' of word 0"),
        (
            (["niña", "-"], ["NOUN", "PNCT"], ["_", "_"]),
            ValueError,
            "'PNCT' of word 1: expected one of the 17",
        ),
        ((["niña"], [""], ["_"]), ValueError, "unknown part of speech '' of word 0"),
    ],
)
def test_parse_errors(parser, args, error, message):
    with pytest.raises(error, match=message):
        parser.parse(*args)


@pytest.mark.parametrize(
    ("sentences", "error", "message"),
    [
        (5, TypeError, "Expected a collection of sentences, not int"),
        (["abc"], TypeError, "Sentence 0 must be a triple, not str"),
        ([(WORDS, UPOS)], ValueError, "got 2 items"),
        ([(WORDS, UPOS, FEATS[:2])], ValueError, "Every word of sentence 0 .*2 features"),
        (
            [(WORDS, UPOS, FEATS), (["La", "niña"], ["DET", "noun"], ["_", "_"])],
            ValueError,
            "'noun' of word 1 of sentence 1:",
        ),
    ],
)
def test_parse_many_errors(parser, sentences, error, message):
    with pytest.raises(error, match=message):
        parser.parse_many(sentences)


def test_annotate(parser):
    document = Analyzer().annotate(Segmenter("es").segment("La niña lee un libro. ¡Gracias!"))
    parser.annotate(document)
    relations = sentence_relations(document)
    assert all(is_tree(sentence) for sentence in relations)
    upos, feats = document.column("upos"), document.column("feats")
    expected = parser.parse_many(
        (
            [word.form for word in sentence.words],
            [upos[word.index] for word in sentence.words],
            [feats[word.index] for word in sentence.words],
        )
        for sentence in document.sentences
    )
    assert relations == expected
    # Parsing again replaces the columns with the same values
    parser.annotate(document)
    assert sentence_relations(document) == expected


def test_annotate_multiword_tokens(parser):
    # esMorph splits a verb with clitics into a new document; contractions are split by anySeg
    segmented = Segmenter("es").segment("Pónganselo ya. Voy al cine.")
    document = Analyzer().annotate(segmented)
    assert document is not segmented
    parser.annotate(document)
    assert [token.text for token in document.multiword_tokens] == ["Pónganselo", "al"]
    assert all(is_tree(sentence) for sentence in sentence_relations(document))
    lines = document.to_conllu().splitlines()
    assert "1-3\tPónganselo\t_\t_\t_\t_\t_\t_\t_\t_" in lines
    assert "2-3\tal\t_\t_\t_\t_\t_\t_\t_\t_" in lines
    assert [line.split("\t")[1] for line in lines if re.match(r"\d+\t", line)][:3] == [
        "Pongan",
        "se",
        "lo",
    ]


def test_annotate_empty_document(parser):
    document = Segmenter("es").segment("")
    parser.annotate(document)
    assert document.column("head") == []


def test_annotate_needs_morphology(parser):
    document = Segmenter("es").segment("La niña lee un libro.")
    with pytest.raises(ValueError, match=r"esmorph\.Analyzer\(\)\.annotate"):
        parser.annotate(document)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("La niña lee.", "not a string: parse_text parses text"),
        (5, "Expected an anySeg document or an object with column, sentences and set_columns"),
    ],
)
def test_annotate_not_document(parser, document, message):
    with pytest.raises(TypeError, match=message):
        parser.annotate(document)


class Word:
    def __init__(self, index):
        self.index = index


class Sentence:
    def __init__(self, indices):
        self.words = [Word(i) for i in indices]


class FakeDocument:
    """A document by the protocol of anySeg: the columns and the sentences are given"""

    def __init__(self, sentences, upos=None):
        self.forms = WORDS[:4]
        self.upos = upos or UPOS[:4]
        self.sentences = sentences
        self.columns = {}

    def column(self, name):
        return {"form": self.forms, "upos": self.upos, "feats": FEATS[:4]}[name]

    def set_columns(self, **columns):
        self.columns = columns


def test_annotate_protocol(parser):
    document = FakeDocument([Sentence([0, 1]), Sentence([2, 3])])
    parser.annotate(document)
    assert set(document.columns) == {"head", "deprel"}
    assert len(document.columns["head"]) == 4


@pytest.mark.parametrize(
    "sentences",
    [
        [Sentence([0, 1]), Sentence([3])],
        [Sentence([0, 1])],
        [Sentence([1, 2, 3])],
        [Sentence([0, 1, 2, 3]), Sentence([4])],
    ],
)
def test_annotate_unordered(parser, sentences):
    with pytest.raises(ValueError, match="do not follow each other"):
        parser.annotate(FakeDocument(sentences))


def test_annotate_bad_types(parser):
    document = FakeDocument([Sentence([0, 1, 2, 3])])
    document.sentences[0].words[0].index = "0"
    with pytest.raises(TypeError, match="The index of a word must be an integer, not str"):
        parser.annotate(document)
    document = FakeDocument([Sentence([0, 1, 2, 3])], upos=["DET", 5, "VERB", "DET"])
    with pytest.raises(TypeError, match="upos: item 1"):
        parser.annotate(document)
    document = FakeDocument(5)
    with pytest.raises(
        TypeError, match="The sentences of the document must be a collection, not int"
    ):
        parser.annotate(document)


def test_annotate_bad_columns(parser):
    document = FakeDocument([Sentence([0, 1, 2, 3])], upos=["DET", "noun", "VERB", "DET"])
    with pytest.raises(ValueError, match="unknown part of speech 'noun' of word 1"):
        parser.annotate(document)
    document = FakeDocument([Sentence([0, 1, 2, 3])], upos=["DET", "_", "VERB", "DET"])
    with pytest.raises(ValueError, match="have no parts of speech"):
        parser.annotate(document)
    document = FakeDocument([Sentence([0, 1, 2])], upos=["DET", "NOUN", "VERB"])
    with pytest.raises(ValueError, match="different lengths: form 4, upos 3, feats 4"):
        parser.annotate(document)


def test_surrogates(parser):
    # anySeg and esMorph pass a lone surrogate, and so does the parser
    document = parser.parse_text("La niña \ud800 lee.")
    assert len(document.column("head")) == len(document.column("form"))
    assert is_tree(parser.parse(["niña", "\ud800"], ["NOUN", "X"], ["_", "_"]))


def test_annotate_generator_columns(parser):
    document = FakeDocument([Sentence([0, 1, 2, 3])])
    document.column = lambda name: iter({"form": WORDS, "upos": UPOS, "feats": FEATS}[name][:4])
    parser.annotate(document)
    assert len(document.columns["head"]) == 4


class Index:
    """An integer by the protocol __index__, as numpy.int64"""

    def __init__(self, value):
        self.value = value

    def __index__(self):
        return self.value


def test_annotate_index_kinds(parser):
    document = FakeDocument([Sentence([0, 1, 2, 3])])
    document.sentences[0].words[0].index = Index(0)
    parser.annotate(document)
    assert len(document.columns["head"]) == 4
    for huge in (2**64, -(2**64), -1):
        document.sentences[0].words[0].index = huge
        with pytest.raises(ValueError, match="do not follow each other"):
            parser.annotate(document)


def test_parse_text(parser):
    document = parser.parse_text("La niña lee un libro.")
    assert isinstance(document, Document)
    assert [(w.form, w.upos, w.head, w.deprel) for w in document.words] == [
        ("La", "DET", 2, "det"),
        ("niña", "NOUN", 3, "nsubj"),
        ("lee", "VERB", 0, "root"),
        ("un", "DET", 5, "det"),
        ("libro", "NOUN", 3, "obj"),
        (".", "PUNCT", 3, "punct"),
    ]
    with pytest.raises(TypeError, match="The text must be a string, not bytes"):
        parser.parse_text(b"text")


def test_parse_text_multiword_tokens(parser):
    # The document that esMorph returns with the words of the tokens it splits is parsed
    text = "Pónganselo ya.\n\nVoy al cine."
    document = parser.parse_text(text)
    expected = Analyzer().annotate(Segmenter("es").segment(text))
    parser.annotate(expected)
    assert document.to_conllu() == expected.to_conllu()
    assert [word.form for word in document.words][:3] == ["Pongan", "se", "lo"]
    assert [token.text for token in document.multiword_tokens] == ["Pónganselo", "al"]
    assert all(is_tree(sentence) for sentence in sentence_relations(document))


def test_parse_text_with_own_tools(parser):
    text = "Llamó el sarg. Pérez."
    assert len(parser.parse_text(text).sentences) == 2
    segmenter = Segmenter("es", abbreviations=["sarg."])
    document = parser.parse_text(text, segmenter=segmenter)
    assert len(document.sentences) == 1
    assert [word.head for word in document.words].count(0) == 1

    class Recording:
        # An analyzer with the same annotate: parse_text calls this one
        def __init__(self):
            self.calls, self.analyzer = 0, Analyzer()

        def annotate(self, document):
            self.calls += 1
            return self.analyzer.annotate(document)

    analyzer = Recording()
    assert parser.parse_text(text, analyzer=analyzer).words[0].upos == "VERB"
    assert analyzer.calls == 1
    parser.parse_text(text, segmenter=segmenter, analyzer=analyzer)
    assert analyzer.calls == 2

    class InPlace:
        # annotate fills the given document and returns None
        def annotate(self, document):
            Analyzer().annotate(document)

    document = parser.parse_text("El gato duerme.", analyzer=InPlace())
    assert document.column("head").count(0) == 1
    with pytest.raises(
        TypeError, match=r"segmenter: expected an anySeg segmenter .*, not Analyzer"
    ):
        parser.parse_text(text, segmenter=Analyzer())
    with pytest.raises(
        TypeError, match=r"analyzer: expected an esMorph analyzer .*, not Segmenter"
    ):
        parser.parse_text(text, analyzer=segmenter)

    class Wrong:
        def segment(self, text):
            return text

        def annotate(self, document):
            return "done"

    with pytest.raises(TypeError, match="segment must return an anySeg document, not str"):
        parser.parse_text(text, segmenter=Wrong())
    with pytest.raises(
        TypeError, match="annotate must return an anySeg document or None, not str"
    ):
        parser.parse_text(text, analyzer=Wrong())


def test_model_from_path(tmp_path, parser):
    custom = Parser(MODEL)
    assert custom.path == MODEL
    assert repr(custom) == f"Parser({str(MODEL)!r})"
    assert custom.parse(WORDS, UPOS, FEATS) == parser.parse(WORDS, UPOS, FEATS)
    assert repr(parser) == "Parser()"
    assert parser.path is None


def test_relative_model_path(tmp_path, monkeypatch):
    shutil.copyfile(MODEL, tmp_path / "model.bin")
    monkeypatch.chdir(tmp_path)
    custom = Parser("model.bin")
    assert custom.path == Path.cwd() / "model.bin"
    data = pickle.dumps(custom)
    monkeypatch.chdir(tmp_path.parent)
    assert pickle.loads(data).path == custom.path


def test_changed_model_file_is_reloaded(tmp_path):
    model = tmp_path / "model.bin"
    shutil.copyfile(MODEL, model)
    first = Parser(model)
    model.write_bytes(b"not a model")
    with pytest.raises(ValueError, match="no signature"):
        Parser(model)
    assert first.parse(WORDS, UPOS, FEATS)


@pytest.mark.parametrize(
    ("path", "error", "message"),
    [
        (5, TypeError, "The path to the model must be a string or os.PathLike, not int"),
        (b"model.bin", TypeError, "not bytes"),
        ("model\0.bin", ValueError, "NUL character"),
    ],
)
def test_model_path_errors(path, error, message):
    with pytest.raises(error, match=message):
        Parser(path)


def test_model_errors(tmp_path):
    missing = tmp_path / "ningún.bin"
    with pytest.raises(FileNotFoundError, match="No model file") as error:
        Parser(missing)
    assert error.value.errno == 2
    assert error.value.filename == str(missing)
    damaged = tmp_path / "damaged.bin"
    data = bytearray(MODEL.read_bytes())
    data[-1] ^= 1
    damaged.write_bytes(bytes(data))
    with pytest.raises(ValueError, match=f"{re.escape(str(damaged))}: .*checksum"):
        Parser(damaged)
    other = tmp_path / "other.bin"
    other.write_bytes(b"not a model")
    with pytest.raises(ValueError, match="no signature"):
        Parser(other)


def test_sources(parser):
    sources = parser.sources
    assert sources["ud"] == "r2.19"
    # The weights take the licenses of the training treebanks: CC BY-SA 4.0 of GSD
    assert sources["licenses"] == {
        "UD_Spanish-AnCora": "CC BY 4.0",
        "UD_Spanish-GSD": "CC BY-SA 4.0",
    }
    # The model parses every text by the conventions of AnCora
    assert sources["treebank_marker"] == "AnCora"
    assert sources["tags"].startswith("esmorph ")
    # The tag noise of train is by treebank, as in scripts/train.py
    assert set(sources["noise"]) == {"ancora", "gsd"}
    # The checksum is the CRC32 of the file after the header of 16 bytes
    assert sources["crc32"] == f"{zlib.crc32(MODEL.read_bytes()[16:]):08x}"


def test_equality_and_weakref(tmp_path, parser):
    assert Parser() == parser
    assert hash(Parser()) == hash(parser)
    model = tmp_path / "model.bin"
    shutil.copyfile(MODEL, model)
    assert Parser(model) == Parser(model)
    assert hash(Parser(model)) == hash(Parser(model))
    assert Parser(model) != parser
    assert parser != "Parser()"
    assert pickle.loads(pickle.dumps(parser)) == parser
    assert weakref.ref(parser)() is parser
    # Another path to the same file and a symbolic link are the same model
    (tmp_path / "x").mkdir()
    other = Parser(tmp_path / "x" / ".." / "model.bin")
    assert other == Parser(model) and hash(other) == hash(Parser(model))
    if sys.platform != "win32":
        (tmp_path / "link.bin").symlink_to(model)
        assert Parser(tmp_path / "link.bin") == Parser(model)
        os.link(model, tmp_path / "hard.bin")
        assert Parser(tmp_path / "hard.bin") == Parser(model)
    # A changed file is another model
    before = Parser(model)
    os.utime(model, (1, 1))
    assert Parser(model) != before


def test_esmorph_tags_match_training():
    # The model is trained on the tags of the esMorph version of sources: the installed esMorph must
    # give the same. The file has heads, so esMorph keeps its words and tags them by their tokens
    (document,) = read_conllu((ROOT / "data" / "check.conllu").read_text(encoding="utf-8"))
    upos, feats = document.column("upos"), document.column("feats")
    tagged = Analyzer().annotate(document)
    pairs = list(zip(upos, feats, tagged.column("upos"), tagged.column("feats"), strict=True))
    total = len(pairs)
    upos_diff = sum(before != after for before, _, after, _ in pairs)
    feats_diff = sum(before != after for _, before, _, after in pairs)
    assert total > 4000
    assert upos_diff <= total * 0.005, f"parts of speech differ in {upos_diff} of {total} words"
    assert feats_diff <= total * 0.005, f"features differ in {feats_diff} of {total} words"


def test_pickle_and_copy(tmp_path, parser):
    assert copy.copy(parser) is parser
    assert copy.deepcopy(parser) is parser
    restored = pickle.loads(pickle.dumps(parser))
    assert restored.path is None
    assert restored.parse(WORDS, UPOS, FEATS) == parser.parse(WORDS, UPOS, FEATS)
    model = tmp_path / "model.bin"
    shutil.copyfile(MODEL, model)
    custom = pickle.loads(pickle.dumps(Parser(model)))
    assert custom.path == model


def test_threads(parser):
    expected = parser.parse(WORDS, UPOS, FEATS)
    results = []

    def work():
        results.extend(parser.parse(WORDS, UPOS, FEATS) == expected for _ in range(50))

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 400 and all(results)
