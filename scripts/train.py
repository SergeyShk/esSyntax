# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = [
#     "anyseg==0.5.0",
#     "esmorph==0.6.0",
#     "numpy==2.5.5",
#     "torch==2.15.0",
# ]
# ///
"""
Training of the esSyntax model: the head and the relation of every word by the words with esMorph tags

Description:
    Takes the training and development parts of UD_Spanish-AnCora and the development part of
    UD_Spanish-GSD from the directory of `scripts/export_ud.py`, gives the words the part of
    speech and the features of esMorph in context (the parser gets the same tags from the user)
    and trains the model on AnCora train. The tags are given to the gold words: the tokens of a
    treebank with its sentences and the words of its multiword tokens make an anySeg document,
    which esMorph annotates keeping the given words; a token that esMorph splits otherwise than
    the treebank (`m.36`, `Al`) gets the first analysis of each of its gold words. Training makes
    the parser robust to tagging errors: for an ambiguous word of train the first analysis with
    other tags is taken with the probability `NOISE`, and a pair of features of a word drops out
    with the probability `FEAT_DROPOUT`. The noise is not for a gap between the tags of train and
    dev: esMorph tags AnCora train almost as accurately as dev. The model: the input of a word is
    its form (the 20 thousand most frequent, lowercase), its endings of length 1-4 with a
    word-start mark, the UPOS and the sum of the embeddings of its first 12 pairs of features; a
    BiLSTM of two layers of 128; the head is a biaffine score and the Chu - Liu - Edmonds tree
    with one root, the relation is a linear score of the pair "dependent - head". The training
    point is chosen by LAS on AnCora dev; GSD dev is a control on another genre. The weights are
    quantized to int8 by rows and written in the format of the core (`--output`, the entry
    `sources` describes the sources and the LAS on dev); `--check` gets the parse of the first
    sentences of AnCora dev by the same quantized model in PyTorch, the reference of the test of
    the crate that checks the forward pass in Rust. The versions of the packages are pinned in
    train.py.lock. On MPS and GPU training is non-deterministic: a rerun gives close but not the
    same weights

Example:
    uv run --python 3.13 scripts/train.py target/ud --output data/es-syntax.bin --check data/check.conllu
"""

import argparse
import json
import platform
import random
import struct
import time
import zlib
from collections import Counter
from collections.abc import Iterator
from importlib import metadata
from pathlib import Path

import anyseg
import esmorph
import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

TRAIN = ["es_ancora-ud-train.conllu"]
# Treebank of the training parts: the weights take its license
TREEBANK = "UD_Spanish-AnCora"
DEV = {"AnCora": "es_ancora-ud-dev.conllu", "GSD": "es_gsd-ud-dev.conllu"}
# Dev parts by which the training point is chosen
SELECT = ("AnCora",)
# Sentences of AnCora dev in the check file of the core; GSD (CC BY-SA 4.0) is not distributed
CHECK = 200
# Tag noise of train by treebank; UPOS and features of esMorph 0.6 are right for 95.0 % of the
# words of AnCora train and 94.9 % of dev
NOISE = {"ancora": 0.05}
# Probability that a pair of features of a word drops out in training
FEAT_DROPOUT = 0.1
CONFIG = {
    "hidden": 128,
    "layers": 2,
    "word_dim": 64,
    "suffix_dim": 16,
    "tag_dim": 50,
    "arc_dim": 128,
    "rel_dim": 64,
    "max_feats": 12,
}
WORDS = 20000
DROPOUT = 0.33
WORD_DROPOUT = 0.25
PAD, UNKNOWN = 0, 1
MAGIC = b"ESSYNTAX"
FORMAT = 1

# Token of a sentence: form, whether a space follows it, rows of its words (10 columns each)
Token = tuple[str, bool, list[list[str]]]
# Sentence: forms, UPOS, features, heads, relations
Sentence = tuple[list[str], list[str], list[str], list[int], list[str]]


def read(path: Path) -> Iterator[list[Token]]:
    """
    Tokens of the sentences of a CoNLL-U file with their words; empty nodes are left out

    Arguments:
        path (Path): CoNLL-U file

    Returns:
        Iterator[list[Token]]: Tokens of a sentence
    """
    tokens: list[Token] = []
    # Last word of the current multiword token
    last = 0
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.rstrip("\n")
            if not line:
                if tokens:
                    yield tokens
                tokens, last = [], 0
            elif not line.startswith("#"):
                cols = line.split("\t")
                space = "SpaceAfter=No" not in cols[9]
                if "-" in cols[0]:
                    last = int(cols[0].split("-")[1])
                    tokens.append((cols[1], space, []))
                elif cols[0].isdigit() and int(cols[0]) <= last:
                    tokens[-1][2].append(cols)
                elif cols[0].isdigit():
                    tokens.append((cols[1], space, [cols]))
    if tokens:
        yield tokens


def document(sentences: list[list[Token]]) -> anyseg.Document:
    """
    anySeg document of the gold tokens: a sentence is a paragraph, the words of a multiword token are
    those of the treebank

    Arguments:
        sentences (list[list[Token]]): Tokens of the sentences

    Returns:
        anyseg.Document: Document with the tokens, sentences and words of the treebank
    """
    chunks: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    sentence_starts: list[int] = []
    words: dict[int, list[str]] = {}
    at = 0
    for tokens in sentences:
        sentence_starts.append(len(starts))
        for k, (form, space, rows) in enumerate(tokens):
            # The byte order mark is a space for anySeg (GSD train starts with it)
            text = form.replace("﻿", "")
            if len(rows) > 1:
                words[len(starts)] = [row[1] for row in rows]
            starts.append(at)
            chunks.append(text)
            at += len(text)
            ends.append(at)
            if space and k + 1 < len(tokens):
                chunks.append(" ")
                at += 1
        chunks.append("\n\n")
        at += 2
    return anyseg.Document.from_tokens(
        "".join(chunks), starts, ends, sentence_starts=sentence_starts, words=words
    )


def feats_text(feats: dict[str, str]) -> str:
    """
    Features in the CoNLL-U notation, ordered without regard to case, as in UD

    Arguments:
        feats (dict[str, str]): Features of an analysis

    Returns:
        str: Notation `A=B|C=D` or `_`
    """
    pairs = sorted(feats.items(), key=lambda pair: pair[0].lower())
    return "|".join(f"{name}={value}" for name, value in pairs) or "_"


def tag(analyzer: esmorph.Analyzer, sentences: list[list[Token]]) -> list[list[tuple[str, str]]]:
    """
    Part of speech and features of esMorph in context for the gold words of the sentences

    Arguments:
        analyzer (esmorph.Analyzer): Morphological analyzer
        sentences (list[list[Token]]): Tokens of the sentences

    Returns:
        list[list[tuple[str, str]]]: UPOS and features of every word of every sentence
    """
    tokens = iter(analyzer.annotate(document(sentences)).tokens)
    out = []
    for sentence in sentences:
        tags = []
        for _, _, rows in sentence:
            words = list(next(tokens).words)
            if len(words) == len(rows):
                tags += [(word.upos or "X", word.feats or "_") for word in words]
                continue
            # esMorph splits the token otherwise than the treebank: the first analysis of every word
            for row in rows:
                best = analyzer.analyze(row[1])[0]
                tags.append((best.pos, feats_text(best.feats)))
        out.append(tags)
    return out


def load(
    path: Path, analyzer: esmorph.Analyzer, rng: random.Random | None = None
) -> list[Sentence]:
    """
    Sentences with the tags of esMorph and the gold heads and relations

    Arguments:
        path (Path): CoNLL-U file
        analyzer (esmorph.Analyzer): Morphological analyzer
        rng (random.Random | None): Make the tags noisy by `NOISE` (for train)

    Returns:
        list[Sentence]: Sentences
    """
    sentences = list(read(path))
    noise = NOISE.get(path.name.split("_")[1].split("-")[0], 0.0) if rng else 0.0
    out = []
    for tokens, tags in zip(sentences, tag(analyzer, sentences), strict=True):
        rows = [row for _, _, words in tokens for row in words]
        forms = [row[1] for row in rows]
        for k, form in enumerate(forms):
            if rng and noise and rng.random() < noise:
                other = ((a.pos, feats_text(a.feats)) for a in analyzer.analyze(form))
                tags[k] = next((pair for pair in other if pair != tags[k]), tags[k])
        out.append(
            (
                forms,
                [upos for upos, _ in tags],
                [feats for _, feats in tags],
                [int(row[6]) for row in rows],
                [row[7] for row in rows],
            )
        )
    return out


def norm(form: str) -> str:
    """
    Form for the vocabulary of the model: lowercase (as in the core)

    Arguments:
        form (str): Form of a word

    Returns:
        str: Normalized form
    """
    return form.lower()


def suffixes(form: str) -> list[str]:
    """
    Keys of the endings of length 1-4 with the word-start mark "^" (as in the core)

    Arguments:
        form (str): Form of a word

    Returns:
        list[str]: Keys `k:ending`
    """
    word = "^" + norm(form)
    return [f"{k}:{word[-k:]}" for k in range(1, 5)]


def pairs(feats: str) -> list[str]:
    """
    Pairs "feature=value" of a CoNLL-U field, at most `max_feats` (as in the core)

    Arguments:
        feats (str): Field of features

    Returns:
        list[str]: Pairs
    """
    return [pair for pair in feats.split("|") if pair and pair != "_"][: CONFIG["max_feats"]]


class Vocab:
    """
    Vocabularies of the model: rows 0 and 1 of the tables are the padding and the unknown

    Arguments:
        sentences (list[Sentence]): Training sentences
    """

    def __init__(self, sentences: list[Sentence]) -> None:
        words = Counter(norm(w) for s in sentences for w in s[0])
        sufs = Counter(x for s in sentences for w in s[0] for x in suffixes(w))
        self.words = sorted(w for w, c in words.most_common(WORDS) if c >= 2)
        self.suffixes = sorted(x for x, c in sufs.items() if c >= 3)
        self.upos = sorted({u for s in sentences for u in s[1]})
        self.feats = sorted({f for s in sentences for fs in s[2] for f in pairs(fs)})
        self.relations = sorted({r for s in sentences for r in s[4]})
        self.index = {
            name: {text: i + 2 for i, text in enumerate(getattr(self, name))}
            for name in ("words", "suffixes", "upos", "feats")
        }
        self.relation = {r: i for i, r in enumerate(self.relations)}

    def number(self, table: str, key: str) -> int:
        return self.index[table].get(key, UNKNOWN)


def encode(vocab: Vocab, sentences: list[Sentence]) -> tuple[torch.Tensor, ...]:
    """
    Tensors of a batch: position 0 is the root (unknown rows, no features)

    Arguments:
        vocab (Vocab): Vocabularies
        sentences (list[Sentence]): Sentences of the batch

    Returns:
        tuple[torch.Tensor, ...]: Words, endings, UPOS, features, heads, relations, lengths
    """
    n = max(len(s[0]) for s in sentences) + 1
    b = len(sentences)
    words = torch.zeros(b, n, dtype=torch.long)
    sufs = torch.zeros(b, n, 4, dtype=torch.long)
    upos = torch.zeros(b, n, dtype=torch.long)
    feats = torch.zeros(b, n, CONFIG["max_feats"], dtype=torch.long)
    heads = torch.zeros(b, n, dtype=torch.long)
    rels = torch.zeros(b, n, dtype=torch.long)
    lens = torch.tensor([len(s[0]) + 1 for s in sentences])
    for i, (forms, tags, fs, hs, rs) in enumerate(sentences):
        words[i, 0], sufs[i, 0], upos[i, 0] = UNKNOWN, UNKNOWN, UNKNOWN
        for j, form in enumerate(forms, 1):
            words[i, j] = vocab.number("words", norm(form))
            for k, key in enumerate(suffixes(form)):
                sufs[i, j, k] = vocab.number("suffixes", key)
            upos[i, j] = vocab.number("upos", tags[j - 1])
            for k, pair in enumerate(pairs(fs[j - 1])):
                feats[i, j, k] = vocab.number("feats", pair)
            heads[i, j] = hs[j - 1]
            rels[i, j] = vocab.relation.get(rs[j - 1], 0)
    return words, sufs, upos, feats, heads, rels, lens


def batches(sentences: list[Sentence], size: int, rng: random.Random | None) -> list[list[int]]:
    """
    Batches of at most `size` positions with padding, sentences of close length together

    Arguments:
        sentences (list[Sentence]): Sentences
        size (int): Positions in a batch
        rng (random.Random | None): Shuffle the batches

    Returns:
        list[list[int]]: Numbers of the sentences of the batches
    """
    order = sorted(range(len(sentences)), key=lambda i: len(sentences[i][0]))
    out: list[list[int]] = []
    current: list[int] = []
    longest = 0
    for i in order:
        n = len(sentences[i][0]) + 1
        if current and max(longest, n) * (len(current) + 1) > size:
            out.append(current)
            current, longest = [], 0
        current.append(i)
        longest = max(longest, n)
    if current:
        out.append(current)
    if rng:
        rng.shuffle(out)
    return out


class Dense(nn.Module):
    """Layer LeakyReLU(Wx + b) with a slope of 0.1 and dropout"""

    def __init__(self, n_in: int, n_out: int) -> None:
        super().__init__()
        self.lin = nn.Linear(n_in, n_out)
        self.drop = nn.Dropout(DROPOUT)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.drop(nn.functional.leaky_relu(self.lin(x), 0.1))


class Parser(nn.Module):
    """
    Model: embeddings, BiLSTM, a biaffine score of heads and a linear score of relations

    Arguments:
        vocab (Vocab): Vocabularies
    """

    def __init__(self, vocab: Vocab) -> None:
        super().__init__()
        c = CONFIG
        self.word = nn.Embedding(len(vocab.words) + 2, c["word_dim"], padding_idx=PAD)
        self.suffix = nn.Embedding(len(vocab.suffixes) + 2, c["suffix_dim"], padding_idx=PAD)
        self.upos = nn.Embedding(len(vocab.upos) + 2, c["tag_dim"], padding_idx=PAD)
        self.feats = nn.EmbeddingBag(
            len(vocab.feats) + 2, c["tag_dim"], mode="sum", padding_idx=PAD
        )
        with torch.no_grad():
            # Train has no unknown pairs: the row does not learn, zero is the absence of a feature
            self.feats.weight[UNKNOWN].zero_()
        n_in = c["word_dim"] + 4 * c["suffix_dim"] + 2 * c["tag_dim"]
        self.lstm = nn.LSTM(
            n_in, c["hidden"], c["layers"], batch_first=True, bidirectional=True, dropout=DROPOUT
        )
        self.drop = nn.Dropout(DROPOUT)
        h2 = 2 * c["hidden"]
        self.arc_dep, self.arc_head = Dense(h2, c["arc_dim"]), Dense(h2, c["arc_dim"])
        self.rel_dep, self.rel_head = Dense(h2, c["rel_dim"]), Dense(h2, c["rel_dim"])
        # Biaffine matrix of (a + 1) rows and a columns: the last row is the bias of the dependent
        self.arc = nn.Parameter(torch.zeros(c["arc_dim"] + 1, c["arc_dim"]))
        self.label = nn.Linear(2 * c["rel_dim"], len(vocab.relations))

    def forward(
        self,
        words: torch.Tensor,
        sufs: torch.Tensor,
        upos: torch.Tensor,
        feats: torch.Tensor,
        lens: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        b, n = words.shape
        if self.training:
            drop = torch.rand(words.shape, device=words.device) < WORD_DROPOUT
            words = words.masked_fill(drop & (words > PAD), UNKNOWN)
            # A pair of features drops out whole: the padding row is the absence of the feature
            drop = torch.rand(feats.shape, device=feats.device) < FEAT_DROPOUT
            feats = feats.masked_fill(drop, PAD)
        x = torch.cat(
            [
                self.word(words),
                self.suffix(sufs).view(b, n, -1),
                self.upos(upos),
                self.feats(feats.view(b * n, -1)).view(b, n, -1),
            ],
            -1,
        )
        packed = pack_padded_sequence(
            self.drop(x), lens.cpu(), batch_first=True, enforce_sorted=False
        )
        out, _ = self.lstm(packed)
        out, _ = pad_packed_sequence(out, batch_first=True, total_length=n)
        out = self.drop(out)
        dep = self.arc_dep(out)
        dep = torch.cat([dep, torch.ones_like(dep[..., :1])], -1)
        scores = dep @ self.arc @ self.arc_head(out).transpose(1, 2)
        mask = torch.arange(n, device=words.device)[None, :] < lens[:, None]
        eye = torch.eye(n, dtype=torch.bool, device=words.device)[None]
        scores = scores.masked_fill(~mask[:, None, :] | eye, float("-inf"))
        return scores, self.rel_dep(out), self.rel_head(out)

    def labels(
        self, rel_dep: torch.Tensor, rel_head: torch.Tensor, heads: torch.Tensor
    ) -> torch.Tensor:
        """Scores of the relations by the pair "dependent - head" for the given heads: [b, n, relations]"""
        head = rel_head.gather(1, heads[..., None].expand(-1, -1, rel_head.shape[-1]))
        return self.label(torch.cat([rel_dep, head], -1))


def cycle(heads: list[int]) -> list[int] | None:
    """
    Nodes of the first cycle in the heads (0 - the root)

    Arguments:
        heads (list[int]): Heads of the positions

    Returns:
        list[int] | None: Cycle or None
    """
    color = [0] * len(heads)
    for start in range(1, len(heads)):
        path, v = [], start
        while v != 0 and color[v] == 0:
            color[v] = 1
            path.append(v)
            v = heads[v]
        if v != 0 and color[v] == 1:
            return path[path.index(v) :]
        for p in path:
            color[p] = 2
    return None


def edmonds(s: np.ndarray) -> list[int]:
    """
    Tree of the maximum weight with the root 0: s[d, h], row 0 and the diagonal are -inf

    Arguments:
        s (np.ndarray): Scores of heads

    Returns:
        list[int]: Heads of the positions
    """
    n = len(s)
    heads = [0] + [int(np.argmax(s[d])) for d in range(1, n)]
    cyc = cycle(heads)
    if cyc is None:
        return heads
    in_cycle = np.zeros(n, bool)
    in_cycle[cyc] = True
    rest = np.where(~in_cycle)[0]
    cyc_a = np.array(cyc)
    m = len(rest)
    t = np.full((m + 1, m + 1), -np.inf)
    t[:m, :m] = s[np.ix_(rest, rest)]
    out_scores = s[np.ix_(rest, cyc_a)]
    best_out = cyc_a[out_scores.argmax(1)]
    t[:m, m] = out_scores.max(1)
    in_scores = s[np.ix_(cyc_a, rest)] - s[cyc_a, np.array(heads)[cyc_a]][:, None]
    best_in = cyc_a[in_scores.argmax(0)]
    t[m, :m] = in_scores.max(0)
    t[0, :] = -np.inf
    inner = edmonds(t)
    result = list(heads)
    for i in range(1, m):
        result[rest[i]] = int(best_out[i]) if inner[i] == m else int(rest[inner[i]])
    h = inner[m]
    result[int(best_in[h])] = int(rest[h])
    return result


def tree(scores: np.ndarray) -> list[int]:
    """
    Tree with one root by the log probabilities of heads (as in the core on ordinary sentences)

    Arguments:
        scores (np.ndarray): Log probabilities s[d, h]

    Returns:
        list[int]: Heads of the positions
    """
    s = scores.astype(np.float64)
    np.fill_diagonal(s, -np.inf)
    s[0, :] = -np.inf
    heads = edmonds(s)
    roots = [d for d in range(1, len(s)) if heads[d] == 0]
    if len(roots) == 1:
        return heads
    best, best_heads = -np.inf, heads
    for root in roots:
        t = s.copy()
        t[:, 0] = -np.inf
        t[root, 0] = s[root, 0]
        candidate = edmonds(t)
        total = sum(t[d, candidate[d]] for d in range(1, len(s)))
        if total > best:
            best, best_heads = total, candidate
    return best_heads


def predict(
    model: Parser, vocab: Vocab, sentences: list[Sentence], device: torch.device
) -> list[tuple[list[int], list[str]]]:
    """
    Heads and relations of sentences

    Arguments:
        model (Parser): Model
        vocab (Vocab): Vocabularies
        sentences (list[Sentence]): Sentences
        device (torch.device): Device

    Returns:
        list[tuple[list[int], list[str]]]: Heads and relations of every sentence
    """
    model.eval()
    out: list[tuple[list[int], list[str]]] = [([], [])] * len(sentences)
    with torch.no_grad():
        for idx in batches(sentences, 4000, None):
            words, sufs, upos, feats, _, _, lens = (
                t.to(device) for t in encode(vocab, [sentences[i] for i in idx])
            )
            scores, rel_dep, rel_head = model(words, sufs, upos, feats, lens)
            logp = torch.log_softmax(scores, -1).cpu().numpy()
            heads = torch.zeros(words.shape, dtype=torch.long)
            for k in range(len(idx)):
                n = int(lens[k])
                heads[k, :n] = torch.tensor(tree(logp[k, :n, :n]))
            labels = model.labels(rel_dep, rel_head, heads.to(device)).argmax(-1).cpu()
            for k, i in enumerate(idx):
                n = int(lens[k])
                out[i] = (
                    heads[k, 1:n].tolist(),
                    [vocab.relations[r] for r in labels[k, 1:n].tolist()],
                )
    return out


def las(sentences: list[Sentence], parses: list[tuple[list[int], list[str]]]) -> float:
    """
    LAS: the share of words with the right head and relation without its subtype, as in the script of
    CoNLL 2018

    Arguments:
        sentences (list[Sentence]): Gold sentences
        parses (list[tuple[list[int], list[str]]]): Parse

    Returns:
        float: LAS, %
    """
    total = right = 0
    for s, (heads, rels) in zip(sentences, parses, strict=True):
        for gh, gr, ph, pr in zip(s[3], s[4], heads, rels, strict=True):
            total += 1
            right += gh == ph and gr.split(":")[0] == pr.split(":")[0]
    return 100 * right / total


def loss_fn(model: Parser, batch: tuple[torch.Tensor, ...]) -> torch.Tensor:
    words, sufs, upos, feats, heads, rels, lens = batch
    scores, rel_dep, rel_head = model(words, sufs, upos, feats, lens)
    mask = torch.arange(words.shape[1], device=words.device)[None, :] < lens[:, None]
    mask[:, 0] = False
    arc = nn.functional.cross_entropy(scores[mask], heads[mask])
    rel = nn.functional.cross_entropy(model.labels(rel_dep, rel_head, heads)[mask], rels[mask])
    return arc + rel


def train(
    model: Parser,
    vocab: Vocab,
    sentences: list[Sentence],
    dev: dict[str, list[Sentence]],
    args: argparse.Namespace,
    device: torch.device,
) -> dict[str, float]:
    """
    Training with the point chosen by the mean LAS of the dev parts `SELECT`: the best weights stay in
    the model

    Arguments:
        model (Parser): Model
        vocab (Vocab): Vocabularies
        sentences (list[Sentence]): Training sentences
        dev (dict[str, list[Sentence]]): Dev parts
        args (argparse.Namespace): Arguments of the run
        device (torch.device): Device

    Returns:
        dict[str, float]: LAS on dev at the best point
    """
    rng = random.Random(args.seed)
    opt = torch.optim.Adam(model.parameters(), lr=2e-3, betas=(0.9, 0.9))
    sched = torch.optim.lr_scheduler.ExponentialLR(opt, 0.75 ** (1 / 5000))
    per_epoch = len(batches(sentences, args.batch, None))
    every = min(per_epoch, 1000)
    best: tuple[float, dict[str, float], dict[str, torch.Tensor]] = (-1.0, {}, {})
    step = bad = 0
    start = time.time()
    while step < args.steps and bad < args.patience:
        model.train()
        for idx in batches(sentences, args.batch, rng):
            batch = tuple(t.to(device) for t in encode(vocab, [sentences[i] for i in idx]))
            loss = loss_fn(model, batch)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            sched.step()
            step += 1
            if step % every == 0 or step == args.steps:
                scores = {
                    name: las(s, predict(model, vocab, s, device)) for name, s in dev.items()
                }
                select = sum(scores[name] for name in SELECT) / len(SELECT)
                print(
                    f"step {step}, epoch {step / per_epoch:.1f}, {(time.time() - start) / 60:.1f} min: "
                    + ", ".join(f"{name} {value:.2f}" for name, value in scores.items()),
                    flush=True,
                )
                if select > best[0]:
                    state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                    best, bad = (select, scores, state), 0
                else:
                    bad += 1
                model.train()
            if step >= args.steps or bad >= args.patience:
                break
    model.load_state_dict(best[2])
    return best[1]


def quantize_(model: Parser) -> None:
    """
    int8 by rows, as in the weight file: the matrices are replaced by the dequantized values

    Arguments:
        model (Parser): Model
    """
    with torch.no_grad():
        for _, tensor in matrices(model):
            scale = tensor.abs().amax(1, keepdim=True).clamp(min=1e-12) / 127
            tensor.copy_((tensor / scale).round().clamp(-127, 127) * scale)


def matrices(model: Parser) -> list[tuple[str, torch.Tensor]]:
    """
    Matrices of the model under the names of the weight file (they are written in int8); the biases are
    apart, in f32

    Arguments:
        model (Parser): Model

    Returns:
        list[tuple[str, torch.Tensor]]: Name of the entry and the matrix
    """
    out = [
        ("embed.word", model.word.weight),
        ("embed.suffix", model.suffix.weight),
        ("embed.upos", model.upos.weight),
        ("embed.feats", model.feats.weight),
        ("arc.weight", model.arc),
        ("label.weight", model.label.weight),
    ]
    for layer in range(CONFIG["layers"]):
        for direction, suffix in (("forward", ""), ("backward", "_reverse")):
            out.append(
                (
                    f"lstm.{layer}.{direction}.ih",
                    getattr(model.lstm, f"weight_ih_l{layer}{suffix}"),
                )
            )
            out.append(
                (
                    f"lstm.{layer}.{direction}.hh",
                    getattr(model.lstm, f"weight_hh_l{layer}{suffix}"),
                )
            )
    out.extend(
        (f"{name}.weight", getattr(model, name).lin.weight)
        for name in ("arc_dep", "arc_head", "rel_dep", "rel_head")
    )
    return out


def write(model: Parser, vocab: Vocab, sources: dict, path: Path) -> None:
    """
    Weight file of the core: the signature, the format version, CRC32 and the entries; matrices are
    int8 by rows

    Arguments:
        model (Parser): Model (the matrices are already quantized by `quantize_`)
        vocab (Vocab): Vocabularies
        sources (dict): Description of the training for the entry `sources`
        path (Path): Weight file
    """

    def strings(items: list[str]) -> bytes:
        out = bytearray([0]) + struct.pack("<I", len(items))
        for text in items:
            data = text.encode("utf-8")
            out += struct.pack("<I", len(data)) + data
        return bytes(out)

    def floats(tensor: torch.Tensor) -> bytes:
        t = tensor.detach().float().reshape(1, -1).cpu()
        return bytes([1]) + struct.pack("<II", *t.shape) + t.numpy().astype("<f4").tobytes()

    def int8(tensor: torch.Tensor) -> bytes:
        t = tensor.detach().float().cpu()
        scale = t.abs().amax(1).clamp(min=1e-12) / 127
        q = (t / scale[:, None]).round().clamp(-127, 127).to(torch.int8)
        return (
            bytes([2])
            + struct.pack("<II", *t.shape)
            + scale.numpy().astype("<f4").tobytes()
            + q.numpy().tobytes()
        )

    c = CONFIG
    entries = {
        "config": bytes([3]) + struct.pack("<I8I", 8, *(c[k] for k in CONFIG)),
        "sources": strings([json.dumps(sources, ensure_ascii=False)]),
        "vocab.words": strings(vocab.words),
        "vocab.suffixes": strings(vocab.suffixes),
        "vocab.upos": strings(vocab.upos),
        "vocab.feats": strings(vocab.feats),
        "relations": strings(vocab.relations),
        "label.bias": floats(model.label.bias),
    }
    entries.update({name: int8(tensor) for name, tensor in matrices(model)})
    for layer in range(c["layers"]):
        for direction, suffix in (("forward", ""), ("backward", "_reverse")):
            bias = getattr(model.lstm, f"bias_ih_l{layer}{suffix}") + getattr(
                model.lstm, f"bias_hh_l{layer}{suffix}"
            )
            entries[f"lstm.{layer}.{direction}.bias"] = floats(bias)
    for name in ("arc_dep", "arc_head", "rel_dep", "rel_head"):
        entries[f"{name}.bias"] = floats(getattr(model, name).lin.bias)
    body = struct.pack("<I", len(entries))
    for name, value in entries.items():
        data = name.encode("utf-8")
        body += struct.pack("<H", len(data)) + data + value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MAGIC + struct.pack("<II", FORMAT, zlib.crc32(body)) + body)


def write_check(
    sentences: list[Sentence], parses: list[tuple[list[int], list[str]]], path: Path
) -> None:
    """
    Check file of the core: forms, UPOS and features of esMorph, heads and relations of the PyTorch model

    Arguments:
        sentences (list[Sentence]): Sentences
        parses (list[tuple[list[int], list[str]]]): Parse of the quantized model
        path (Path): CoNLL-U file
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for s, (heads, rels) in zip(sentences, parses, strict=True):
            for i, (form, upos, feats, head, rel) in enumerate(
                zip(s[0], s[1], s[2], heads, rels, strict=True), 1
            ):
                file.write(f"{i}\t{form}\t_\t{upos}\t_\t{feats}\t{head}\t{rel}\t_\t_\n")
            file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("data", type=Path, help="directory of scripts/export_ud.py")
    parser.add_argument("--output", type=Path, default=Path("data/es-syntax.bin"))
    parser.add_argument("--check", type=Path, default=Path("data/check.conllu"))
    parser.add_argument("--steps", type=int, default=12000)
    parser.add_argument(
        "--patience", type=int, default=8, help="evaluations on dev without growth before the stop"
    )
    parser.add_argument("--batch", type=int, default=5000, help="positions in a batch")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    device = torch.device(args.device)
    analyzer = esmorph.Analyzer()
    rng = random.Random(args.seed + 7)
    sentences = [s for name in TRAIN for s in load(args.data / name, analyzer, rng)]
    dev = {name: load(args.data / file, analyzer) for name, file in DEV.items()}
    vocab = Vocab(sentences)
    model = Parser(vocab).to(device)
    print(
        f"train: {len(sentences)} sentences, {sum(len(s[0]) for s in sentences)} words",
        flush=True,
    )
    best = train(model, vocab, sentences, dev, args, device)
    model = model.cpu()
    quantize_(model)
    quantized = {
        name: round(las(s, predict(model, vocab, s, torch.device("cpu"))), 2)
        for name, s in dev.items()
    }
    exported = json.loads((args.data / "sources.json").read_text(encoding="utf-8"))
    sources = {
        "ud": exported["release"],
        "license": exported["licenses"][TREEBANK],
        "treebanks": exported["treebanks"],
        "train": TRAIN,
        "select": list(SELECT),
        "tags": f"esmorph {metadata.version('esmorph')}",
        "noise": NOISE,
        "feat_dropout": FEAT_DROPOUT,
        "torch": metadata.version("torch"),
        "python": platform.python_version(),
        "seed": args.seed,
        "dev_las": {name: round(value, 2) for name, value in best.items()},
        "dev_las_int8": quantized,
    }
    write(model, vocab, sources, args.output)
    check = dev["AnCora"][:CHECK]
    write_check(check, predict(model, vocab, check, torch.device("cpu")), args.check)
    print(
        f"{args.output}: {args.output.stat().st_size} bytes; LAS dev int8: {quantized}", flush=True
    )


if __name__ == "__main__":
    main()
