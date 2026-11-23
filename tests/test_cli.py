import errno
import io
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

import anyseg
import esmorph
import pytest

import essyntax
from essyntax import Parser, __main__ as command

ROOT = Path(__file__).parents[1]
TEXT = "La niña lee un libro. Voy al cine.\n\nPónganselo ya.\n"
WORD = "1\tElla\t_\t_\t_\t_\t_\t_\t_\t_"
FEATS = [
    "Definite=Def|Gender=Fem|Number=Sing|PronType=Art",
    "Gender=Fem|Number=Sing",
    "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin",
]
TAGGED = (
    "# sent_id = a\n# text = La niña lee\n"
    f"1\tLa\t_\tDET\t_\t{FEATS[0]}\t_\t_\t_\t_\n"
    f"2\tniña\t_\tNOUN\t_\t{FEATS[1]}\t_\t_\t_\t_\n"
    f"3\tlee\t_\tVERB\t_\t{FEATS[2]}\t_\t_\t_\t_\n\n"
)


@pytest.fixture(scope="module")
def parser():
    return Parser()


def call(*args, data=b""):
    stdout, stderr = io.BytesIO(), io.StringIO()
    code = command.run(list(args), io.BytesIO(data), stdout, stderr)
    return code, stdout.getvalue().decode(), stderr.getvalue()


def run(*args, data=b""):
    return subprocess.run(
        [sys.executable, "-m", "essyntax", *args], input=data, capture_output=True, check=False
    )


def sentence_ids(conllu):
    return [int(number) for number in re.findall(r"^# sent_id = (\d+)$", conllu, re.MULTILINE)]


def esmorph_conllu(*files):
    return subprocess.run(
        [sys.executable, "-m", "esmorph", "-f", "conllu", *map(str, files)],
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout


def without_syntax(conllu):
    return [re.sub(r"^((?:[^\t]*\t){6})[^\t]*\t[^\t]*", r"\1_\t_", line) for line in conllu]


class Chunks:
    """Input of size bytes a read: the chunks end in the middle of lines and characters"""

    def __init__(self, data, size=1):
        self.data, self.size = data, size

    def read(self, size):
        chunk, self.data = self.data[: self.size], self.data[self.size :]
        return chunk


class NonBlocking:
    """A non-blocking descriptor without data: read returns None"""

    def read(self, size):
        return None


def test_text(parser):
    code, out, err = call(data=TEXT.encode())
    assert (code, err) == (0, "")
    assert out == parser.parse_text(TEXT).to_conllu()
    assert sentence_ids(out) == [1, 2, 3]


def test_text_multiword_tokens():
    # Contractions of anySeg and verbs with clitics of esMorph are multiword tokens of the output
    code, out, _ = call(data=TEXT.encode())
    assert code == 0
    lines = out.splitlines()
    assert "2-3\tal\t_\t_\t_\t_\t_\t_\t_\t_" in lines
    assert "1-3\tPónganselo\t_\t_\t_\t_\t_\t_\t_\t_" in lines
    words = [line.split("\t") for line in lines if re.match(r"\d+\t", line)]
    assert [word[1] for word in words[-5:]] == ["Pongan", "se", "lo", "ya", "."]
    assert all(word[6].isdigit() and word[7] != "_" for word in words)


def test_text_like_esmorph(tmp_path):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_text(TEXT, encoding="utf-8")
    second.write_bytes("﻿El gato duerme.\r\nY ya.\r\n".encode())
    code, out, err = call(str(first), str(second))
    assert (code, err) == (0, "")
    assert out.count("# newdoc\n") == 2
    assert sentence_ids(out) == [1, 2, 3, 4, 5]
    morphology = esmorph_conllu(first, second)
    assert without_syntax(out.splitlines()) == without_syntax(morphology.splitlines())


def test_conllu_from_esmorph(tmp_path):
    # The output of esmorph keeps its columns and gets the heads and relations of the text input
    path = tmp_path / "text.txt"
    path.write_text(TEXT, encoding="utf-8")
    morphology = esmorph_conllu(path)
    code, out, err = call("-i", "conllu", data=morphology.encode())
    assert (code, err) == (0, "")
    assert out == call(str(path))[1]
    assert without_syntax(out.splitlines()) == without_syntax(morphology.splitlines())


def test_text_in_pieces(parser):
    # The segmenter cuts a long paragraph without blank lines into pieces: numbers and the paragraph
    # go on
    text = "Supercalifragilístico extraordinariamente. " * 9000 + "\n\nEl gato duerme.\n"
    code, out, err = call(data=text.encode())
    assert (code, err) == (0, "")
    assert sentence_ids(out) == list(range(1, 9002))
    assert (out.count("# newdoc\n"), out.count("# newpar\n")) == (1, 2)
    # Chunks of a byte: lines and characters break at the bounds of the reads
    stdout = io.BytesIO()
    assert command.run([], Chunks(TEXT.encode()), stdout, io.StringIO()) == 0
    assert stdout.getvalue().decode() == parser.parse_text(TEXT).to_conllu()


def test_long_line(parser):
    # A line longer than a chunk of reading is given in parts at the bounds of characters
    text = "El niño y la niña duermen. " * 6000 + "\n"
    code, out, _ = call(data=text.encode())
    assert code == 0
    assert out == parser.parse_text(text).to_conllu()


def test_non_blocking_input():
    # "No data yet" is an error of reading, not the end of the input
    stdout, stderr = io.BytesIO(), io.StringIO()
    assert command.run([], NonBlocking(), stdout, stderr) == 1
    assert stderr.getvalue() == f"essyntax: -: {os.strerror(errno.EAGAIN)}\n"
    assert stdout.getvalue() == b""


def test_empty_input():
    assert call() == (0, "", "")
    assert call(data=b"\n \n\n") == (0, "", "")
    stdout, stderr = io.BytesIO(), io.StringIO()
    assert command.run([], None, stdout, stderr) == 0
    assert stdout.getvalue() == b""


def test_conllu_tagged(parser):
    code, out, err = call("-i", "conllu", data=TAGGED.encode())
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[:2] == ["# sent_id = a", "# text = La niña lee"]
    expected = parser.parse(["La", "niña", "lee"], ["DET", "NOUN", "VERB"], FEATS)
    assert [tuple(line.split("\t")[6:8]) for line in lines[2:5]] == [
        (str(head), deprel) for head, deprel in expected
    ]
    # The lemmas of the input are not filled: the morphology is not touched
    assert [line.split("\t")[2] for line in lines[2:5]] == ["_", "_", "_"]


def test_conllu_untagged(parser):
    # esMorph tags a sentence without parts of speech, a tagged one stays as it is
    untagged = "# newdoc id = x\n" + WORD + "\n2\tduerme\t_\t_\t_\t_\t_\t_\t_\t_\n\n"
    code, out, err = call("--input=conllu", data=(untagged + TAGGED).encode())
    assert (code, err) == (0, "")
    first, second = anyseg.read_conllu(untagged)[0], anyseg.read_conllu(TAGGED)[0]
    first = esmorph.Analyzer().annotate(first)
    parser.annotate(first)
    parser.annotate(second)
    assert out == first.to_conllu() + second.to_conllu()
    assert out.splitlines()[1].split("\t")[2:4] == ["él", "PRON"]


def test_conllu_untagged_multiword_tokens():
    # esMorph splits a verb with clitics of an untagged sentence into its words, as esmorph does
    conllu = "1\tPónganselo\t_\t_\t_\t_\t_\t_\t_\t_\n2\tya\t_\t_\t_\t_\t_\t_\t_\t_\n\n"
    code, out, err = call("-i", "conllu", data=conllu.encode())
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[0] == "1-3\tPónganselo\t_\t_\t_\t_\t_\t_\t_\t_"
    assert [line.split("\t")[1] for line in lines[1:5]] == ["Pongan", "se", "lo", "ya"]
    assert [line.split("\t")[6] for line in lines[1:5]].count("0") == 1


def test_conllu_errors(tmp_path):
    path = tmp_path / "broken.conllu"
    path.write_text(TAGGED + WORD + "\n2\tduerme\n\n" + TAGGED, encoding="utf-8")
    code, out, err = call("-iconllu", str(path), str(path))
    assert code == 1
    # The sentences before the error are parsed, the other files too
    assert out.count("# sent_id = a\n") == 2
    message = f"essyntax: {path}: line 8: expected 10 tab-separated columns, got 2\n"
    assert err == message * 2
    mixed = TAGGED + WORD.replace("\t_\t_\t_\t_\t_", "\t_\tPRON\t_\t_\t_") + "\n" + WORD + "\n\n"
    code, out, err = call("-i", "conllu", data=mixed.encode())
    assert (code, out.count("# sent_id = a\n")) == (1, 1)
    assert err == (
        "essyntax: -: line 8: the word has no part of speech, while other words of the sentence "
        "do\n"
    )
    code, _, err = call("-i", "conllu", data=TAGGED.replace("VERB", "verb").encode())
    assert code == 1
    assert err.startswith("essyntax: -: line 5: unknown part of speech 'verb': expected")
    # Of two errors of a sentence the first by lines is reported
    broken = "1\tElla\t_\tPRON\t_\t_\tz\t_\t_\t_\n2\tduerme\t_\tverb\t_\t_\t_\t_\t_\t_\n\n"
    assert (
        call("-i", "conllu", data=broken.encode())[2]
        == 'essyntax: -: line 1: cannot read the head "z"\n'
    )
    assert call("-i", "conllu", data=broken.replace("verb", "VERB").encode())[2] == (
        'essyntax: -: line 1: cannot read the head "z"\n'
    )


@pytest.mark.parametrize(
    ("conllu", "message"),
    [
        (WORD.replace("1\t", "x\t", 1) + "\n", 'line 1: expected word 1, got "x"'),
        (WORD.replace("1\t", "1.x\t", 1) + "\n", 'line 1: cannot read the ID "1.x"'),
        ("1\tElla\t_\t_\t_\t_\tz\t_\t_\t_\n", 'line 1: cannot read the head "z"'),
        ("1-2" + WORD[1:] + "\n" + WORD + "\n", "line 1: a multiword token without all its words"),
        ("2-3" + WORD[1:] + "\n", "line 1: multiword token 2-3 does not start at word 1"),
        ("# newdoc\n", "line 1: a sentence without words"),
        (WORD + "\n# c\n", "line 2: a comment after token lines"),
        (
            "# text = Él\n" + WORD + "\n",
            'line 2: the form "Ella" does not match the text of the sentence',
        ),
        (
            "# text = Ella y\n" + WORD + "\n",
            "line 1: the text of the sentence holds characters that no token has",
        ),
    ],
)
def test_conllu_messages(conllu, message):
    # The messages of anySeg come with the line of the file
    code, _, err = call("-i", "conllu", data=conllu.encode())
    assert (code, err) == (1, f"essyntax: -: {message}\n")


def test_conllu_line_ends_and_pieces(parser):
    # The line ends CR and CRLF, as in text; lines broken by reading are the same
    expected = call("-i", "conllu", data=TAGGED.encode())[1]
    for end in ("\r", "\r\n"):
        assert call("-i", "conllu", data=TAGGED.replace("\n", end).encode()) == (0, expected, "")
    stdout = io.BytesIO()
    assert command.run(["-i", "conllu"], Chunks(TAGGED.encode(), 7), stdout, io.StringIO()) == 0
    assert stdout.getvalue().decode() == expected
    # A very long line without a line end is one error, without a quadratic joining
    code, _, err = call("-i", "conllu", data=b"x" * 3_000_000)
    assert (code, err) == (1, "essyntax: -: line 1: expected 10 tab-separated columns, got 1\n")


def test_crlf_split_between_reads():
    # A chunk of reading ends between CR and LF: there is no blank line in the middle of a sentence
    pieces: list[bytes] = []

    class Pieces(command.Input):
        def read(self, size=command.CHUNK, /):
            return pieces.pop(0) if pieces else b""

    def lines(*chunks):
        pieces.extend(chunks)
        reader = Pieces(io.BytesIO(), lambda: None)
        return [item for item in reader.lines() if item is not None]

    assert lines(b"# a\r", b"\n1\r", b"\r\n2\r", b"\n\r\n", b"3\r") == [
        (1, "# a"),
        (2, "1"),
        (3, ""),
        (4, "2"),
        (5, ""),
        (6, "3"),
    ]
    # A held CR followed by the last line without a line end
    assert lines(b"1\r", b"2") == [(1, "1"), (2, "2")]


def test_encoding(tmp_path):
    damaged = "La niña lee.\n\n".encode() + b"\xff el gato\n"
    code, out, err = call(data=damaged)
    assert code == 1
    assert "�" in out and "gato" in out
    assert err == "essyntax: -: line 3: not UTF-8, the wrong bytes are replaced with U+FFFD\n"
    # A file in Latin-1 with ASCII at the start (subtitles) is not parsed, not even in part
    subtitles = tmp_path / "latin1.srt"
    subtitles.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nLa niña lee\n".encode("latin-1"))
    assert call(str(subtitles)) == (
        1,
        "",
        f"essyntax: {subtitles}: the file is not in UTF-8 (line 3)\n",
    )
    assert (
        call(data="El gato duerme\n".encode("utf-16"))[2]
        == "essyntax: -: the file is not in UTF-8 (line 1)\n"
    )
    assert call(data=b"A\r\nB\x00\n")[2] == "essyntax: -: the file is not in UTF-8 (line 2)\n"
    # After a line of UTF-8 a NUL is part of the text, and wrong bytes in CoNLL-U are replaced too
    assert call(data="Niño\nB\x00\n".encode())[0] == 0
    conllu = (
        (TAGGED + "1\tNi\xffo\t_\tNOUN\t_\t_\t_\t_\t_\t_\n\n")
        .encode()
        .replace(b"\xc3\xbf", b"\xff")
    )
    code, out, err = call("-i", "conllu", data=conllu)
    assert (code, err) == (
        1,
        "essyntax: -: line 7: not UTF-8, the wrong bytes are replaced with U+FFFD\n",
    )
    assert "Ni�o" in out


def test_files(tmp_path):
    path = tmp_path / "text.txt"
    path.write_text(TEXT, encoding="utf-8")
    code, out, err = call(str(tmp_path / "ningún.txt"), str(tmp_path), str(path))
    assert code == 1
    assert sentence_ids(out) == [1, 2, 3]
    assert err == (
        f"essyntax: {tmp_path / 'ningún.txt'}: no such file\n"
        f"essyntax: {tmp_path}: is a directory\n"
    )
    # After "--" a name with a dash is a file
    dashed = tmp_path / "-text.txt"
    dashed.write_text(TEXT, encoding="utf-8")
    code, out, _ = call("--", str(dashed), data=b"")
    assert code == 0 and sentence_ids(out) == [1, 2, 3]
    assert call("-", data=TEXT.encode())[1] == out


def test_output_file(tmp_path):
    path, output = tmp_path / "text.txt", tmp_path / "text.conllu"
    path.write_text(TEXT, encoding="utf-8")
    assert call("-o", str(output), str(path)) == (0, "", "")
    assert output.read_text(encoding="utf-8") == call(str(path))[1]
    assert call("--output", "-", str(path))[1] == output.read_text(encoding="utf-8")
    # An output file that would overwrite an input or the model is not created
    message = f"essyntax: {path}: the output file is an input file or the model file\n"
    assert call("-o", str(path), str(path)) == (1, "", message)
    model = tmp_path / "model.bin"
    shutil.copy(ROOT / "data" / "es-syntax.bin", model)
    assert call("-m", str(model), "-o", str(model), str(path))[0] == 1
    assert path.read_text(encoding="utf-8") == TEXT
    assert call("-o", str(tmp_path), str(path)) == (
        1,
        "",
        f"essyntax: {tmp_path}: is a directory\n",
    )
    if sys.platform != "win32":
        # The standard input from the output file
        with path.open("rb") as stdin:
            result = subprocess.run(
                [sys.executable, "-m", "essyntax", "-o", str(path)],
                stdin=stdin,
                capture_output=True,
                check=False,
            )
        assert result.returncode == 1
        assert path.read_text(encoding="utf-8") == TEXT
        # The input /dev/stdin: on macOS stat of this path is a file of devfs, not the redirected file
        for name in ("/dev/stdin", "/dev/fd/0"):
            with path.open("rb") as stdin:
                result = subprocess.run(
                    [sys.executable, "-m", "essyntax", "-o", str(path), name],
                    stdin=stdin,
                    capture_output=True,
                    check=False,
                )
            assert result.returncode == 1, name
            assert path.read_text(encoding="utf-8") == TEXT
        # The standard output appended to an input file
        with path.open("ab") as stdout:
            result = subprocess.run(
                [sys.executable, "-m", "essyntax", str(path)],
                stdout=stdout,
                stderr=subprocess.PIPE,
                check=False,
            )
        assert result.returncode == 1
        assert (
            result.stderr == b"essyntax: the standard output is an input file or the model file\n"
        )
        assert path.read_text(encoding="utf-8") == TEXT


def test_closed_stdout(tmp_path, monkeypatch):
    # A closed standard output (>&-) is an error, as nothing would be written
    path = tmp_path / "text.conllu"
    for args in ([], ["-V"]):
        stderr = io.StringIO()
        assert command.run(args, io.BytesIO(TEXT.encode()), None, stderr) == 1
        assert stderr.getvalue() == "essyntax: the standard output is closed\n"
    stderr = io.StringIO()
    assert command.run(["-o", str(path)], io.BytesIO(TEXT.encode()), None, stderr) == 0
    assert path.read_text(encoding="utf-8") == call(data=TEXT.encode())[1]
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(raw, encoding="utf-8"))
    monkeypatch.setattr(sys, "argv", ["essyntax", "-V"])
    with pytest.raises(SystemExit) as exit_info:
        command.main()
    assert exit_info.value.code == 1
    assert raw.getvalue() == b"essyntax: the standard output is closed\n"


def test_model_option(tmp_path, monkeypatch):
    model = tmp_path / "model.bin"
    shutil.copy(ROOT / "data" / "es-syntax.bin", model)
    assert call("--model", str(model), data=TEXT.encode())[1] == call(data=TEXT.encode())[1]
    model.write_bytes(b"not a model")
    code, out, err = call("-m", str(model), data=TEXT.encode())
    assert (code, out) == (1, "")
    assert err.startswith(f"essyntax: {model}: ")
    # A model that cannot be opened is as the input files: the path as given and the reason
    missing = tmp_path / "ningún.bin"
    assert call("-m", str(missing)) == (1, "", f"essyntax: {missing}: no such file\n")
    assert call("-m", str(tmp_path)) == (1, "", f"essyntax: {tmp_path}: is a directory\n")
    # The paths are as given: relative ones and an empty one
    monkeypatch.chdir(tmp_path)
    for name in ("model.bin", "./model.bin"):
        code, _, err = call("-m", name)
        assert code == 1
        assert err.startswith(f"essyntax: {name}: wrong model format: ")
    assert call("-m", "./ningún.bin") == (1, "", "essyntax: ./ningún.bin: no such file\n")
    assert call("-m", "") == (1, "", "essyntax: : no such file\n")
    assert call("-o", "", data=TEXT.encode()) == (1, "", "essyntax: : no such file\n")
    message = "essyntax: ./ningún/x.conllu: no such file\n"
    assert call("-o", "./ningún/x.conllu", data=TEXT.encode()) == (1, "", message)
    assert call("./ningún.txt") == (1, "", "essyntax: ./ningún.txt: no such file\n")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--format", "xml"], "unknown option --format"),
        (["-i", "tokens"], "unknown input tokens, expected one of: text, conllu"),
        (["--model"], "option --model needs a value"),
        (["-hx"], "unknown option -hx"),
        (["--version=1"], "unknown option --version=1"),
    ],
)
def test_usage_errors(args, message):
    assert call(*args) == (2, "", f"essyntax: {message}\nHelp: essyntax --help\n")


def test_help_and_version():
    code, out, _ = call("--help")
    assert code == 0 and out.startswith("essyntax - dependency parsing of Spanish text")
    assert call("-h")[1] == out
    versions = f"anyseg {anyseg.__version__}, esmorph {esmorph.__version__}"
    assert call("-V") == (0, f"essyntax {essyntax.__version__} ({versions})\n", "")


class Closed(io.BytesIO):
    def __init__(self, error):
        super().__init__()
        self.error = error

    def write(self, data):
        raise self.error


def test_write_errors():
    stderr = io.StringIO()
    assert command.run([], io.BytesIO(TEXT.encode()), Closed(BrokenPipeError()), stderr) == 0
    assert command.run(["-V"], None, Closed(BrokenPipeError()), stderr) == 0
    assert stderr.getvalue() == ""
    assert command.run([], io.BytesIO(TEXT.encode()), Closed(OSError(28, "No space")), stderr) == 1
    assert stderr.getvalue() == "essyntax: write error: [Errno 28] No space\n"


def test_closed_pipe(tmp_path):
    path = tmp_path / "text.txt"
    path.write_text(TEXT * 3000, encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "essyntax", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None and process.stderr is not None
    assert process.stdout.readline().decode() == "# newdoc\n"
    process.stdout.close()
    assert process.wait(timeout=60) == 0
    assert process.stderr.read() == b""


@pytest.mark.parametrize(
    ("args", "paragraph"), [([], "Somos amigos\n\n"), (["-i", "conllu"], WORD + "\n\n")]
)
def test_paragraph_by_paragraph(args, paragraph):
    # The command answers every paragraph without waiting for the end of the input: it can be kept
    # open
    process = subprocess.Popen(
        [sys.executable, "-m", "essyntax", *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        encoding="utf-8",
    )
    assert process.stdin is not None and process.stdout is not None
    stdout = process.stdout
    try:
        for _ in range(2):
            process.stdin.write(paragraph)
            process.stdin.flush()
            lines: list[str] = []

            def read(out: list[str] = lines) -> None:
                while not out or out[-1] not in {"\n", ""}:
                    out.append(stdout.readline())

            reader = threading.Thread(target=read)
            reader.start()
            reader.join(timeout=60)
            assert lines[-1] == "\n" and lines[-2].split("\t")[1] in {"amigos", "Ella"}
    finally:
        process.stdin.close()
        process.wait(timeout=60)


def test_console_script():
    script = shutil.which("essyntax", path=str(Path(sys.executable).parent))
    assert script is not None
    result = subprocess.run([script, "-V"], capture_output=True, encoding="utf-8", check=False)
    assert result.stdout.startswith(f"essyntax {essyntax.__version__} (")


def test_main_in_process(tmp_path, monkeypatch, capfd):
    path = tmp_path / "text.txt"
    path.write_text(TEXT, encoding="utf-8")
    handlers = []
    monkeypatch.setattr(signal, "signal", lambda *args: handlers.append(args))
    monkeypatch.setattr(sys, "argv", ["essyntax", str(path)])
    with pytest.raises(SystemExit) as exit_info:
        command.main()
    assert exit_info.value.code == 0
    assert handlers[0] == (signal.SIGINT, signal.SIG_DFL)
    assert capfd.readouterr().out.startswith("# newdoc\n# newpar\n# sent_id = 1\n")
    # An ignored SIGINT stays ignored
    handlers.clear()
    monkeypatch.setattr(signal, "getsignal", lambda _: signal.SIG_IGN)
    with pytest.raises(SystemExit):
        command.main()
    assert handlers == []


def test_messages_in_utf8(tmp_path, monkeypatch):
    # The stream of errors is not a console: the messages are in UTF-8, not in the encoding of the
    # stream of Python
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(raw, encoding="ascii"))
    monkeypatch.setattr(sys, "argv", ["essyntax", str(tmp_path / "ningún.txt")])
    with pytest.raises(SystemExit) as exit_info:
        command.main()
    assert exit_info.value.code == 1
    assert raw.getvalue().decode() == f"essyntax: {tmp_path / 'ningún.txt'}: no such file\n"
    # The wrapper does not close the stream of errors of Python
    sys.stderr.write("open")


def test_closed_stderr(tmp_path, monkeypatch):
    # A closed stream of errors: there is nowhere to write a message, the exit code is the same
    raw = io.BytesIO()
    closed = io.TextIOWrapper(raw)
    raw.close()
    monkeypatch.setattr(sys, "stderr", closed)
    monkeypatch.setattr(sys, "argv", ["essyntax", str(tmp_path / "ningún.txt")])
    with pytest.raises(SystemExit) as exit_info:
        command.main()
    assert exit_info.value.code == 1


def test_subprocess_smoke():
    result = run("-i", "conllu", data=TAGGED.encode())
    assert (result.returncode, result.stderr) == (0, b"")
    heads = [line.split("\t")[6] for line in result.stdout.decode().splitlines()[2:5]]
    assert heads.count("0") == 1
