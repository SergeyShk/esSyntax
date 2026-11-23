# Spanish dependency parser (esSyntax)
#
# Copyright (C) 2026
# Author: Sergey Shkarin <kouki.sergey@gmail.com>
# URL: <https://github.com/SergeyShk/esSyntax>

"""
The essyntax command: dependency parsing of text from files and the standard input

Example:
    essyntax text.txt
    essyntax --input conllu tagged.conllu
    python -m essyntax --help
"""

import codecs
import contextlib
import errno
import io
import os
import re
import signal
import stat
import sys
import threading
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import BinaryIO, NoReturn, Protocol, TextIO

import anyseg
import esmorph

from ._essyntax import Parser, __version__

HELP = """\
essyntax - dependency parsing of Spanish text: the head and the Universal Dependencies relation of
every word

Usage: essyntax [options] [file ...]

Files are read one after another; without files and in place of "-" the standard input is
read, in UTF-8. The result, CoNLL-U, goes to the standard output or to the file of -o.

Options:
  -i, --input INPUT        input:
                             text - text: a blank line ends a paragraph, the anySeg segmenter
                             finds the tokens, their words and the sentences, esMorph the
                             parts of speech and the features (default)
                             conllu - CoNLL-U with parts of speech and features; esMorph tags a
                             sentence without parts of speech first
  -m, --model FILE         esSyntax model file (default: the model of the package)
  -o, --output FILE        write the result to a file
  -h, --help               show this help and exit
  -V, --version            show the versions of esSyntax, anySeg and esMorph and exit
"""

# The input is read in chunks: so many bytes a read, and no longer an unfinished line in memory
CHUNK = 1 << 16
UPOS = frozenset((
    "ADJ", "ADP", "ADV", "AUX", "CCONJ", "DET", "INTJ", "NOUN", "NUM",
    "PART", "PRON", "PROPN", "PUNCT", "SCONJ", "SYM", "VERB", "X",
))  # fmt: skip
SENT_ID = re.compile(r"^# sent_id = (\d+)$", re.MULTILINE)
# Line ends, as in the commands anyseg and esmorph: LF, CR and CRLF
LINE_END = re.compile(r"\r\n|\r|\n")
CONLLU_ERROR = re.compile(r"line (\d+): (.*)", re.DOTALL)


class _Raw(Protocol):
    def read(self, size: int, /) -> bytes | None: ...


class UsageError(Exception):
    """Wrong arguments of the command"""


class EncodingError(Exception):
    """The file is not in UTF-8: the number of the line where it shows"""

    def __init__(self, line: int) -> None:
        super().__init__(line)
        self.line = line


class InputError(Exception):
    """A wrong line of CoNLL-U: the number of the line and the message"""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(line, message)
        self.line = line
        self.message = message


class WriteError(Exception):
    """An error of writing the result"""

    def __init__(self, error: OSError) -> None:
        super().__init__(error)
        self.error = error


@dataclass
class Options:
    """The arguments of a run of the command"""

    conllu: bool
    model: str | None
    output: str | None
    files: list[str]


def parse_args(args: Sequence[str]) -> Options | str:
    """
    Parsing of the command line arguments

    Arguments:
        args (Sequence[str]): The arguments without the name of the program

    Returns:
        Options | str: The arguments of the run or "help" and "version" for the help and the version

    Raises:
        UsageError: If an option is unknown, has no value or a wrong one
    """
    conllu, model, output, files = False, None, None, []
    options = True
    rest = iter(args)
    for arg in rest:
        if not (options and arg.startswith("-") and arg != "-"):
            files.append(arg)
            continue
        if arg.startswith("--"):
            name, equals, attached = arg.partition("=")
            inline = attached if equals else None
        elif len(arg) > 2:
            name, inline = arg[:2], arg[2:]
        else:
            name, inline = arg, None
        if name in {"--", "-h", "--help", "-V", "--version"}:
            if inline is not None:
                raise UsageError(f"unknown option {arg}")
            if name == "--":
                options = False
                continue
            return "help" if name in {"-h", "--help"} else "version"
        if name not in {"-i", "--input", "-m", "--model", "-o", "--output"}:
            raise UsageError(f"unknown option {arg}")
        value = inline if inline is not None else next(rest, None)
        if value is None:
            raise UsageError(f"option {name} needs a value")
        if name in {"-i", "--input"}:
            if value not in {"text", "conllu"}:
                raise UsageError(f"unknown input {value}, expected one of: text, conllu")
            conllu = value == "conllu"
        elif name in {"-m", "--model"}:
            model = value
        else:
            output = None if value == "-" else value
    return Options(conllu, model, output, files)


class Input:
    """
    The input of the command in UTF-8, as in the commands anyseg and esmorph

    Description:
        The bytes are read in chunks and given as whole lines, and a line longer than a chunk in
        parts at the bounds of characters. Wrong bytes of UTF-8 and NUL before the first line of
        UTF-8 with non-ASCII characters mean another encoding of the file (Latin-1, UTF-16), after
        it a damaged line: its wrong bytes are replaced with U+FFFD. Before every read that may
        wait for input waiting is called: the result of what is parsed reaches the reader

    Arguments:
        raw (_Raw): A file open for reading in binary mode without a buffer
        waiting (Callable[[], None]): What to do before a read
    """

    def __init__(self, raw: _Raw, waiting: Callable[[], None]) -> None:
        self._raw = raw
        self._waiting = waiting
        self._rest = b""
        self._ready = b""
        self._line = 1
        self._utf8 = False
        self._start = True
        self._end = False
        # The first line whose wrong bytes are replaced with U+FFFD
        self.invalid: int | None = None

    def read(self, size: int = CHUNK, /) -> bytes:
        """
        The next bytes of the input

        Arguments:
            size (int): How many bytes to give at most

        Returns:
            bytes: Bytes of UTF-8, empty at the end of the input

        Raises:
            EncodingError: If the input is not in UTF-8
            OSError: If the file cannot be read
        """
        while not self._ready and not self._end:
            self._fill()
        ready, self._ready = self._ready[:size], self._ready[size:]
        return ready

    def _fill(self) -> None:
        self._waiting()
        data = self._raw.read(CHUNK)
        # A non-blocking descriptor without data is an error of reading, as in the commands anyseg
        # and esmorph
        if data is None:
            raise BlockingIOError(errno.EAGAIN, os.strerror(errno.EAGAIN))
        if self._start and data.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise EncodingError(1)
        self._start = self._start and not data
        if not data:
            self._end = True
            chunk, self._rest = self._rest, b""
        else:
            data = self._rest + data
            # A CR at the end of a chunk may be the start of a CRLF
            cut = max(data.rfind(b"\n"), data.rfind(b"\r", 0, len(data) - 1)) + 1
            if not cut:
                if len(data) < CHUNK:
                    self._rest = data
                    return
                cut = _boundary(data)
            chunk, self._rest = data[:cut], data[cut:]
        self._ready = self._check(chunk)

    def _check(self, chunk: bytes) -> bytes:
        if self._utf8 or b"\0" not in chunk:
            try:
                chunk.decode()
            except UnicodeDecodeError:
                pass
            else:
                self._utf8 = self._utf8 or not chunk.isascii()
                self._line += chunk.count(b"\n") + chunk.count(b"\r") - chunk.count(b"\r\n")
                return chunk
        lines = []
        for line in chunk.splitlines(keepends=True):
            if not self._utf8 and b"\0" in line:
                raise EncodingError(self._line)
            try:
                line.decode()
            except UnicodeDecodeError:
                if not self._utf8:
                    raise EncodingError(self._line) from None
                self.invalid = self.invalid or self._line
                line = line.decode(errors="replace").encode()
            else:
                self._utf8 = self._utf8 or not line.isascii()
            lines.append(line)
            self._line += line.endswith((b"\n", b"\r"))
        return b"".join(lines)

    def lines(self) -> Iterator[tuple[int, str] | None]:
        """
        The lines of the input with their numbers, without the line ends

        Description:
            None comes before a read that may wait for input: it is time to parse what is read

        Returns:
            Iterator[tuple[int, str] | None]: A number and a line or None
        """
        # The start of an unfinished line in pieces: a long line is joined once
        pending: list[str] = []
        number, start = 0, True
        # A chunk may end in the middle of a character
        decoder = codecs.getincrementaldecoder("utf-8")()
        while True:
            yield None
            chunk = self.read()
            if not chunk:
                break
            data = decoder.decode(chunk)
            if start and data:
                data, start = data.removeprefix("﻿"), False
            pending.append(data)
            if not LINE_END.search(data):
                continue
            text, held = "".join(pending), ""
            # A CR at the end of a chunk may be the start of a CRLF: it waits for the next chunk
            if text.endswith("\r"):
                text, held = text[:-1], "\r"
            *complete, rest = LINE_END.split(text)
            pending = [rest + held] if rest or held else []
            for line in complete:
                number += 1
                yield number, line
        # The rest may hold a held CR followed by the last line without a line end
        *complete, rest = LINE_END.split("".join(pending))
        for line in complete:
            number += 1
            yield number, line
        if rest:
            yield number + 1, rest


def _boundary(data: bytes) -> int:
    """The length of the start of data without an unfinished character of UTF-8 at its end"""
    for back in range(1, min(4, len(data)) + 1):
        byte = data[-back]
        if byte & 0xC0 != 0x80:
            need = 1 if byte < 0xC0 else 2 if byte < 0xE0 else 3 if byte < 0xF0 else 4
            return len(data) - back if need > back else len(data)
    return len(data)


class Output:
    """
    The output of the result: an error of writing is a WriteError, to a terminal - at once

    Arguments:
        file (BinaryIO): A file open for writing in binary mode
        interactive (bool): Flush the buffer after every write
    """

    def __init__(self, file: BinaryIO, interactive: bool) -> None:
        self.file = file
        self._interactive = interactive

    def write(self, text: str) -> None:
        """
        Writing of a text in UTF-8

        Arguments:
            text (str): The text

        Raises:
            WriteError: If writing fails
        """
        try:
            self.file.write(text.encode(errors="replace"))
            if self._interactive:
                self.file.flush()
        except OSError as error:
            raise WriteError(error) from None

    def flush(self) -> None:
        """
        Flushing of the buffer

        Raises:
            WriteError: If writing fails
        """
        try:
            self.file.flush()
        except OSError as error:
            raise WriteError(error) from None


@dataclass
class Block:
    """A sentence of CoNLL-U: the number of its first line and its lines"""

    start: int
    lines: list[str]
    tagged: bool = True

    def check(self) -> InputError | None:
        """
        The parts of speech of the words of the sentence

        Description:
            A sentence without parts of speech is marked for esMorph; a part of speech not at all
            the words and an unknown part of speech are errors

        Returns:
            InputError | None: An error with the number of its line or None
        """
        words = []
        for number, line in enumerate(self.lines, self.start):
            fields = line.split("\t")
            if len(fields) == 10 and fields[0].isdigit():
                words.append((number, fields[3]))
        self.tagged = any(upos != "_" for _, upos in words)
        for number, upos in words:
            if upos == "_" and self.tagged:
                return InputError(
                    number, "the word has no part of speech, while other words of the sentence do"
                )
            if upos != "_" and upos not in UPOS:
                return InputError(
                    number,
                    f"unknown part of speech '{upos}': expected one of the 17 UD parts of "
                    "speech in capitals",
                )
        return None


class Command:
    """
    Parsing of the input of the command and writing of the result

    Arguments:
        parser (Parser): The dependency parser
        output (Output): The output of the result
    """

    def __init__(self, parser: Parser, output: Output) -> None:
        self.parser = parser
        self.output = output
        self.segmenter = anyseg.Segmenter("es")
        self._analyzer: esmorph.Analyzer | None = None
        self._sentences = 0

    @property
    def analyzer(self) -> esmorph.Analyzer:
        """The esMorph morphological analyzer, loaded on first use"""
        if self._analyzer is None:
            self._analyzer = esmorph.Analyzer()
        return self._analyzer

    def text(self, source: Input) -> None:
        """
        Parsing of text by paragraphs

        Description:
            A file starts the comment newdoc, a paragraph newpar; the numbers of the sentences go
            on over all the files, as in the commands anyseg and esmorph

        Arguments:
            source (Input): The input
        """
        stream = self.segmenter.stream(source)
        newdoc = True
        for segmented in stream:
            if not segmented.sentences:
                continue
            # esMorph returns a new document when it splits a token into words
            document = self.analyzer.annotate(segmented)
            self.parser.annotate(document)
            conllu = document.to_conllu().removeprefix("# newdoc\n")
            if stream.continued:
                conllu = conllu.removeprefix("# newpar\n")
            conllu = SENT_ID.sub(self._sent_id, conllu)
            self._sentences += len(document.sentences)
            self.output.write("# newdoc\n" + conllu if newdoc else conllu)
            newdoc = False

    def _sent_id(self, match: re.Match[str]) -> str:
        return f"# sent_id = {int(match[1]) + self._sentences}"

    def conllu(self, source: Input) -> None:
        """
        Parsing of CoNLL-U by sentences

        Description:
            The sentences are parsed in batches: all that is read before a read that may wait for
            input; the result is the input with HEAD and DEPREL filled

        Arguments:
            source (Input): The input

        Raises:
            InputError: If a line of CoNLL-U is wrong; the sentences before it are parsed
        """
        pending: list[Block] = []
        lines: list[str] = []
        start = 0
        for item in source.lines():
            if item is None:
                self._blocks(pending)
                pending.clear()
                continue
            number, line = item
            if line.strip():
                start = start if lines else number
                lines.append(line)
            elif lines:
                pending.append(Block(start, lines))
                lines = []
        if lines:
            pending.append(Block(start, lines))
        self._blocks(pending)

    def _blocks(self, blocks: list[Block]) -> None:
        error = None
        for index, block in enumerate(blocks):
            error = block.check()
            if error is not None:
                # An error in the lines of the same sentence higher in the file comes first
                try:
                    anyseg.read_conllu(_join([block]))
                except ValueError as found:
                    _, earlier = _locate([block], found)
                    error = earlier if earlier.line < error.line else error
                blocks = blocks[:index]
                break
        run: list[Block] = []
        for block in blocks:
            if run and run[0].tagged != block.tagged:
                self._run(run)
                run = []
            run.append(block)
        self._run(run)
        if error is not None:
            raise error

    def _run(self, blocks: list[Block]) -> None:
        if not blocks:
            return
        try:
            documents = anyseg.read_conllu(_join(blocks))
        except ValueError as error:
            index, failure = _locate(blocks, error)
            self._run(blocks[:index])
            raise failure from None
        for document in documents:
            if not blocks[0].tagged:
                document = self.analyzer.annotate(document)
            self.parser.annotate(document)
            self.output.write(document.to_conllu())


def _join(blocks: list[Block]) -> str:
    """The text of CoNLL-U of the sentences: each and a blank line after it"""
    return "".join("\n".join(block.lines) + "\n\n" for block in blocks)


def _locate(blocks: list[Block], error: ValueError) -> tuple[int, InputError]:
    """An error of reading CoNLL-U by anySeg: the number of the sentence and the error with the
    number of its line in the file"""
    match = CONLLU_ERROR.fullmatch(str(error))
    line = int(match[1]) if match else 1
    index, first = 0, 1
    while index + 1 < len(blocks) and first + len(blocks[index].lines) < line:
        first += len(blocks[index].lines) + 1
        index += 1
    message = match[2] if match else str(error)
    # anySeg puts an error of a whole sentence on the blank line after it: the number is its first
    # line
    offset = line - first
    if offset >= len(blocks[index].lines):
        offset = 0
    return index, InputError(blocks[index].start + offset, message)


def run(args: Sequence[str], stdin: _Raw | None, stdout: BinaryIO | None, stderr: TextIO) -> int:
    """
    Run of the essyntax command

    Arguments:
        args (Sequence[str]): The arguments without the name of the program
        stdin (_Raw | None): The standard input in binary mode
        stdout (BinaryIO | None): The standard output in binary mode; None - it is closed
        stderr (TextIO): The stream of error messages

    Returns:
        int: The exit code: 0 - success, 1 - an error of the input, the model or writing, 2 - wrong
            arguments
    """

    def report(message: str) -> None:
        # If the stream of errors is closed too, there is no one to tell
        with contextlib.suppress(OSError, ValueError):
            stderr.write(f"essyntax: {message}\n")
            stderr.flush()

    try:
        options = parse_args(args)
    except UsageError as error:
        report(f"{error}\nHelp: essyntax --help")
        return 2
    if stdout is None:
        if isinstance(options, str) or options.output is None:
            report("the standard output is closed")
            return 1
        # With -o nothing goes to the standard output
        stdout = io.BytesIO()
    if isinstance(options, str):
        versions = f"anyseg {anyseg.__version__}, esmorph {esmorph.__version__}"
        text = HELP if options == "help" else f"essyntax {__version__} ({versions})\n"
        output = Output(stdout, interactive=False)
        try:
            output.write(text)
            output.flush()
        except WriteError as error:
            return _write_error(error, stdout, report)
        return 0
    try:
        parser = Parser(options.model)
    except OSError as error:
        model = options.model
        report(f"{model}: {_describe(error, model)}" if model is not None else str(error))
        return 1
    except ValueError as error:
        # The module writes the absolute path, the command the path as given, as for the input files
        _, marker, detail = str(error).partition(": wrong model format: ")
        if options.model is not None and marker:
            report(f"{options.model}{marker}{detail}")
        else:
            report(str(error))
        return 1
    files = options.files or ["-"]
    opened = _open_output(options, files, stdin, stdout, report)
    if opened is None:
        return 1
    output = Output(opened, interactive=options.output is None and _isatty(opened))
    command = Command(parser, output)
    code = 0
    try:
        for file in files:
            code = max(code, _process(command, file, stdin, options.conllu, report))
        output.flush()
    except WriteError as error:
        code = max(code, _write_error(error, stdout if options.output is None else None, report))
    finally:
        if options.output is not None:
            with contextlib.suppress(OSError):
                output.file.close()
    return code


def _process(
    command: Command, file: str, stdin: _Raw | None, conllu: bool, report: Callable[[str], None]
) -> int:
    """Parsing of one file; the exit code: 0 or 1"""
    try:
        with contextlib.ExitStack() as stack:
            if file == "-":
                raw: _Raw = stdin if stdin is not None else _Empty()
            else:
                raw = stack.enter_context(open(file, "rb", buffering=0))
            source = Input(raw, command.output.flush)
            if conllu:
                command.conllu(source)
            else:
                command.text(source)
    except EncodingError as error:
        report(f"{file}: the file is not in UTF-8 (line {error.line})")
        return 1
    except InputError as error:
        report(f"{file}: line {error.line}: {error.message}")
        return 1
    except OSError as error:
        report(f"{file}: {_describe(error, file)}")
        return 1
    if source.invalid is not None:
        report(
            f"{file}: line {source.invalid}: not UTF-8, the wrong bytes are replaced with U+FFFD"
        )
        return 1
    return 0


class _Empty:
    """An empty input: there is no standard input (pythonw)"""

    def read(self, size: int, /) -> bytes:
        return b""


def _open_output(
    options: Options,
    files: list[str],
    stdin: _Raw | None,
    stdout: BinaryIO,
    report: Callable[[str], None],
) -> BinaryIO | None:
    """The file of the output, the file of -o created anew or the standard output; None - the
    file is not created or the output would overwrite or grow an input or the model"""
    path = options.output
    with contextlib.suppress(OSError, AttributeError, ValueError):
        target = os.fstat(stdout.fileno()) if path is None else os.stat(path)
        if stat.S_ISREG(target.st_mode):
            sources: list[os.stat_result] = []
            for file in files:
                with contextlib.suppress(OSError, AttributeError, ValueError):
                    if file == "-":
                        sources.append(os.fstat(stdin.fileno()))  # type: ignore[union-attr]
                    else:
                        sources.append(_opened_stat(file))
            if options.model is not None:
                with contextlib.suppress(OSError):
                    sources.append(os.stat(options.model))
            if any(os.path.samestat(target, source) for source in sources):
                report(
                    "the standard output is an input file or the model file"
                    if path is None
                    else f"{path}: the output file is an input file or the model file"
                )
                return None
    if path is None:
        return stdout
    try:
        return open(path, "wb")
    except OSError as error:
        report(f"{path}: {_describe(error, path)}")
        return None


def _opened_stat(path: str) -> os.stat_result:
    """The metadata of an input file by the open descriptor: a pipe and a socket are not opened"""
    # On macOS stat("/dev/stdin") is a file of devfs, not the file redirected into it
    info = os.stat(path)
    if stat.S_ISFIFO(info.st_mode) or stat.S_ISSOCK(info.st_mode):
        return info
    try:
        with open(path, "rb", buffering=0) as file:
            return os.fstat(file.fileno())
    except OSError:
        return info


def _describe(error: OSError, path: str) -> str:
    """An error of input and output in plain words for the frequent cases"""
    if isinstance(error, IsADirectoryError) or (
        isinstance(error, PermissionError) and os.path.isdir(path)
    ):
        return "is a directory"
    if isinstance(error, FileNotFoundError):
        return "no such file"
    if isinstance(error, PermissionError):
        return "permission denied"
    return error.strerror or str(error)


def _isatty(file: BinaryIO) -> bool:
    try:
        return file.isatty()
    except (OSError, ValueError):
        return False


def _write_error(error: WriteError, stdout: BinaryIO | None, report: Callable[[str], None]) -> int:
    """The exit code after an error of writing: a closed pipe (essyntax ... | head) is not an error"""
    closed = isinstance(error.error, BrokenPipeError) or (
        sys.platform == "win32" and error.error.errno == errno.EINVAL
    )
    if not closed:
        report(f"write error: {error.error}")
        return 1
    # The rest of the buffer goes nowhere, not to the closed pipe at the exit of Python
    if stdout is not None:
        with contextlib.suppress(OSError, ValueError, AttributeError):
            null = os.open(os.devnull, os.O_WRONLY)
            os.dup2(null, stdout.fileno())
            os.close(null)
    return 0


def main() -> NoReturn:
    """
    Entry point of the essyntax command

    Description:
        Ctrl+C ends the command at once, as any program, and an ignored SIGINT (a command in the
        background of a script) stays ignored; the handler of Python comes back after the command

    Raises:
        SystemExit: Always, with the exit code of the command
    """
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.flush()
    handler = None
    main_thread = threading.current_thread() is threading.main_thread()
    if main_thread and signal.getsignal(signal.SIGINT) is signal.default_int_handler:
        handler = signal.signal(signal.SIGINT, signal.SIG_DFL)
    # Without a console (pythonw) or with a closed descriptor the standard streams are None
    stdin = getattr(sys.stdin, "buffer", None)
    stdout = getattr(sys.stdout, "buffer", None)
    stderr: TextIO = sys.stderr or io.StringIO()
    # Messages to a file or a pipe are in UTF-8, as the result and as in the commands anyseg and
    # esmorph (on Windows Python before 3.15 writes them in the ANSI code page); the console of
    # Python writes Unicode anyway
    utf8 = None
    error_buffer = getattr(sys.stderr, "buffer", None)
    if (
        error_buffer is not None
        and not getattr(error_buffer, "closed", True)
        and not _isatty(error_buffer)
    ):
        # The line ends are LF, as in the commands in Rust, on Windows too
        stderr = utf8 = io.TextIOWrapper(
            error_buffer,
            encoding="utf-8",
            errors="backslashreplace",
            newline="\n",
            write_through=True,
        )
    try:
        code = run(sys.argv[1:], getattr(stdin, "raw", stdin), stdout, stderr)
    finally:
        if utf8 is not None:
            # The wrapper does not close the stream of errors of Python
            with contextlib.suppress(ValueError):
                utf8.detach()
        if handler is not None:
            signal.signal(signal.SIGINT, handler)
    sys.exit(code)


if __name__ == "__main__":
    main()
