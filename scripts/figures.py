"""
Figures of the documentation: how esSyntax parses a sentence

Description:
    Draws by the real parse of the packaged model: the pipeline anySeg → esMorph → esSyntax on one
    sentence (docs/img/pipeline.svg), the dependency arcs of this sentence with the plain names of
    the relations (docs/img/arcs.svg), the structure of the model with the sizes from its file of
    weights (docs/img/model.svg) and the head probabilities of an ambiguous sentence
    (docs/img/heads.svg); each in English and in Spanish (*.es.svg). The probabilities come from a
    forward pass of the model in numpy over the file of weights (data/es-syntax.bin), checked
    against the parse of the Rust core: the same heads and relations, the same probabilities up to
    rounding. Runs in the environment of the project with esSyntax built from the repository;
    numpy is added for the run.

Example:
    uv run --with numpy python scripts/figures.py
"""

import json
import re
import struct
import zlib
from itertools import accumulate, pairwise
from pathlib import Path
from typing import Any

import numpy as np

from essyntax import Parser

ROOT = Path(__file__).parents[1]
MODEL = ROOT / "data" / "es-syntax.bin"
IMG = ROOT / "docs" / "img"
EXAMPLE = "Ayer la hija del vecino compró un coche nuevo."
AMBIGUOUS = "Vi a la niña con el telescopio."
CONFIG = (
    "hidden",
    "layers",
    "word_dim",
    "suffix_dim",
    "tag_dim",
    "arc_dim",
    "rel_dim",
    "max_feats",
)
# Row of a table for an unknown string; row 0 is the padding
UNKNOWN = 1
TIMES = "\N{MULTIPLICATION SIGN}"

FONT = "PT Sans, Source Sans Pro, Arial, sans-serif"
# The colors of the logo
DARK, LIGHT, SOFT = "#c62828", "#ef5350", "#fdecea"
INK, MUTED, GREY = "#212121", "#6b6b6b", "#eeeeee"
SUB = '<tspan baseline-shift="sub" font-size="70%">{}</tspan>'
SUP = '<tspan baseline-shift="super" font-size="70%">{}</tspan>'
BIAFFINE = "s(i, j) = [d" + SUB.format("i") + "; 1]" + SUP.format("T") + " W h" + SUB.format("j")
PAIR = "[d" + SUB.format("i") + "; h"

TEXTS: dict[str, dict[str, Any]] = {
    "en": {
        "pos": {
            "NOUN": "noun",
            "VERB": "verb",
            "AUX": "aux.",
            "ADJ": "adj.",
            "ADV": "adv.",
            "ADP": "prep.",
            "DET": "det.",
            "PRON": "pron.",
            "PROPN": "name",
            "NUM": "num.",
            "PUNCT": "punct.",
        },
        "feats": {
            ("Gender", "Masc"): "masc.",
            ("Gender", "Fem"): "fem.",
            ("Number", "Sing"): "sing.",
            ("Number", "Plur"): "plur.",
            ("Tense", "Past"): "past",
            ("Tense", "Pres"): "present",
        },
        "rel": {
            "root": "predicate",
            "nsubj": "subject",
            "obj": "direct object",
            "iobj": "indirect object",
            "obl": "adverbial",
            "advmod": "adverbial",
            "amod": "modifier",
            "nmod": "noun complement",
            "det": "determiner",
            "case": "preposition",
            "punct": "punctuation",
        },
        "steps": (
            "1. Text",
            "2. anySeg splits the text into words: «{token}» is {words}",
            "3. esMorph gives every word its part of speech and features",
            "4. esSyntax finds the word every word depends on and names the relation",
        ),
        "root": "ROOT",
        "model": (
            ("form in lowercase", "endings 1-4", "UPOS of esMorph", "features of esMorph"),
            "{words} words",
            "word vector: {din}",
            "BiLSTM {layers} {x} {hidden}, both directions: {out} per word",
            ("head MLP: {arc} and {arc}", "relation MLP: {rel} and {rel}"),
            "biaffine score " + BIAFFINE,
            "softmax over j: P(head j | word i)",
            "Chu - Liu - Edmonds: a tree with one root",
            "linear layer over " + PAIR + " of the head]\n→ {labels} UD relations",
            "heads",
            "the head and the relation of every word · {params} million parameters, int8 by rows",
            (
                "Trained on {treebanks} (UD {ud}) with a treebank marker at the input;",
                "every text is parsed with the marker of {marker}, folded into the first BiLSTM layer",
            ),
        ),
        "heads": (
            "Word",
            "Head candidate",
            (
                "P(head | word): softmax of the biaffine scores over the row;",
                "a frame marks the head in the parse tree",
            ),
        ),
    },
    "es": {
        "pos": {
            "NOUN": "sust.",
            "VERB": "verbo",
            "AUX": "aux.",
            "ADJ": "adj.",
            "ADV": "adv.",
            "ADP": "prep.",
            "DET": "det.",
            "PRON": "pron.",
            "PROPN": "n. propio",
            "NUM": "num.",
            "PUNCT": "signo",
        },
        "feats": {
            ("Gender", "Masc"): "masc.",
            ("Gender", "Fem"): "fem.",
            ("Number", "Sing"): "sing.",
            ("Number", "Plur"): "pl.",
            ("Tense", "Past"): "pasado",
            ("Tense", "Pres"): "presente",
        },
        "rel": {
            "root": "núcleo del predicado",
            "nsubj": "sujeto",
            "obj": "complemento directo",
            "iobj": "complemento indirecto",
            "obl": "complemento circunstancial",
            "advmod": "complemento circunstancial",
            "amod": "modificador",
            "nmod": "complemento del nombre",
            "det": "determinante",
            "case": "preposición",
            "punct": "puntuación",
        },
        "steps": (
            "1. Texto",
            "2. anySeg divide el texto en palabras: «{token}» es {words}",
            "3. esMorph da a cada palabra su categoría y sus rasgos",
            "4. esSyntax encuentra la palabra de la que depende cada palabra y la relación",
        ),
        "root": "RAÍZ",
        "model": (
            ("forma en minúsculas", "terminaciones 1-4", "UPOS de esMorph", "rasgos de esMorph"),
            "{words} palabras",
            "vector de la palabra: {din}",
            "BiLSTM {layers} {x} {hidden}, en ambos sentidos: {out} por palabra",
            ("MLP del núcleo: {arc} y {arc}", "MLP de la relación: {rel} y {rel}"),
            "puntuación biafín " + BIAFFINE,
            "softmax por j: P(núcleo j | palabra i)",
            "Chu - Liu - Edmonds: árbol con una raíz",
            "capa lineal sobre " + PAIR + " del núcleo]\n→ {labels} relaciones UD",
            "núcleos",
            "el núcleo y la relación de cada palabra · {params} millones de parámetros, "
            "int8 por filas",
            (
                "Entrenado con {treebanks} (UD {ud}) con un marcador del corpus en la entrada;",
                "cada texto se analiza con el marcador de {marker}, incorporado en la primera "
                "capa BiLSTM",
            ),
        ),
        "heads": (
            "Palabra",
            "Candidato a núcleo",
            (
                "P(núcleo | palabra): softmax de las puntuaciones biafines por fila;",
                "el marco señala el núcleo en el árbol del análisis",
            ),
        ),
    },
}


def read_model(path: Path) -> dict[str, Any]:
    """
    Entries of the model file of esSyntax: strings, matrices (int8 by rows - dequantized) and numbers

    Arguments:
        path (Path): Model file

    Returns:
        dict[str, Any]: Entries by name

    Raises:
        ValueError: If the file is not an esSyntax model or is damaged
    """
    data = path.read_bytes()
    if data[:8] != b"ESSYNTAX" or zlib.crc32(data[16:]) != struct.unpack_from("<I", data, 12)[0]:
        raise ValueError(f"{path}: not an esSyntax model or the file is damaged")
    at = 20
    entries: dict[str, Any] = {}
    for _ in range(struct.unpack_from("<I", data, 16)[0]):
        (length,) = struct.unpack_from("<H", data, at)
        name = data[at + 2 : at + 2 + length].decode()
        at += 2 + length
        kind = data[at]
        at += 1
        if kind == 0:
            (count,) = struct.unpack_from("<I", data, at)
            at += 4
            items = []
            for _ in range(count):
                (size,) = struct.unpack_from("<I", data, at)
                items.append(data[at + 4 : at + 4 + size].decode())
                at += 4 + size
            entries[name] = items
        elif kind in (1, 2):
            rows, cols = struct.unpack_from("<II", data, at)
            at += 8
            if kind == 1:
                matrix = np.frombuffer(data, "<f4", rows * cols, at).reshape(rows, cols)
                at += 4 * rows * cols
            else:
                scales = np.frombuffer(data, "<f4", rows, at)
                at += 4 * rows
                values = np.frombuffer(data, "i1", rows * cols, at).reshape(rows, cols)
                at += rows * cols
                matrix = values.astype(np.float32) * scales[:, None]
            entries[name] = matrix.astype(np.float32)
        else:
            (count,) = struct.unpack_from("<I", data, at)
            entries[name] = list(struct.unpack_from(f"<{count}I", data, at + 4))
            at += 4 + 4 * count
    return entries


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


class Numpy:
    """
    Forward pass of the model in numpy, for the figures and not for parsing

    Arguments:
        path (Path): Model file
    """

    def __init__(self, path: Path) -> None:
        self.e = read_model(path)
        self.config = dict(zip(CONFIG, self.e["config"], strict=True))
        self.index = {
            name: {text: i + 2 for i, text in enumerate(self.e[f"vocab.{name}"])}
            for name in ("words", "suffixes", "upos", "feats")
        }

    def row(self, table: str, matrix: str, key: str | None) -> np.ndarray:
        number = UNKNOWN if key is None else self.index[table].get(key, UNKNOWN)
        return self.e[f"embed.{matrix}"][number]

    def embed(self, words: list[dict]) -> np.ndarray:
        """Input of the BiLSTM, as in the core: the root (unknown rows, no features) and the words"""
        rows = []
        for word in [None, *words]:
            form = None if word is None else word["form"].lower()
            # Endings of length 1-4 with the word-start mark: a short form is whole with the mark
            ends = [None if form is None else f"{k}:{('^' + form)[-k:]}" for k in range(1, 5)]
            parts = [self.row("words", "word", form)]
            parts += [self.row("suffixes", "suffix", end) for end in ends]
            parts.append(self.row("upos", "upos", None if word is None else word["upos"]))
            total = np.zeros(self.config["tag_dim"], np.float32)
            if word is not None:
                pairs = [p for p in word["feats"].split("|") if p and p != "_"]
                for pair in pairs[: self.config["max_feats"]]:
                    total += self.row("feats", "feats", pair)
            parts.append(total)
            rows.append(np.concatenate(parts))
        return np.stack(rows)

    def lstm(self, x: np.ndarray, prefix: str, reverse: bool) -> np.ndarray:
        ih, hh, bias = (self.e[f"{prefix}.{name}"] for name in ("ih", "hh", "bias"))
        hidden = hh.shape[1]
        h = np.zeros(hidden, np.float32)
        c = np.zeros(hidden, np.float32)
        out = np.zeros((len(x), hidden), np.float32)
        steps = range(len(x) - 1, -1, -1) if reverse else range(len(x))
        for t in steps:
            # The gates in the order of PyTorch: input, forget, candidate, output
            i, f, cand, o = np.split(ih @ x[t] + bias[0] + hh @ h, 4)
            c = 1 / (1 + np.exp(-f)) * c + 1 / (1 + np.exp(-i)) * np.tanh(cand)
            h = 1 / (1 + np.exp(-o)) * np.tanh(c)
            out[t] = h
        return out

    def dense(self, x: np.ndarray, name: str) -> np.ndarray:
        y = x @ self.e[f"{name}.weight"].T + self.e[f"{name}.bias"][0]
        return np.where(y > 0, y, 0.1 * y)

    def parse(self, words: list[dict]) -> dict[str, Any]:
        """
        Parse of a sentence whose best heads already make a tree with one root: the core takes such
        heads as they are

        Arguments:
            words (list[dict]): Words with forms, UPOS and features

        Returns:
            dict[str, Any]: Head probabilities (a row - a word, a column - a candidate, 0 - the
            root), heads, relations and their probabilities
        """
        x = self.embed(words)
        for layer in range(self.config["layers"]):
            x = np.concatenate(
                [
                    self.lstm(x, f"lstm.{layer}.forward", False),
                    self.lstm(x, f"lstm.{layer}.backward", True),
                ],
                1,
            )
        dep = self.dense(x, "arc_dep")
        dep = np.concatenate([dep, np.ones((len(dep), 1), np.float32)], 1)
        scores = dep @ self.e["arc.weight"] @ self.dense(x, "arc_head").T
        np.fill_diagonal(scores, -np.inf)
        probs = softmax(scores[1:])
        heads = [int(np.argmax(row)) for row in probs]
        pairs = np.concatenate([self.dense(x, "rel_dep")[1:], self.dense(x, "rel_head")[heads]], 1)
        labels = pairs @ self.e["label.weight"].T + self.e["label.bias"][0]
        relations = self.e["relations"]
        root = relations.index("root")
        deprels, deprel_probs = [], []
        for head, row in zip(heads, labels, strict=True):
            # The word with head 0 has the relation root, and only it
            if head == 0:
                deprels.append("root")
                deprel_probs.append(1.0)
                continue
            p = softmax(np.where(np.arange(len(row)) == root, -np.inf, row))
            deprels.append(relations[int(np.argmax(p))])
            deprel_probs.append(float(p.max()))
        return {
            "probs": probs,
            "heads": heads,
            "deprels": deprels,
            "head_probs": [float(probs[i, h]) for i, h in enumerate(heads)],
            "deprel_probs": deprel_probs,
        }


def width(value: str, size: float) -> float:
    return len(re.sub(r"<[^>]+>", "", value)) * size * 0.56 + 6


def text(
    x: float,
    y: float,
    value: str,
    size: float = 16,
    color: str = INK,
    bold: bool = False,
    anchor: str = "middle",
) -> str:
    weight = ' font-weight="bold"' if bold else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:g}" fill="{color}"{weight} '
        f'text-anchor="{anchor}">{value}</text>'
    )


def arrow(x: float, y: float, size: float = 7, color: str = LIGHT) -> str:
    return (
        f'<path d="M{x - size:.1f} {y - 1.6 * size:.1f}L{x + size:.1f} {y - 1.6 * size:.1f}'
        f'L{x:.1f} {y:.1f}Z" fill="{color}"/>'
    )


def save(name: str, lang: str, w: float, h: float, body: list[str]) -> None:
    """A figure on a white background: it stays readable in the dark theme of the site"""
    suffix = "" if lang == "en" else f".{lang}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" '
        f'height="{h:.0f}" font-family="{FONT}" role="img">\n'
        f'<rect width="{w:.0f}" height="{h:.0f}" rx="12" fill="white"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )
    (IMG / f"{name}{suffix}.svg").write_text(svg, encoding="utf-8")


def pos(word: dict, lang: str) -> str:
    return TEXTS[lang]["pos"].get(word["upos"], word["upos"])


def relation(word: dict, lang: str) -> str:
    return TEXTS[lang]["rel"].get(word["deprel"], word["deprel"])


def label_width(word: dict, lang: str) -> float:
    return max(width(relation(word, lang), 13), width(word["deprel"], 10)) + 8


def layout(
    words: list[dict], lang: str, size: float, gap: float, x0: float
) -> tuple[list[float], float]:
    """
    Centers of the words in a row and its width: room for a word and its part of speech, and the
    labels of the arcs of one length (they are at one height) do not overlap

    Arguments:
        words (list[dict]): Words with heads and relations
        lang (str): Language of the labels
        size (float): Font size of the words
        gap (float): Gap between words
        x0 (float): Margin

    Returns:
        tuple[list[float], float]: Centers of the words and the width of the row with the margins
    """
    half = [max(width(w["form"], size), width(pos(w, lang), 13)) / 2 for w in words]
    steps = [half[k] + gap + half[k + 1] for k in range(len(words) - 1)]
    # Arcs by length and start: neighbors at one height follow each other
    arcs = sorted(
        (abs(w["head"] - 1 - i), min(i, w["head"] - 1), label_width(w, lang))
        for i, w in enumerate(words)
        if w["head"]
    )
    while True:
        xs = list(accumulate([x0 + half[0], *steps]))
        for (d1, a1, w1), (d2, a2, w2) in pairwise(arcs):
            room = (xs[a2] + xs[a2 + d2] - xs[a1] - xs[a1 + d1]) / 2 - (w1 + w2) / 2 - 10
            if d1 == d2 and room < 0:
                # The first gap of the first arc and the last gap of the second are each inside
                # one of them: widening a gap like that moves the labels apart by half of it
                steps[a1] -= room
                steps[a2 + d2 - 1] -= room
                break
        else:
            return xs, xs[-1] + half[-1] + x0


def arcs(words: list[dict], lang: str, xs: list[float]) -> tuple[list[str], float]:
    """Arcs from the head to the dependent above the row of words (the row is at y = 0) and the top
    of the highest label; the height grows with the length of the relation"""
    # First all the arcs, then the labels: otherwise a long arc crosses the label of a short one
    body, labels, top = [], [], 0.0
    order = sorted(range(len(words)), key=lambda i: abs(words[i]["head"] - 1 - i))
    for i in order:
        w = words[i]
        if w["head"] == 0:
            continue
        h = w["head"] - 1
        x1, x2 = xs[h], xs[i]
        height = 30 + 46 * abs(h - i)
        y, cy = -8, -8 - height
        start = x1 + (6 if x2 > x1 else -6)
        body.append(
            f'<path fill="none" stroke="{LIGHT}" stroke-width="2.5" '
            f'd="M{start:.1f} {y}C{x1:.1f} {cy:.1f} {x2:.1f} {cy:.1f} {x2:.1f} {y - 9}"/>'
        )
        body.append(arrow(x2, y))
        name = relation(w, lang)
        # The label is at the top of the curve: three quarters of the height of its control points
        mx, my = (x1 + x2) / 2, cy + 0.25 * height - 6
        top = min(top, my - 14)
        lw = label_width(w, lang)
        labels.append(
            f'<rect x="{mx - lw / 2:.1f}" y="{my - 14:.1f}" width="{lw:.1f}" height="30" rx="5" '
            'fill="white"/>'
        )
        labels.append(text(mx, my, name, 13, DARK, True))
        labels.append(text(mx, my + 12, w["deprel"], 10, MUTED))
    return body + labels, top


def draw_arcs(words: list[dict], lang: str) -> None:
    xs, total = layout(words, lang, 22, 30, 40)
    body, top = arcs(words, lang, xs)
    root = next(i for i, w in enumerate(words) if w["head"] == 0)
    body[:0] = [
        f'<path fill="none" stroke="{DARK}" stroke-width="2.5" '
        f'd="M{xs[root]:.1f} {top - 30:.1f}L{xs[root]:.1f} -18"/>',
        arrow(xs[root], -8, 7, DARK),
    ]
    body.append(text(xs[root] + 10, top - 20, TEXTS[lang]["rel"]["root"], 13, DARK, True, "start"))
    for w, x in zip(words, xs, strict=True):
        body.append(text(x, 20, w["form"], 22, INK, True))
        body.append(text(x, 40, pos(w, lang), 13, MUTED))
    shift = -top + 50
    save(
        "arcs",
        lang,
        total,
        shift + 60,
        [f'<g transform="translate(0,{shift:.0f})">', *body, "</g>"],
    )


def features(word: dict, lang: str) -> str:
    """Gender and number of a word or the tense of a verb in plain words: "fem. sing.", "past" """
    names = TEXTS[lang]["feats"]
    pairs = dict(pair.split("=", 1) for pair in word["feats"].split("|") if "=" in pair)
    keys = ("Tense",) if "Tense" in pairs else ("Gender", "Number")
    return " ".join(names[key, pairs[key]] for key in keys if (key, pairs.get(key)) in names)


def draw_pipeline(words: list[dict], token: tuple[int, int, int, int], lang: str) -> None:
    first, last, start, end = token
    steps = [
        step.format(
            token=EXAMPLE[start:end],
            words=" + ".join(f"«{w['form']}»" for w in words[first : last + 1]),
        )
        for step in TEXTS[lang]["steps"]
    ]
    xs, total = layout(words, lang, 18, 24, 20)
    sentence = (
        f'{EXAMPLE[:start]}<tspan fill="{DARK}" font-weight="bold">{EXAMPLE[start:end]}</tspan>'
        f"{EXAMPLE[end:]}"
    )
    body = [
        text(20, 30, steps[0], 15, DARK, True, "start"),
        text(20, 60, sentence, 20, INK, False, "start"),
        text(20, 100, steps[1], 15, DARK, True, "start"),
    ]
    boxes = []
    for w, x in zip(words, xs, strict=True):
        bw = width(w["form"], 18) + 10
        boxes.append((x - bw / 2, x + bw / 2))
        body.append(
            f'<rect x="{x - bw / 2:.1f}" y="138" width="{bw:.1f}" height="30" rx="6" fill="white" '
            f'stroke="{LIGHT}" stroke-width="1.5"/>'
        )
        body.append(text(x, 159, w["form"], 18))
    # The multiword token over its words: a bracket with the token as in the text
    left, right = boxes[first][0], boxes[last][1]
    body.append(
        f'<path fill="none" stroke="{DARK}" stroke-width="1.5" '
        f'd="M{left:.1f} 133L{left:.1f} 127L{right:.1f} 127L{right:.1f} 133"/>'
    )
    body.append(text((left + right) / 2, 121, EXAMPLE[start:end], 15, DARK, True))
    body.append(text(20, 200, steps[2], 15, DARK, True, "start"))
    for w, x in zip(words, xs, strict=True):
        body.append(text(x, 228, w["form"], 18))
        body.append(text(x, 246, pos(w, lang), 12, DARK))
        body.append(text(x, 260, features(w, lang), 12, MUTED))
    body.append(text(20, 300, steps[3], 15, DARK, True, "start"))
    arc, top = arcs(words, lang, xs)
    shift = 320 - top
    body.append(f'<g transform="translate(0,{shift:.0f})">')
    body += arc + [text(x, 18, w["form"], 18, INK, True) for w, x in zip(words, xs, strict=True)]
    body.append("</g>")
    w = max(total, *(width(step, 15) + 40 for step in steps))
    save("pipeline", lang, w, shift + 40, body)


def box(
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
    fill: str = SOFT,
    color: str = INK,
    size: float = 15,
) -> list[str]:
    lines = label.split("\n")
    return [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" fill="{fill}" '
        f'stroke="{DARK}" stroke-width="1.5"/>',
        *(
            text(
                x + w / 2,
                y + h / 2 + size * (0.35 + 1.1 * (k - (len(lines) - 1) / 2)),
                line,
                size,
                color,
            )
            for k, line in enumerate(lines)
        ),
    ]


def down(x: float, y1: float, y2: float) -> list[str]:
    return [
        f'<path d="M{x:.1f} {y1:.1f}L{x:.1f} {y2 - 9:.1f}" stroke="{DARK}" stroke-width="2"/>',
        arrow(x, y2, 6, DARK),
    ]


def number(value: float, lang: str, digits: int = 2) -> str:
    shown = f"{value:.{digits}f}"
    return shown if lang == "en" else shown.replace(".", ",")


def draw_model(model: Numpy, sources: dict, lang: str, labels: int, params: float) -> None:
    c = model.config
    t = TEXTS[lang]["model"]
    words = len(model.e["vocab.words"])
    treebanks = [name.removeprefix("UD_Spanish-") for name in sources["treebanks"]]
    fmt = {
        "words": f"{words:,}".replace(",", "," if lang == "en" else " "),
        "din": c["word_dim"] + 4 * c["suffix_dim"] + 2 * c["tag_dim"],
        "layers": c["layers"],
        "hidden": c["hidden"],
        "out": 2 * c["hidden"],
        "arc": c["arc_dim"],
        "rel": c["rel_dim"],
        "labels": labels,
        "params": number(params, lang, 1),
        "treebanks": (" and " if lang == "en" else " y ").join(treebanks),
        "ud": sources["ud"].removeprefix("r"),
        "marker": sources["treebank_marker"],
        "x": TIMES,
    }
    body = []
    dims = (
        f"{t[1].format(**fmt)} · {c['word_dim']}",
        f"4 {TIMES} {c['suffix_dim']}",
        str(c["tag_dim"]),
        f"Σ {c['tag_dim']}",
    )
    for k, (name, dim) in enumerate(zip(t[0], dims, strict=True)):
        x = 40 + k * 205
        body += box(x, 20, 185, 54, "", "white")
        body += [text(x + 92.5, 43, name, 15), text(x + 92.5, 63, dim, 13, MUTED)]
        body += down(x + 92.5, 74, 104)
    body += box(40, 104, 800, 40, t[2].format(**fmt))
    body += down(440, 144, 172)
    body += box(40, 172, 800, 44, t[3].format(**fmt), DARK, "white", 16)
    left, right = 40, 470
    body += down(left + 185, 216, 246) + down(right + 185, 216, 246)
    for k, y in enumerate((246, 312, 378, 444)):
        label = t[4][0] if k == 0 else t[4 + k]
        body += box(left, y, 370, 44, label.format(**fmt), size=14)
        if k < 3:
            body += down(left + 185, y + 44, y + 66)
    # The relation is scored for the heads of the tree: the linear layer is next to the tree
    body += box(right, 246, 370, 44, t[4][1].format(**fmt), size=14)
    body += down(right + 185, 290, 444)
    body += box(right, 444, 370, 44, t[8].format(**fmt), size=14)
    body += [
        f'<path d="M{left + 370} 466L{right - 9} 466" stroke="{DARK}" stroke-width="2"/>',
        f'<path d="M{right} 466L{right - 10} 460L{right - 10} 472Z" fill="{DARK}"/>',
        text((left + 370 + right) / 2, 458, t[9], 12, DARK),
    ]
    body += down(left + 185, 488, 516) + down(right + 185, 488, 516)
    body += box(40, 516, 800, 44, t[10].format(**fmt), DARK, "white", 15)
    for k, line in enumerate(t[11]):
        body.append(text(440, 590 + k * 18, line.format(**fmt), 13, MUTED))
    save("model", lang, 880, 628, body)


def draw_heads(words: list[dict], probs: np.ndarray, lang: str) -> None:
    t = TEXTS[lang]["heads"]
    n = len(words)
    candidates = [TEXTS[lang]["root"]] + [w["form"] for w in words]
    # A cell is as wide as two neighboring candidates need
    sizes = [width(name, 14) for name in candidates]
    cell = round(max(66, *((a + b) / 2 + 8 for a, b in pairwise(sizes))))
    left, topy = 150, 100
    body = [
        text(left + cell * (n + 1) / 2, 30, t[1], 15, DARK, True),
        text(30, topy + cell * n / 2 + 5, t[0], 15, DARK, True, "start"),
    ]
    for j, name in enumerate(candidates):
        body.append(text(left + j * cell + cell / 2, topy - 14, name, 14, INK, True))
    for i, w in enumerate(words):
        y = topy + i * cell
        body.append(text(left - 12, y + cell / 2 + 5, w["form"], 16, INK, True, "end"))
        for j in range(n + 1):
            x = left + j * cell
            if j == i + 1:
                body.append(
                    f'<rect x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" '
                    f'fill="{GREY}"/>'
                )
                continue
            p = float(probs[i, j])
            body.append(
                f'<rect x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" '
                f'fill="{DARK}" fill-opacity="{min(1.0, p) ** 0.6:.3f}"/>'
            )
            if p >= 0.005:
                color = "white" if p > 0.35 else INK
                body.append(text(x + cell / 2, y + cell / 2 + 6, number(p, lang), 17, color, True))
            if words[i]["head"] == j:
                body.append(
                    f'<rect x="{x + 3}" y="{y + 3}" width="{cell - 6}" height="{cell - 6}" '
                    f'fill="none" stroke="{INK}" stroke-width="3" rx="4"/>'
                )
    for k, line in enumerate(t[2]):
        body.append(text(30, topy + cell * n + 34 + k * 18, line, 14, MUTED, False, "start"))
    w = max(left + cell * (n + 1) + 30, *(width(line, 14) + 60 for line in t[2]))
    save("heads", lang, w, topy + cell * n + 72, body)


def tagged(parser: Parser, value: str) -> tuple[list[dict], list[tuple[int, int, int, int]]]:
    """
    Words of a sentence parsed by the package and its multiword tokens

    Arguments:
        parser (Parser): Parser
        value (str): Text of one sentence

    Returns:
        tuple[list[dict], list[tuple[int, int, int, int]]]: Words and the multiword tokens: the
        numbers of their first and last words, the start and the end in the text
    """
    document = parser.parse_text(value)
    words = [
        {
            "form": w.form,
            "upos": w.upos,
            "feats": w.feats or "_",
            "head": w.head,
            "deprel": w.deprel,
        }
        for w in document.words
    ]
    tokens = [
        (t.words[0].index, t.words[-1].index, t.start, t.end) for t in document.multiword_tokens
    ]
    return words, tokens


def check(model: Numpy, parser: Parser, words: list[dict]) -> tuple[np.ndarray, float]:
    """
    Forward pass in numpy against the parse of the core: the same heads and relations, the
    probabilities equal up to rounding

    Arguments:
        model (Numpy): Model in numpy
        parser (Parser): Parser of the package
        words (list[dict]): Words parsed by the package

    Returns:
        tuple[np.ndarray, float]: Head probabilities of the words and the largest difference of the
        probabilities of the heads and the relations from those of the core
    """
    ours = model.parse(words)
    core = parser.parse(
        [w["form"] for w in words],
        [w["upos"] for w in words],
        [w["feats"] for w in words],
        probs=True,
    )
    assert ours["heads"] == [r[0] for r in core] == [w["head"] for w in words]
    assert ours["deprels"] == [r[1] for r in core] == [w["deprel"] for w in words]
    ours_probs = np.array([ours["head_probs"], ours["deprel_probs"]])
    core_probs = np.array([[r[2] for r in core], [r[3] for r in core]])
    diff = float(np.abs(ours_probs - core_probs).max())
    assert diff < 1e-3, diff
    return ours["probs"], diff


def main() -> None:
    parser = Parser()
    model = Numpy(MODEL)
    params = sum(v.size for v in model.e.values() if isinstance(v, np.ndarray)) / 1e6
    example, tokens = tagged(parser, EXAMPLE)
    ambiguous, _ = tagged(parser, AMBIGUOUS)
    _, example_diff = check(model, parser, example)
    probs, ambiguous_diff = check(model, parser, ambiguous)
    for lang in TEXTS:
        draw_pipeline(example, tokens[0], lang)
        draw_arcs(example, lang)
        draw_model(model, parser.sources, lang, len(parser.relations), params)
        draw_heads(ambiguous, probs, lang)
    print(
        json.dumps(
            {
                "params_million": round(params, 2),
                "max_prob_diff_from_core": max(example_diff, ambiguous_diff),
                "ambiguous": [[round(float(p), 3) for p in row] for row in probs],
            }
        )
    )


if __name__ == "__main__":
    main()
