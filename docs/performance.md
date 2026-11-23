# Comparison

From raw text esSyntax parses more accurately than spaCy, its transformer model included, and UDPipe 1 on all four test sets: by 2.8-6.5 LAS points than spaCy `es_dep_news_trf` and by 5.9-12.5 than the others. It is level with the default Stanza model on AnCora and COSER and behind it on GSD and PUD, whose conventions that model learns from GSD; it is ahead of the AnCora model of Stanza on GSD and PUD and behind it by 1.2-1.7 points on AnCora and COSER; Stanza accurate, with a transformer, is ahead on all four sets. At the same time esSyntax parses 31 thousand words per second in one thread together with the esMorph tags - almost as fast as the spaCy models without a transformer, 23 times faster than spaCy `es_dep_news_trf` and 27 times faster than Stanza - loads in 0.01 s and needs 120 MB of memory, 6 times less than the smallest spaCy model.

## Quality { #quality }

The gold standard is the test parts of the [UD Spanish AnCora](https://github.com/UniversalDependencies/UD_Spanish-AnCora), [GSD](https://github.com/UniversalDependencies/UD_Spanish-GSD), [PUD](https://github.com/UniversalDependencies/UD_Spanish-PUD) and [COSER](https://github.com/UniversalDependencies/UD_Spanish-COSER) treebanks from the UD 2.19 release: news, web texts, news and Wikipedia sentences translated from other languages, and rural speech. The scores are those of the official [CoNLL 2018](https://universaldependencies.org/conll18/evaluation.html) evaluation script: UAS is the share of words with the right head, LAS - with the right head and relation (without its subtype); punctuation is counted. The treebanks follow different conventions, so systems should be compared on the same set rather than sets against each other.

What the models are trained on:

- esSyntax - the training parts of AnCora and GSD, and it parses in the conventions of AnCora;
- spaCy `es_core_news_sm`, `es_core_news_md`, `es_core_news_lg` and the transformer model `es_dep_news_trf` - AnCora;
- Stanza (the `default` package) and Stanza accurate (`default_accurate`, with the bertin-roberta-base-spanish transformer) - AnCora and GSD;
- Stanza ancora (the `ancora` package) - AnCora;
- UDPipe 1 - AnCora of UD 2.5.

AnCora is the home set of every system. PUD and GSD were both annotated by Google with the same guidelines, so the models that learn the conventions of GSD, Stanza and Stanza accurate, are ahead on PUD too. COSER, transcribed rural speech, is new to all of them. UDPipe 2, a web service, and trankit are not compared.

### Raw text { #raw }

Every system splits the text into sentences, tokens and words itself, as it works for the user; esSyntax does it with `parse_text` (anySeg and esMorph). UAS / LAS, %:

| System | AnCora | GSD | PUD | COSER |
| :----- | -----: | --: | --: | ----: |
| esSyntax | 91.94 / 89.25 | 87.06 / 80.95 | 89.57 / 81.97 | 73.66 / 65.52 |
| spaCy es_core_news_sm | 84.07 / 79.77 | 77.96 / 70.48 | 81.90 / 72.82 | 68.08 / 59.24 |
| spaCy es_core_news_md | 84.73 / 80.63 | 78.46 / 71.23 | 82.45 / 73.63 | 68.07 / 59.64 |
| spaCy es_core_news_lg | 84.81 / 80.84 | 78.15 / 70.99 | 82.73 / 73.83 | 66.53 / 58.37 |
| spaCy es_dep_news_trf | 88.46 / 85.01 | 81.40 / 74.45 | 84.84 / 75.85 | 71.22 / 62.73 |
| Stanza | 91.72 / 89.19 | 89.32 / 84.89 | 90.43 / 83.99 | 73.44 / 65.43 |
| Stanza ancora | 92.92 / **90.90** | 86.12 / 80.20 | 89.30 / 81.41 | 73.90 / **66.76** |
| Stanza accurate | 92.97 / 90.67 | 91.02 / **87.14** | 91.34 / **85.17** | 74.57 / 66.47 |
| UDPipe 1 | 84.12 / 78.73 | 77.28 / 68.48 | 82.15 / 72.19 | 67.10 / 58.24 |

An error in the words or sentences carries over to the parse. spaCy does not split `del`, `al` and a verb with its clitics into words, and UDPipe 1 splits only some of them: from the gold words to raw text they lose 2.1-4.2 LAS points, while esSyntax and Stanza lose 0.1-0.8 outside COSER. COSER is transcribed speech without paragraphs, and on it every system finds the sentence boundaries worst.

??? note "Words and sentences"

    Words / sentences F1, %:

    | System | AnCora | GSD | PUD | COSER |
    | :----- | -----: | --: | --: | ----: |
    | esSyntax (anySeg and esMorph) | 99.93 / 98.66 | 99.90 / 90.97 | 99.77 / 98.80 | 99.76 / 83.82 |
    | spaCy es_core_news_sm | 96.60 / 97.70 | 96.39 / 88.14 | 96.60 / 97.34 | 98.41 / 82.65 |
    | spaCy es_core_news_md | 96.60 / 97.42 | 96.39 / 86.99 | 96.60 / 96.89 | 98.41 / 81.26 |
    | spaCy es_core_news_lg | 96.60 / 97.33 | 96.39 / 87.85 | 96.60 / 96.89 | 98.41 / 79.88 |
    | spaCy es_dep_news_trf | 96.60 / 98.96 | 96.39 / 95.62 | 96.60 / 99.20 | 98.41 / 89.47 |
    | Stanza | 99.95 / 98.78 | 99.81 / 93.44 | 99.66 / 98.20 | 99.54 / 79.21 |
    | Stanza ancora | 99.97 / 98.95 | 99.72 / 90.62 | 99.73 / 98.45 | 99.62 / 83.38 |
    | Stanza accurate | 99.95 / 98.34 | 99.79 / 93.67 | 99.65 / 98.35 | 99.53 / 80.12 |
    | UDPipe 1 | 97.12 / 98.32 | 96.83 / 89.18 | 96.96 / 97.60 | 98.66 / 73.99 |

### Gold words { #words }

The systems get the gold words and sentences, with `del` as `de` and `el` and a verb apart from its clitics, and tag them themselves (esSyntax with the esMorph tags in context): this shows the parse without the errors of splitting. UAS / LAS, %:

| System | AnCora | GSD | PUD | COSER |
| :----- | -----: | --: | --: | ----: |
| esSyntax | 92.15 / 89.44 | 87.83 / 81.68 | 89.85 / 82.21 | 75.39 / 67.03 |
| spaCy es_core_news_sm | 87.64 / 82.93 | 82.24 / 74.35 | 85.34 / 75.79 | 71.00 / 61.79 |
| spaCy es_core_news_md | 88.34 / 83.91 | 82.67 / 74.90 | 85.87 / 76.64 | 71.01 / 62.24 |
| spaCy es_core_news_lg | 88.40 / 84.14 | 82.59 / 74.96 | 86.24 / 76.90 | 70.25 / 61.59 |
| spaCy es_dep_news_trf | 92.33 / 88.57 | 85.87 / 78.42 | 88.30 / 78.82 | 73.62 / 64.83 |
| Stanza | 91.86 / 89.32 | 90.02 / 85.51 | 90.85 / 84.37 | 75.99 / 67.74 |
| Stanza ancora | 93.02 / **91.00** | 87.02 / 80.98 | 89.59 / 81.64 | 75.98 / 68.67 |
| Stanza accurate | 93.12 / 90.82 | 91.68 / **87.78** | 91.74 / **85.52** | 77.22 / **68.77** |
| UDPipe 1 | 86.91 / 81.39 | 81.08 / 71.96 | 84.97 / 75.03 | 71.70 / 62.41 |

Every system tags the words with its own tagger, as it does for the user. The parsers of Stanza also read the fine-grained AnCora tags (XPOS) of its tagger, which esMorph does not give, so the systems are not compared on the same morphology.

## Speed { #speed }

Parsing the gold words of AnCora test (53,622 words) in one thread, the best of two runs without loading; esSyntax together with the esMorph tags. Loading is the import and the creation of the parser with the parse of the first sentence; memory is the peak of the process.

| System | Words/s | Loading, s | Memory, MB |
| :----- | ------: | ---------: | ---------: |
| esSyntax | 31,253 | **0.01** | **120** |
| spaCy es_core_news_sm | **34,069** | 1.77 | 743 |
| spaCy es_core_news_md | 31,697 | 1.96 | 955 |
| spaCy es_core_news_lg | 31,484 | 2.03 | 1,525 |
| spaCy es_dep_news_trf | 1,332 | 2.48 | 2,642 |
| Stanza | 1,143 | 2.85 | 3,535 |
| Stanza ancora | 1,146 | 2.90 | 3,592 |
| Stanza accurate | 424 | 3.98 | 4,150 |
| UDPipe 1 | 6,155 | 0.82 | 222 |

spaCy gets the words as a ready `Doc`, esSyntax as an anySeg document, and both tag them before parsing. Stanza accurate was measured on the first 20,034 words. The peak memory depends on the amount of text per call: the other systems got the whole AnCora test in one call, so the memory of Stanza accurate does not compare with theirs. The computer is an Apple M3 Pro with macOS 26 and other applications running: the 1-minute load average was below 4 (3.3-4.0) before every measurement. esSyntax and spaCy `es_core_news_sm`, measured one after the other three times, gave 31,253-31,401 and 32,663-34,069 words per second.

## How to reproduce { #reproduce }

The script `scripts/compare.py` downloads the test parts of the treebanks, the CoNLL 2018 evaluation script and the models of the other systems with their SHA-256 checked (the Stanza models with its own downloader, then the checksums of their files), parses the sets with every system and computes the scores, measures speed, loading and memory in a separate process for every system, and writes the tables. The raw text of a set is the text of its sentences by paragraphs; GSD and COSER have no paragraphs and are one text each. The versions of the packages are pinned in `scripts/compare.py.lock`; esSyntax comes from a wheel built from the repository, and esMorph and anySeg are pinned in the command (their versions go into the results):

``` bash
rm -rf target/compare/wheels
uvx maturin@1.15.0 build --release --locked -o target/compare/wheels
uvx uv@0.13.5 run --with target/compare/wheels/essyntax-*.whl --with esmorph==0.6.0 --with anyseg==0.5.0 \
    scripts/compare.py target/compare
```

Versions: Python 3.11, esMorph 0.6.0, anySeg 0.5.0, spaCy 3.8.16 with the models 3.8.0 without NER, Stanza 1.15.0 with its models 1.15.0 on the CPU (torch 2.14.1, transformers 4.57.6), UDPipe 1.4.0.1 with the `spanish-ancora-ud-2.5-191206` model.
