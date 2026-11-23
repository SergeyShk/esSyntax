# The essyntax command

``` bash
essyntax [options] [file ...]
```

The command parses text from files or the standard input and writes [CoNLL-U](https://universaldependencies.org/format.html): for every word its lemma, part of speech and features, its head and its [Universal Dependencies](https://universaldependencies.org/) relation. It is installed with the package (`pip install essyntax`) and also runs as `python -m essyntax`. The [anySeg](https://sergeyshk.github.io/anySeg/) segmenter splits the text into sentences, tokens and their words, and the [esMorph](https://sergeyshk.github.io/esMorph/) morphological analyzer gives the parts of speech and features - the versions installed with the package - so the result is that of [`parse_text`](parser.md#parse_text).

In one thread the command parses about 30 thousand words a second of raw text together with the segmentation and the morphology (the raw text of UD Spanish PUD test, Apple M3 Pro); other parsers are compared on the [Comparison](performance.md) page.

``` bash
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

## Options { #options }

| Option | Default | Description |
| :----- | :------ | :---------- |
| `-i`, `--input` | `text` | [Input](#input): `text`, `conllu` |
| `-m`, `--model` | the package model | An esSyntax model file, as in [`Parser(path)`](parser.md#parameters) |
| `-o`, `--output` | the standard output | The result file; `-` is the standard output |
| `-h`, `--help` | | Show the help |
| `-V`, `--version` | | Show the versions of esSyntax, anySeg and esMorph |

Files are read one after another; without files and in place of `-` the standard input is read. The input is in UTF-8: a file in another encoding (Latin-1, cp1252, UTF-16) is not parsed, unless its first letter with an accent comes after the first 64 KiB: then the paragraphs of the pieces of 64 KiB read before that line are parsed. A single line with invalid bytes is parsed with U+FFFD in their place. An option value is written separately or attached: `-i conllu`, `-iconllu`, `--input=conllu`; a file name starting with a hyphen goes after `--`. Text is parsed by paragraphs and CoNLL-U by sentences: the result is written as soon as a blank line or the end of the input closes the paragraph or the sentence - on a terminal at once, and to a pipe or a file whenever the command waits for the next line of input, so it can be kept open and fed text paragraph by paragraph.

In Windows PowerShell 5.1 the `>` redirection and a pipeline (`Get-Content text.txt | essyntax`) corrupt letters with accents: pass the file as an argument and write the result with the `-o` option (in PowerShell 7 they work too). Text passed with `echo` in cmd comes in the console encoding: run `chcp 65001` first. Neither cmd nor PowerShell expands file patterns (`*.txt`).

## Input { #input }

- `text` - text: a blank line ends a paragraph. The anySeg segmenter finds the tokens, their words and the sentences following the conventions of Universal Dependencies that the esMorph and esSyntax models are trained on: `del` and `al` are two words, and so are an infinitive or a gerund with clitics (`dárselo`); esMorph splits into words a token that the segmenter leaves whole and whose analysis has several (`Llévalo` is `Lleva` + `lo`). A sentence may go across a line break. A paragraph without blank lines longer than 256 KiB (a file with a sentence per line, a single long line) is parsed in pieces that end at a sentence boundary: the memory does not grow with the input, and the sentence numbers and the paragraph go on across the pieces; a sentence longer than 256 KiB is cut.
- `conllu` - [CoNLL-U](https://universaldependencies.org/format.html) with parts of speech (UPOS) and features (FEATS): the HEAD and DEPREL columns are filled, and the other columns, the comments, multiword tokens and empty nodes stay as they are (the DEPS column does not change either). A part of speech is one of the 17 UD parts of speech in capitals. A sentence where no word has a part of speech goes through esMorph first: LEMMA, UPOS and FEATS are filled, and a token whose analysis has several words gets them, as with the `esmorph -i conllu` command; a part of speech on some words of a sentence but not on all is an error. The file is read as by `anyseg.read_conllu`: the word IDs go in order, a multiword token has all its words, the forms agree with the comment `text` if there is one, and a sentence has words. This is stricter than `esmorph -i conllu`, which writes a wrong sentence as it is and goes on: at a wrong line the parsing of the file stops, the sentences before it are written, and the next files are parsed.

``` bash
printf '1\tElla\t_\tPRON\t_\tCase=Nom|Person=3\t_\t_\t_\t_\n2\tduerme\t_\tVERB\t_\tMood=Ind|Person=3\t_\t_\t_\t_\n' | essyntax -i conllu
```

```
1	Ella	_	PRON	_	Case=Nom|Person=3	2	nsubj	_	_
2	duerme	_	VERB	_	Mood=Ind|Person=3	0	root	_	_
```

The model is trained on the tags of esMorph, and the features should be complete; with the gold tags of the treebanks LAS on the gold words of AnCora dev and GSD dev is 0.4 and 1.4 points higher. To replace the morphology of a CoNLL-U file with that of esMorph and parse it, pipe the commands:

``` bash
esmorph -i conllu -f conllu gold.conllu | essyntax -i conllu > parsed.conllu
```

## Output { #output }

CoNLL-U as anySeg writes it. For the `text` input it is that of the `esmorph -f conllu` command with HEAD and DEPREL filled: a file starts with the comment `newdoc`, a paragraph with `newpar`, a sentence has the comments `sent_id` (numbered across all the files) and `text`; MISC has `SpaceAfter=No` on a token with no space after it in its paragraph and `SpacesAfter` where the space is not a single one, and the indent of a paragraph is `SpacesBefore` of its first token. A multiword token is a line with the range of its words (`1-2`) and the form of the token, followed by the lines of its words; the heads and the relations are those of the words, so the token line keeps `_` in HEAD and DEPREL. For the `conllu` input a sentence is written as it was read, with the new heads and relations. Lines end with LF, the text is in UTF-8.

``` bash
echo "Llévalo al coche." | essyntax
```

```
# newdoc
# newpar
# sent_id = 1
# text = Llévalo al coche.
1-2	Llévalo	_	_	_	_	_	_	_	_
1	Lleva	llevar	VERB	_	Mood=Imp|Number=Sing|Person=2|VerbForm=Fin	0	root	_	_
2	lo	él	PRON	_	Case=Acc|Gender=Masc|Number=Sing|Person=3|PrepCase=Npr|PronType=Prs	1	obj	_	_
3-4	al	_	_	_	_	_	_	_	_
3	a	a	ADP	_	_	5	case	_	_
4	el	el	DET	_	Definite=Def|Gender=Masc|Number=Sing|PronType=Art	5	det	_	_
5	coche	coche	NOUN	_	Gender=Masc|Number=Sing	1	obl:arg	_	SpaceAfter=No
6	.	.	PUNCT	_	PunctType=Peri	1	punct	_	_
```

## Exit codes { #exit-codes }

| Code | When |
| :--- | :--- |
| 0 | Success, including when the output is closed before the end (`essyntax text.txt \| head`) |
| 1 | An input file is missing, cannot be read or is not in UTF-8, a line is not in UTF-8 (it is parsed with U+FFFD), a CoNLL-U line is wrong or a part of speech is unknown; the sentences before the error are parsed, and so are the other files |
| 1 | The model cannot be read, the output file cannot be created or is an input file or the model file; nothing is parsed |
| 1 | A write error; parsing stops |
| 2 | Invalid options |

Error messages go to the standard error with the file and the line:

``` bash
printf '1\tElla\t_\tPRON\t_\t_\t_\t_\t_\t_\n2\tduerme\t_\t_\t_\t_\t_\t_\t_\t_\n' | essyntax -i conllu
```

```
essyntax: -: line 2: the word has no part of speech, while other words of the sentence do
```
