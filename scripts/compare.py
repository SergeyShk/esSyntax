# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#     "spacy==3.8.16",
#     "spacy-curated-transformers==0.3.1",
#     "stanza==1.15.0",
#     "torch==2.14.1",
#     "transformers==4.57.6",
#     "ufal.udpipe==1.4.0.1",
# ]
# ///
"""
Comparison of esSyntax with other dependency parsers: UAS and LAS on UD treebanks and speed

Description:
    Systems: esSyntax, spaCy (es_core_news_sm, es_core_news_md, es_core_news_lg and
    es_dep_news_trf), Stanza (the packages default, ancora and default_accurate) and UDPipe 1 (the
    AnCora model of UD 2.5).

    Downloads the test parts of UD_Spanish-AnCora, UD_Spanish-GSD, UD_Spanish-PUD and
    UD_Spanish-COSER of a pinned UD 2.19 release, the official CoNLL 2018 evaluation script and
    the models of the systems with their SHA-256 checked into the data directory. Stanza downloads
    its models itself (the files of the v1.15.0 tag of stanfordnlp/stanza-es on Hugging Face, the
    version is set by the package), and the script checks their SHA-256 (`STANZA_FILES`); the
    transformer of default_accurate is a pinned Hugging Face commit (`BERT`).

    Every system parses the sets in two modes. tok - the gold words and sentences (`del` as `de`
    and `el`) with the own morphology of the system; esSyntax annotates an anySeg document of the
    gold tokens, a multiword token with its gold words, with esMorph tags in context. raw - the
    raw text: `# text` of the sentences joined by spaces, paragraphs (`# newpar`, `# newdoc`)
    apart; the system gets the text paragraph by paragraph and splits it itself (esSyntax -
    parse_text: anySeg and esMorph). Heads that do not make a tree with one root are repaired
    (`repair`), the number of repairs goes into the results; the multiword tokens of the gold
    words or of the system are written with the parse. Scores - evaluate of the CoNLL 2018 script:
    UAS and LAS, for raw text also the F1 of words and sentences. Quality is measured in the main
    process with the number of threads the library chooses.

    Speed is measured after quality, every system in its own process in one thread, once the
    1-minute load average is below `--max-load`: words per second on the gold words of AnCora
    test without loading, the best of two runs (esSyntax together with esMorph tags; slow systems -
    the first sentences, `SPEED_WORDS`), the time of import and loading (together with the parse
    of the first sentence: some systems load at the first parse), the peak memory of the process
    (RSS) and the load average before and after.

    Writes results.json (a run of some systems, `--systems`, updates only their results),
    environment.json, the tables tables.md and tables.es.md and the parses in pred/ into the data
    directory; `--skip quality` or `--skip speed` skips a measurement, `--report` makes the tables
    from results.json. The versions of the packages are pinned in compare.py.lock. esSyntax is
    measured from a wheel built from the repository: it is given with `--with`, and esmorph and
    anyseg are pinned there too (their versions go into results.json). A `--with-editable` build
    is a debug one, its speed is not representative.

Example:
    rm -rf target/compare/wheels
    uvx maturin@1.15.0 build --release --locked -o target/compare/wheels
    uvx uv@0.13.5 run --with target/compare/wheels/essyntax-*.whl --with esmorph==0.6.0 \\
        --with anyseg==0.5.0 scripts/compare.py target/compare
"""

import argparse
import functools
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

# Set: treebank, test file, commit of the UD 2.19 release and SHA-256
DATASETS = {
    "AnCora": (
        "UD_Spanish-AnCora",
        "es_ancora-ud-test.conllu",
        "bdb41b5f95db8e0a64217fcb8d15cd3ad38c34db",
        "4d74d95cfe5a53eacaa7adf3b7ae6ef76a7df9806fd519113e25d74c43ad2b9c",
    ),
    "GSD": (
        "UD_Spanish-GSD",
        "es_gsd-ud-test.conllu",
        "c262f3ca7897ea3b7719731d5958948614e3a214",
        "f6a7a64c61a089f311bc8299f87e62f3af5c92d444a5d51681d1fa42234dca95",
    ),
    "PUD": (
        "UD_Spanish-PUD",
        "es_pud-ud-test.conllu",
        "e7ae2691ecf36988467016f57647dffb43d047bd",
        "542ab95a9240fb66ade9d3d234fc34dfd0d5b041bdd304f005ce3573d93418c7",
    ),
    "COSER": (
        "UD_Spanish-COSER",
        "es_coser-ud-test.conllu",
        "06f18e8286d5c1c042bfc218c1bf567af7307959",
        "546565e466048e4c9c2c455d4873fc8a2902594a3ddcf176ab542ae42cab8648",
    ),
}
SPACY_URL = "https://github.com/explosion/spacy-models/releases/download/{0}/{0}-py3-none-any.whl"
# Models of spaCy by system: package and version
SPACY_MODELS = {
    "spacy-sm": "es_core_news_sm-3.8.0",
    "spacy-md": "es_core_news_md-3.8.0",
    "spacy-lg": "es_core_news_lg-3.8.0",
    "spacy-trf": "es_dep_news_trf-3.8.0",
}
UDPIPE_MODEL = "spanish-ancora-ud-2.5-191206.udpipe"
# Files: address and SHA-256
DOWNLOADS = {
    "conll18_ud_eval.py": (
        "https://universaldependencies.org/conll18/conll18_ud_eval.py",
        "1072e02af00b1a56205b5e8216d51dee9b8944a104d80744afaccc78859fcb16",
    ),
    "es_core_news_sm-3.8.0-py3-none-any.whl": (
        SPACY_URL.format("es_core_news_sm-3.8.0"),
        "e451a83d6df79b87e9eed0cb553f03e99e36a3bab18a7b79f0dcfd1fdf875e12",
    ),
    "es_core_news_md-3.8.0-py3-none-any.whl": (
        SPACY_URL.format("es_core_news_md-3.8.0"),
        "478b8bb3f3e8eb149192f7d80e7cd64f990b7e9bccbc5329df41a57e86326be2",
    ),
    "es_core_news_lg-3.8.0-py3-none-any.whl": (
        SPACY_URL.format("es_core_news_lg-3.8.0"),
        "7c6c212715a12f31aacde3361754436945ff7376fb24cde57d0c277c9c9b050b",
    ),
    "es_dep_news_trf-3.8.0-py3-none-any.whl": (
        SPACY_URL.format("es_dep_news_trf-3.8.0"),
        "afe76019ca75827db18f14f282f4678b1544277b29dcba8011b400837b19dcb4",
    ),
    # LINDAT, Universal Dependencies 2.5 Models for UDPipe (2019-12-06), hdl:11234/1-3131
    UDPIPE_MODEL: (
        "https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/"
        "52474ca8-939b-4fcf-80b0-228679464582/content",
        "eb7c37977de18072d1f63740c06c588620d48b51dc0c0d0a3604a21db12600fc",
    ),
}
# Vectors and character language models shared by the Stanza packages
STANZA_SHARED = {
    "es/pretrain/conll17.pt": "d0c4fbb5a061f5fcca8855efbae04358313a1f00526e1a744986f5180c80846b",
    "es/forward_charlm/newswiki.pt": "a8edffc309f86e8e31212eb15f90f188af2f93132d55a4dff17680d06308d2ea",
    "es/backward_charlm/newswiki.pt": "bc1892d2d044c13668f449621cd85fac14e698aed107f9eea8fcae8f16fb595e",
}
# Files of the Stanza 1.15.0 models by package and their SHA-256
STANZA_FILES = {
    "default": {
        "es/tokenize/combined_nocharlm.pt": "ed4a59d0dc061e1e358480c78ef70a43c37322a7e36ac5b99c834800d48fd112",
        "es/mwt/combined.pt": "940f87ac09794f4dc3c9f0ede9916642df8f43067bf8202b766936ac360fe3eb",
        "es/pos/combined_charlm.pt": "8f720495414dc0edc28a4167826341e4165c0638335676e07251fdc4ceba37f4",
        "es/lemma/combined_nocharlm.pt": "acc745b47c4878d423a00bcb3b5d819cf3cbd043e7105981c690cf8079526b2e",
        "es/depparse/combined_charlm.pt": "9d83af22938e103c1cfbf678c117d8f9c2c06a03c8c5a17a26cdd9ce2ba1e3a4",
    }
    | STANZA_SHARED,
    "ancora": {
        "es/tokenize/ancora_nocharlm.pt": "a01efc3155794591baee08b6409c79613964daebcece71095a70ee7f2b6b9f8e",
        "es/mwt/ancora.pt": "5566c593a3be8d3e377f49109b275ed03bfd0f6ea5f579421bad46160472f58a",
        "es/pos/ancora_charlm.pt": "8ba215402de55642779b88986d9a29c6f747cbd7e23104ec5bbb26b682c80b10",
        "es/lemma/ancora_nocharlm.pt": "a8ed66d134e1ea78b359fb313650442e8fb4d7c9a356d5e59626881c341b9ec5",
        "es/depparse/ancora_charlm.pt": "19529e7689f75042f155b834df52f6c894278432b24e1eefdda9c9c582339605",
    }
    | STANZA_SHARED,
    "default_accurate": {
        "es/tokenize/combined_charlm.pt": "f94823633b8d24198f215d82a97745218b078bb9a142a9e032314f5e80926f5e",
        "es/mwt/combined.pt": "940f87ac09794f4dc3c9f0ede9916642df8f43067bf8202b766936ac360fe3eb",
        "es/pos/combined_bertin-roberta.pt": "d11b9be32c1f517f38ce025d008c996e83e3f69ee4ccd469cef37aa81b72b16a",
        "es/lemma/combined_charlm.pt": "081c24516c513faa67ed42b05bf80c9c783d549eb8bd97bf07ffbf2f3b20daec",
        "es/depparse/combined_bertin-roberta.pt": "1e9ba447db826e3a9c34b4eb3ae292a82dd684c27db8318ae9c5903b59f59e81",
    }
    | STANZA_SHARED,
}
# Stanza package by system
STANZA_PACKAGES = {
    "stanza": "default",
    "stanza-ancora": "ancora",
    "stanza-accurate": "default_accurate",
}
# Transformer of Stanza default_accurate: repository and commit on Hugging Face
BERT = ("bertin-project/bertin-roberta-base-spanish", "72b7e584ff8552880b39045a8bb80d86dcc27672")
STANZA_PROCESSORS = "tokenize,mwt,pos,lemma,depparse"
# Set of the speed measurement
SPEED_SET = "AnCora"
# Speed of slow systems - on the first sentences of AnCora test, at least so many words
SPEED_WORDS = {"stanza-accurate": 20_000}
# Variables of the number of threads: set for the process of the speed measurement before its start
THREADS = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "RAYON_NUM_THREADS": "1",
    "TOKENIZERS_PARALLELISM": "false",
}
MODES = ("tok", "raw")
METRICS = ("Tokens", "Sentences", "Words", "UAS", "LAS")


class Token(NamedTuple):
    form: str
    # Words of the token: more than one for a multiword token (`del` - `de`, `el`)
    words: list[str]
    # A space after the token: no SpaceAfter=No
    space: bool


@dataclass
class Sentence:
    tokens: list[Token] = field(default_factory=list)
    words: list[str] = field(default_factory=list)
    text: str = ""
    # The sentence starts a paragraph or a document
    paragraph: bool = False

    @property
    def multiword(self) -> list[tuple[int, int, str]]:
        """Multiword tokens: the numbers of the first and the last word (from 1) and the form"""
        result, count = [], 0
        for token in self.tokens:
            if len(token.words) > 1:
                result.append((count + 1, count + len(token.words), token.form))
            count += len(token.words)
        return result


# Word of a parse: form, head, relation
Word = tuple[str, int, str]


class Parsed(NamedTuple):
    """Parse of a sentence: the words and the multiword tokens (`Sentence.multiword`)"""

    words: list[Word]
    multiword: list[tuple[int, int, str]]


class System(NamedTuple):
    """Parse of the gold words with the own API of the system (its speed is measured), conversion
    of the answer into parses of the sentences and parse of raw text by paragraphs"""

    parse: Callable[[list[Sentence]], object]
    convert: Callable[[list[Sentence], object], list[Parsed]]
    text: Callable[[list[str]], list[Parsed]]


def sha256(path: Path) -> str:
    """
    SHA-256 of a file

    Arguments:
        path (Path): File

    Returns:
        str: Checksum in hexadecimal
    """
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, path: Path, digest: str) -> Path:
    """
    Download of a file with its checksum checked; a file with the right checksum is not
    downloaded again

    Arguments:
        url (str): Address of the file
        path (Path): Where to write
        digest (str): SHA-256 of the file

    Returns:
        Path: Path of the file

    Raises:
        ValueError: If the checksum does not match
    """
    if path.exists() and sha256(path) == digest:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "essyntax-compare"})
    with urllib.request.urlopen(request, timeout=300) as response, part.open("wb") as file:
        while chunk := response.read(1 << 20):
            file.write(chunk)
    if sha256(part) != digest:
        part.unlink()
        raise ValueError(f"{url}: the checksum does not match")
    part.replace(path)
    return path


def fetch(name: str, data: Path) -> Path:
    """File of `DOWNLOADS` in the data directory"""
    url, digest = DOWNLOADS[name]
    return download(url, data / name, digest)


def gold(dataset: str, data: Path) -> Path:
    """
    Test part of a set in the data directory

    Arguments:
        dataset (str): Set
        data (Path): Data directory

    Returns:
        Path: CoNLL-U file
    """
    treebank, name, commit, digest = DATASETS[dataset]
    url = f"https://raw.githubusercontent.com/UniversalDependencies/{treebank}/{commit}/{name}"
    return download(url, data / name, digest)


def sentences(path: Path) -> list[Sentence]:
    """
    Sentences of a CoNLL-U file: tokens and words without empty nodes

    Arguments:
        path (Path): CoNLL-U file

    Returns:
        list[Sentence]: Sentences
    """
    result: list[Sentence] = []
    current, last = Sentence(), 0
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            line = line.rstrip("\n")
            if not line:
                if current.words:
                    result.append(current)
                current, last = Sentence(), 0
            elif line.startswith("#"):
                if line.startswith("# text = "):
                    current.text = line.removeprefix("# text = ")
                current.paragraph |= line.startswith(("# newpar", "# newdoc"))
            else:
                cols = line.split("\t")
                space = "SpaceAfter=No" not in cols[9]
                if "-" in cols[0]:
                    last = int(cols[0].split("-")[1])
                    current.tokens.append(Token(cols[1], [], space))
                elif cols[0].isdigit():
                    current.words.append(cols[1])
                    if int(cols[0]) <= last:
                        current.tokens[-1].words.append(cols[1])
                    else:
                        current.tokens.append(Token(cols[1], [cols[1]], space))
    if current.words:
        result.append(current)
    return result


def paragraphs(text: list[Sentence]) -> list[str]:
    """
    Raw text of a set by paragraphs: `# text` of the sentences joined by spaces, a new paragraph -
    at `# newpar` and `# newdoc`

    Arguments:
        text (list[Sentence]): Sentences

    Returns:
        list[str]: Paragraphs
    """
    result: list[list[str]] = []
    for sentence in text:
        if sentence.paragraph or not result:
            result.append([])
        result[-1].append(sentence.text)
    return [joined for part in result if (joined := " ".join(part).strip())]


def repair(heads: list[int], deprels: list[str]) -> int:
    """
    Tree with one root from the heads: loops and heads outside the sentence become roots, extra
    roots and nodes of cycles go to the first root labeled root (or to the first root)

    Arguments:
        heads (list[int]): Heads of the words, changed in place
        deprels (list[str]): Relations, changed in place

    Returns:
        int: Number of repairs
    """
    count = len(heads)
    fixes = 0
    for index, head in enumerate(heads):
        if head < 0 or head > count or head == index + 1:
            heads[index] = 0
            fixes += 1
    roots = [index for index, head in enumerate(heads) if head == 0]
    if not roots:
        root = next((i for i, deprel in enumerate(deprels) if deprel.lower() == "root"), 0)
        heads[root] = 0
        roots = [root]
        fixes += 1
    root = next((i for i in roots if deprels[i].lower() == "root"), roots[0])
    for index in roots:
        if index != root:
            heads[index] = root + 1
            deprels[index] = "dep" if deprels[index].lower() == "root" else deprels[index]
            fixes += 1
    for start in range(count):
        seen, node = set(), start
        while heads[node] != 0:
            if node in seen:
                heads[node] = root + 1
                fixes += 1
                break
            seen.add(node)
            node = heads[node] - 1
    deprels[root] = "root"
    return fixes


def write(path: Path, parsed: list[Parsed]) -> int:
    """
    Parses into a CoNLL-U file: the form, head and relation of the words and the lines of the
    multiword tokens; the heads are repaired into a tree

    Arguments:
        path (Path): File
        parsed (list[Parsed]): Sentences

    Returns:
        int: Number of tree repairs
    """
    lines = []
    fixes = 0
    for sentence in parsed:
        if not sentence.words:
            continue
        heads = [head for _, head, _ in sentence.words]
        deprels = [deprel or "_" for _, _, deprel in sentence.words]
        fixes += repair(heads, deprels)
        multiword = {first: (last, form) for first, last, form in sentence.multiword}
        for number, ((form, _, _), head, deprel) in enumerate(
            zip(sentence.words, heads, deprels, strict=True), 1
        ):
            if number in multiword:
                last, token = multiword[number]
                lines.append(f"{number}-{last}\t{token}" + "\t_" * 8)
            lines.append(f"{number}\t{form}\t_\t_\t_\t_\t{head}\t{deprel}\t_\t_")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fixes


def tok_parses(text: list[Sentence], arcs: Iterable[list[tuple[int, str]]]) -> list[Parsed]:
    """Gold words and multiword tokens with the heads and relations of the system; the number of
    words must match"""
    return [
        Parsed(
            [(form, head, deprel) for form, (head, deprel) in zip(s.words, a, strict=True)],
            s.multiword,
        )
        for s, a in zip(text, arcs, strict=True)
    ]


def token_parse(tokens: Iterable[tuple[str, list[Word]]]) -> Parsed:
    """Parse of a sentence from its tokens: the form and the words of every token"""
    words: list[Word] = []
    multiword = []
    for form, found in tokens:
        if len(found) > 1:
            multiword.append((len(words) + 1, len(words) + len(found), form))
        words += found
    return Parsed(words, multiword)


def feats_string(feats: dict[str, str]) -> str | None:
    """Features of esMorph in the CoNLL-U notation: by name ignoring case"""
    pairs = sorted(feats.items(), key=lambda item: item[0].lower())
    return "|".join(f"{key}={value}" for key, value in pairs) or None


def gold_document(document: Any, text: list[Sentence]) -> Any:
    """
    anySeg document of the gold tokens: a sentence is a paragraph, a multiword token has its gold
    words

    Arguments:
        document (Any): The class anyseg.Document
        text (list[Sentence]): Sentences

    Returns:
        anyseg.Document: Document
    """
    chunks, starts, ends, sentence_starts = [], [], [], []
    words: dict[int, list[str]] = {}
    position = 0
    for sentence in text:
        sentence_starts.append(len(starts))
        for number, token in enumerate(sentence.tokens, 1):
            if len(token.words) > 1:
                words[len(starts)] = token.words
            starts.append(position)
            position += len(token.form)
            ends.append(position)
            chunks.append(token.form)
            if token.space and number < len(sentence.tokens):
                chunks.append(" ")
                position += 1
        chunks.append("\n\n")
        position += 2
    return document.from_tokens(
        "".join(chunks), starts, ends, sentence_starts=sentence_starts, words=words
    )


def essyntax_system(data: Path, threads: int | None) -> System:
    """esSyntax: esMorph tags in context of the document of the gold tokens and its parse
    (annotate); raw text - parse_text"""
    from anyseg import Document
    from esmorph import Analyzer

    from essyntax import Parser

    morph = Analyzer()
    parser = Parser()

    def tag(text: list[Sentence]) -> Any:
        document = gold_document(Document, text)
        annotated = morph.annotate(document)
        if len(annotated.words) == len(document.words):
            return annotated
        # esMorph splits a few tokens otherwise than the gold words (`Al` - `A el`, `m.36` -
        # `m. 36`): their gold words get the first analysis of the word
        upos, feats = [], []
        for token, found in zip(document.tokens, annotated.tokens, strict=True):
            if len(found.words) == len(token.words):
                upos += [word.upos for word in found.words]
                feats += [word.feats for word in found.words]
                continue
            for word in token.words:
                best = morph.analyze(word.form)[0]
                upos.append(best.pos)
                feats.append(feats_string(best.feats))
        document.set_columns(upos=upos, feats=feats)
        return document

    def parse(text: list[Sentence]) -> object:
        document = tag(text)
        parser.annotate(document)
        return document

    def convert(text: list[Sentence], document: Any) -> list[Parsed]:
        arcs = ([(w.head, w.deprel) for w in s.words] for s in document.sentences)
        return tok_parses(text, arcs)

    def raw(paragraphs: list[str]) -> list[Parsed]:
        return [
            token_parse(
                (t.text, [(w.form, w.head, w.deprel) for w in t.words]) for t in sentence.tokens
            )
            for paragraph in paragraphs
            for sentence in parser.parse_text(paragraph).sentences
        ]

    return System(parse, convert, raw)


def spacy_model(data: Path, name: str) -> Path:
    """Directory of a spaCy model in its unpacked wheel"""
    model = SPACY_MODELS[name]
    return data / "spacy" / model.rsplit("-", 1)[0] / model


def spacy_words(span: Any) -> list[Word]:
    """Words of a spaCy sentence without whitespace tokens: their dependents go to the head of the
    whitespace"""
    tokens = [token for token in span if not token.is_space]
    index = {token.i: number + 1 for number, token in enumerate(tokens)}

    def head(token: Any) -> int:
        while token.head.i != token.i:
            if token.head.i in index:
                return index[token.head.i]
            token = token.head
        return 0

    return [(t.text, head(t), "root" if t.dep_ == "ROOT" else t.dep_) for t in tokens]


def spacy_system(data: Path, threads: int | None, name: str) -> System:
    """spaCy without ner: one Doc per gold sentence; raw text - nlp.pipe, multiword tokens are not
    split"""
    import spacy
    from spacy.tokens import Doc

    if threads and name == "spacy-trf":
        import torch

        torch.set_num_threads(threads)
        torch.set_num_interop_threads(threads)
    nlp = spacy.load(spacy_model(data, name), exclude=["ner"])

    def parse(text: list[Sentence]) -> object:
        docs = []
        for s in text:
            spaces = [True] * len(s.words)
            last = 0
            for token in s.tokens:
                last += len(token.words)
                spaces[last - 1] = token.space
            starts = [True] + [False] * (len(s.words) - 1)
            docs.append(Doc(nlp.vocab, words=s.words, spaces=spaces, sent_starts=starts))
        return list(nlp.pipe(docs))

    def convert(text: list[Sentence], docs: Any) -> list[Parsed]:
        arcs = ([(head, deprel) for _, head, deprel in spacy_words(doc[:])] for doc in docs)
        return tok_parses(text, arcs)

    def raw(paragraphs: list[str]) -> list[Parsed]:
        nlp.max_length = max(len(paragraph) for paragraph in paragraphs) + 1
        found = [spacy_words(sent) for doc in nlp.pipe(paragraphs) for sent in doc.sents]
        return [Parsed(sentence, []) for sentence in found if sentence]

    return System(parse, convert, raw)


def stanza_system(data: Path, threads: int | None, name: str) -> System:
    """Stanza: tokenize, mwt, pos, lemma, depparse; gold words - tokenize_pretokenized without
    mwt, raw text - paragraphs as separate documents (bulk_process)"""
    import stanza
    import torch
    from stanza.models.common.doc import Document

    if threads:
        torch.set_num_threads(threads)
        torch.set_num_interop_threads(threads)
    options = {
        "lang": "es",
        "dir": str(data / "stanza"),
        "package": STANZA_PACKAGES[name],
        "download_method": None,
        "use_gpu": False,
        "verbose": False,
    }
    processors = STANZA_PROCESSORS.replace("mwt,", "")
    tagged = stanza.Pipeline(processors=processors, tokenize_pretokenized=True, **options)

    def convert(text: list[Sentence], doc: Any) -> list[Parsed]:
        arcs = ([(w.head, w.deprel) for w in s.words] for s in doc.sentences)
        return tok_parses(text, arcs)

    # The pipeline of raw text - at the first parse: the speed measurement does not load it
    @functools.cache
    def plain() -> Any:
        return stanza.Pipeline(processors=STANZA_PROCESSORS, **options)

    def raw(paragraphs: list[str]) -> list[Parsed]:
        docs = plain().bulk_process([Document([], text=paragraph) for paragraph in paragraphs])
        return [
            token_parse(
                (t.text, [(w.text, w.head, w.deprel) for w in t.words]) for t in sentence.tokens
            )
            for doc in docs
            for sentence in doc.sentences
        ]

    return System(lambda text: tagged([s.words for s in text]), convert, raw)


def conllu_parses(text: str) -> list[Parsed]:
    """Parses of the sentences of CoNLL-U output"""
    result = []
    words: list[Word] = []
    multiword: list[tuple[int, int, str]] = []
    for line in [*text.splitlines(), ""]:
        cols = line.split("\t")
        if not line:
            if words:
                result.append(Parsed(words, multiword))
            words, multiword = [], []
        elif line.startswith("#"):
            continue
        elif "-" in cols[0]:
            first, last = cols[0].split("-")
            multiword.append((int(first), int(last), cols[1]))
        elif cols[0].isdigit():
            words.append((cols[1], int(cols[6]), cols[7]))
    return result


def udpipe_system(data: Path, threads: int | None) -> System:
    """UDPipe 1, AnCora model of UD 2.5: gold words - tag and parse, raw text - Pipeline with the
    tokenizer of the model"""
    from ufal.udpipe import Model, Pipeline, ProcessingError, Sentence as UDPipeSentence

    path = data / UDPIPE_MODEL
    model = Model.load(str(path))
    if model is None:
        raise ValueError(f"{path}: the model is not loaded")

    def parse(text: list[Sentence]) -> object:
        result = []
        for sentence in text:
            found = UDPipeSentence()
            for word in sentence.words:
                found.addWord(word)
            model.tag(found, Model.DEFAULT)
            model.parse(found, Model.DEFAULT)
            result.append(found)
        return result

    def convert(text: list[Sentence], found: Any) -> list[Parsed]:
        arcs = ([(w.head, w.deprel) for w in list(s.words)[1:]] for s in found)
        return tok_parses(text, arcs)

    def raw(paragraphs: list[str]) -> list[Parsed]:
        pipeline = Pipeline(model, "tokenize", Pipeline.DEFAULT, Pipeline.DEFAULT, "conllu")
        error = ProcessingError()
        result = []
        for paragraph in paragraphs:
            output = pipeline.process(paragraph, error)
            if error.occurred():
                raise RuntimeError(error.message)
            result += conllu_parses(output)
        return result

    return System(parse, convert, raw)


SYSTEMS: dict[str, Callable[[Path, int | None], System]] = {
    "essyntax": essyntax_system,
    **{name: functools.partial(spacy_system, name=name) for name in SPACY_MODELS},
    **{name: functools.partial(stanza_system, name=name) for name in STANZA_PACKAGES},
    "udpipe": udpipe_system,
}
TITLES = {
    "essyntax": "esSyntax",
    "spacy-sm": "spaCy es_core_news_sm",
    "spacy-md": "spaCy es_core_news_md",
    "spacy-lg": "spaCy es_core_news_lg",
    "spacy-trf": "spaCy es_dep_news_trf",
    "stanza": "Stanza",
    "stanza-ancora": "Stanza ancora",
    "stanza-accurate": "Stanza accurate",
    "udpipe": "UDPipe 1",
}
MODELS = {
    "essyntax": "built-in model, esMorph tags, anySeg segmentation",
    "spacy-sm": "es_core_news_sm 3.8.0 without ner",
    "spacy-md": "es_core_news_md 3.8.0 without ner",
    "spacy-lg": "es_core_news_lg 3.8.0 without ner",
    "spacy-trf": "es_dep_news_trf 3.8.0",
    "stanza": "default (AnCora and GSD, charlm), resources 1.15.0",
    "stanza-ancora": "ancora (charlm), resources 1.15.0",
    "stanza-accurate": f"default_accurate ({BERT[0]} {BERT[1][:7]}), resources 1.15.0",
    "udpipe": UDPIPE_MODEL.removesuffix(".udpipe"),
}
PACKAGES = {
    "essyntax": ("essyntax", "esmorph", "anyseg"),
    **dict.fromkeys(SPACY_MODELS, ("spacy", "thinc", "numpy")),
    "spacy-trf": ("spacy", "thinc", "numpy", "spacy-curated-transformers", "torch"),
    **dict.fromkeys(STANZA_PACKAGES, ("stanza", "torch", "numpy")),
    "stanza-accurate": ("stanza", "torch", "numpy", "transformers"),
    "udpipe": ("ufal.udpipe",),
}


def stanza_ready(data: Path, package: str) -> bool:
    """Files of a Stanza model in place and with the right checksums"""
    folder = data / "stanza"
    return (folder / "resources.json").exists() and all(
        (folder / name).exists() and sha256(folder / name) == digest
        for name, digest in STANZA_FILES[package].items()
    )


def prepare(name: str, data: Path) -> None:
    """
    Models of a system in the data directory - before the measurements

    Arguments:
        name (str): Name of the system
        data (Path): Data directory

    Raises:
        ValueError: If the checksum of a model does not match
    """
    if name in SPACY_MODELS and not (spacy_model(data, name) / "meta.json").exists():
        wheel = fetch(f"{SPACY_MODELS[name]}-py3-none-any.whl", data)
        with zipfile.ZipFile(wheel) as files:
            files.extractall(data / "spacy")
    if name in STANZA_PACKAGES:
        import stanza

        package = STANZA_PACKAGES[name]
        if not stanza_ready(data, package):
            stanza.download(
                "es",
                model_dir=str(data / "stanza"),
                package=package,
                processors=STANZA_PROCESSORS,
                verbose=False,
            )
            if not stanza_ready(data, package):
                raise ValueError(f"Stanza {package}: the checksum of the model does not match")
        if package == "default_accurate":
            from huggingface_hub import snapshot_download

            snapshot = snapshot_download(
                BERT[0],
                revision=BERT[1],
                allow_patterns=[
                    "config.json",
                    "vocab.json",
                    "merges.txt",
                    "tokenizer*",
                    "pytorch_model.bin",
                ],
            )
            # Without downloads transformers takes the model from the cache by the main reference
            refs = Path(snapshot).parents[1] / "refs"
            refs.mkdir(exist_ok=True)
            (refs / "main").write_text(BERT[1], encoding="utf-8")
    if name == "udpipe":
        fetch(UDPIPE_MODEL, data)


def evaluator(data: Path) -> ModuleType:
    """
    Official CoNLL 2018 evaluation script as a module

    Arguments:
        data (Path): Data directory

    Returns:
        ModuleType: Module conll18_ud_eval
    """
    path = fetch("conll18_ud_eval.py", data)
    spec = importlib.util.spec_from_file_location("conll18_ud_eval", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    # No __pycache__ in the data directory
    write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = write_bytecode
    return module


def quality(name: str, data: Path, ud: ModuleType, cache: dict[str, object]) -> dict:
    """
    UAS and LAS of a system on all the sets in the modes tok and raw

    Arguments:
        name (str): Name of the system
        data (Path): Data directory
        ud (ModuleType): CoNLL 2018 evaluation script
        cache (dict[str, object]): Loaded gold sets, filled

    Returns:
        dict: Mode - set - scores, number of tree repairs and parse time in seconds
    """
    system = SYSTEMS[name](data, None)
    result: dict = {mode: {} for mode in MODES}
    for dataset in DATASETS:
        path = gold(dataset, data)
        text = sentences(path)
        if dataset not in cache:
            cache[dataset] = ud.load_conllu_file(str(path))
        for mode in MODES:
            start = time.perf_counter()
            if mode == "tok":
                parsed = system.convert(text, system.parse(text))
            else:
                parsed = system.text(paragraphs(text))
            seconds = time.perf_counter() - start
            pred = data / "pred" / name / mode / f"{dataset}.conllu"
            fixes = write(pred, parsed)
            scores = ud.evaluate(cache[dataset], ud.load_conllu_file(str(pred)))
            result[mode][dataset] = {key: round(100 * scores[key].f1, 2) for key in METRICS}
            result[mode][dataset] |= {"repaired": fixes, "seconds": round(seconds, 2)}
            values = result[mode][dataset]
            print(
                f"{TITLES[name]}, {mode}, {dataset}: UAS {values['UAS']}, LAS {values['LAS']}, "
                f"{seconds:.1f} s",
                file=sys.stderr,
                flush=True,
            )
    return result


def speed_run(name: str, data: Path) -> None:
    """
    Measurement in a clean process: the time of import and loading of a system, of the first parse
    of the gold words of AnCora test and the best of two parses, the peak memory of the process

    Arguments:
        name (str): Name of the system
        data (Path): Data directory
    """
    text = sentences(data / DATASETS[SPEED_SET][1])
    if limit := SPEED_WORDS.get(name):
        count = 0
        for size, sentence in enumerate(text):
            count += len(sentence.words)
            if count >= limit:
                text = text[: size + 1]
                break
    base = peak_memory()
    start = time.perf_counter()
    system = SYSTEMS[name](data, 1)
    # Deferred loading (the dictionary and models of esMorph) is loading too
    system.parse(text[:1])
    loaded = time.perf_counter()
    system.parse(text)
    first = time.perf_counter()
    system.parse(text)
    best = min(first - loaded, time.perf_counter() - first)
    words = sum(len(sentence.words) for sentence in text)
    result = {
        "words": words,
        "sentences": len(text),
        "subset": name in SPEED_WORDS,
        "load": round(loaded - start, 3),
        "first": round(first - loaded, 3),
        "best": round(best, 3),
        "words_per_second": round(words / best),
        "memory": peak_memory(),
        "memory_before_load": base,
    }
    print(json.dumps(result))


def peak_memory() -> float | None:
    """Peak memory of the process (RSS), MB; None if the system does not give it"""
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS gives bytes, Linux - kilobytes
    return round(peak / 2**20 if sys.platform == "darwin" else peak / 2**10, 1)


def load_average() -> list[float] | None:
    """Load average over 1, 5 and 15 minutes; None if the system does not give it"""
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        return None


def measure(name: str, data: Path, max_load: float) -> dict:
    """
    Measurement `speed_run` in a separate process in one thread, once the 1-minute load average
    is below the limit

    Arguments:
        name (str): Name of the system
        data (Path): Data directory
        max_load (float): Limit of the 1-minute load average

    Returns:
        dict: Words, times in seconds, words per second, memory in MB and load average

    Raises:
        RuntimeError: If the process of the measurement failed
    """
    while (before := load_average()) and before[0] >= max_load:
        print(f"load average {before[0]}: waiting", file=sys.stderr, flush=True)
        time.sleep(30)
    run = subprocess.run(
        [sys.executable, __file__, str(data), "--speed-run", name],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **THREADS, "PYTHONWARNINGS": "ignore"},
    )
    if run.returncode:
        raise RuntimeError(f"{name}: the speed measurement failed\n{run.stderr[-3000:]}")
    result = json.loads(run.stdout.strip().splitlines()[-1])
    return result | {"threads": 1, "load_average": {"before": before, "after": load_average()}}


def number(value: float, digits: int, spanish: bool) -> str:
    """Number with a thousands separator: in Spanish a space from five digits on"""
    text = f"{value:,.{digits}f}"
    if not spanish:
        return text
    return text.replace(",", " " if abs(value) >= 10_000 else "")


def tables(results: dict, spanish: bool = False) -> str:
    """
    Markdown tables: UAS / LAS by mode, words and sentences of raw text, speed

    Arguments:
        results (dict): Results of the systems
        spanish (bool): Captions in Spanish

    Returns:
        str: Tables
    """
    names = [name for name in SYSTEMS if name in results]
    if spanish:
        captions = {
            "tok": (
                "Palabras de referencia",
                "UAS / LAS, %: las palabras y oraciones de referencia, la morfología propia del "
                "sistema (las etiquetas de esMorph para esSyntax)",
            ),
            "raw": (
                "Texto sin procesar",
                "UAS / LAS, %: la segmentación propia del sistema en oraciones, tokens y palabras "
                "(anySeg y esMorph para esSyntax)",
            ),
            "segmentation": (
                "Texto sin procesar: palabras y oraciones",
                "F1 de palabras / oraciones, %",
            ),
        }
        speed_title = "Velocidad"
        speed_caption = (
            "Un hilo, las palabras de referencia de AnCora test, el mejor de dos análisis sin la "
            "carga (esSyntax junto con las etiquetas de esMorph); memoria - el pico de RSS del proceso"
        )
        speed_header = [
            "Sistema",
            "palabras/s",
            "importación y carga, s",
            "memoria, MB",
            "palabras medidas",
            "carga media",
        ]
        system = "Sistema"
    else:
        captions = {
            "tok": (
                "Gold words",
                "UAS / LAS, %: the gold words and sentences, the own morphology of the system "
                "(esMorph tags for esSyntax)",
            ),
            "raw": (
                "Raw text",
                "UAS / LAS, %: the own segmentation of the system into sentences, tokens and words "
                "(anySeg and esMorph for esSyntax)",
            ),
            "segmentation": ("Raw text: words and sentences", "Words / Sentences F1, %"),
        }
        speed_title = "Speed"
        speed_caption = (
            "One thread, the gold words of AnCora test, the best of two runs without loading "
            "(esSyntax together with esMorph tags); memory - the peak RSS of the process"
        )
        speed_header = [
            "System",
            "words/s",
            "import and loading, s",
            "memory, MB",
            "words measured",
            "load average",
        ]
        system = "System"
    lines = []
    for key, (title, caption) in captions.items():
        mode, metrics = ("raw", ("Words", "Sentences")) if key == "segmentation" else (key, None)
        rows = [name for name in names if mode in results[name]]
        if not rows:
            continue
        lines += [f"## {title}", "", caption, ""]
        lines.append(f"| {system} | " + " | ".join(DATASETS) + " |")
        lines.append("| :-- | " + " | ".join("--:" for _ in DATASETS) + " |")
        for name in rows:
            cells = []
            for dataset in DATASETS:
                values = results[name][mode][dataset]
                first, second = metrics or ("UAS", "LAS")
                pair = (number(values[first], 2, spanish), number(values[second], 2, spanish))
                cells.append(" / ".join(pair))
            lines.append(f"| {TITLES[name]} | " + " | ".join(cells) + " |")
        lines.append("")
    rows = [name for name in names if "speed" in results[name]]
    if rows:
        lines += [f"## {speed_title}", "", speed_caption, ""]
        lines.append("| " + " | ".join(speed_header) + " |")
        lines.append("| :-- | " + " | ".join("--:" for _ in speed_header[1:]) + " |")
        for name in rows:
            speed = results[name]["speed"]
            memory = "-" if speed["memory"] is None else number(speed["memory"], 0, spanish)
            load = speed["load_average"]
            cells = [
                TITLES[name],
                number(speed["words_per_second"], 0, spanish),
                number(speed["load"], 2, spanish),
                memory,
                number(speed["words"], 0, spanish),
                " - ".join(
                    "-" if value is None else number(value[0], 2, spanish)
                    for value in (load["before"], load["after"])
                ),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def versions(packages: tuple[str, ...]) -> dict[str, str | None]:
    """Versions of packages; None - the package is not installed"""
    found: dict[str, str | None] = {}
    for package in packages:
        try:
            found[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            found[package] = None
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("data", type=Path, help="data directory")
    parser.add_argument("--systems", nargs="+", default=list(SYSTEMS), choices=list(SYSTEMS))
    parser.add_argument(
        "--skip", choices=("quality", "speed"), help="do not measure quality or speed"
    )
    parser.add_argument(
        "--max-load",
        type=float,
        default=4.0,
        help="the 1-minute load average below which speed is measured (default 4)",
    )
    parser.add_argument(
        "--report", action="store_true", help="tables from results.json without measurements"
    )
    parser.add_argument("--speed-run", metavar="SYSTEM", help=argparse.SUPPRESS)
    args = parser.parse_args()
    data: Path = args.data.resolve()
    # Cache of Hugging Face (Stanza models and the transformer) - in the data directory
    os.environ["HF_HOME"] = str(data / "stanza" / "hf")
    if args.speed_run:
        speed_run(args.speed_run, data)
        return
    saved = data / "results.json"
    results = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else {}

    def save() -> None:
        saved.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.report:
        data.mkdir(parents=True, exist_ok=True)
        for name in args.systems:
            prepare(name, data)
        # A run of some systems updates only their results
        if args.skip != "quality":
            ud = evaluator(data)
            cache: dict[str, object] = {}
            for name in args.systems:
                entry = results.setdefault(name, {})
                entry |= quality(name, data, ud, cache)
                entry |= {"model": MODELS[name], "versions": versions(PACKAGES[name])}
                save()
        # Speed - after quality, when other measurements do not load the machine
        if args.skip != "speed":
            gold(SPEED_SET, data)
            for name in args.systems:
                results.setdefault(name, {})["speed"] = measure(name, data, args.max_load)
                speed = results[name]["speed"]
                print(
                    f"{TITLES[name]}: {speed['words_per_second']:,} words/s, "
                    f"load average {speed['load_average']['before']}",
                    file=sys.stderr,
                    flush=True,
                )
                save()
        environment = {"python": sys.version.split()[0], "platform": platform.platform()}
        environment |= {"machine": platform.machine(), "processor": platform.processor()}
        packages = sorted({package for name in SYSTEMS for package in PACKAGES[name]})
        environment |= versions(tuple(packages))
        (data / "environment.json").write_text(json.dumps(environment, indent=2), encoding="utf-8")
    (data / "tables.md").write_text(tables(results), encoding="utf-8")
    (data / "tables.es.md").write_text(tables(results, spanish=True), encoding="utf-8")
    print(tables(results))


if __name__ == "__main__":
    main()
