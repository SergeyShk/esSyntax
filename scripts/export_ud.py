"""
Training and development parts of the Universal Dependencies treebanks for the esSyntax model

Description:
    Downloads the training and development parts of UD_Spanish-AnCora (CC BY 4.0) and
    UD_Spanish-GSD (CC BY-SA 4.0) of a pinned UD release and checks their SHA-256: the model is
    trained on both, AnCora dev chooses the training point, and GSD dev is a control. Downloaded
    files with the right checksum are not downloaded again; the description of the sources is
    written next to them (sources.json)

Example:
    uv run python scripts/export_ud.py target/ud
"""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

RELEASE = "r2.19"
LICENSES = {"UD_Spanish-AnCora": "CC BY 4.0", "UD_Spanish-GSD": "CC BY-SA 4.0"}
# Treebank, commit of the release and files with SHA-256
SOURCES = {
    "UD_Spanish-AnCora": (
        "bdb41b5f95db8e0a64217fcb8d15cd3ad38c34db",
        {
            "es_ancora-ud-train.conllu": "acb96e0b3d28d8ae0288e0fb0a2d5243bd352c86bcecc0773deef5f40e612f83",
            "es_ancora-ud-dev.conllu": "83033c89b18594a8c7d1571a0f259721714fd989974ca51bd9776bc69faba40c",
        },
    ),
    "UD_Spanish-GSD": (
        "c262f3ca7897ea3b7719731d5958948614e3a214",
        {
            "es_gsd-ud-train.conllu": "f8e0c5ba75d33f78ab7299355924ea9923067a4554a5eff4e04b71064b1835fd",
            "es_gsd-ud-dev.conllu": "5c701ddde2de7ac10032665dcfb8ea39316584ec032ac46ed44a4a567afec82f",
        },
    ),
}


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
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, path: Path, digest: str) -> None:
    """
    Download of a file with its SHA-256 checked; a file with the right checksum is not downloaded again

    Arguments:
        url (str): Address
        path (Path): Where to write
        digest (str): Expected SHA-256

    Raises:
        SystemExit: If the checksum of the downloaded file does not match
    """
    if path.exists() and sha256(path) == digest:
        return
    partial = path.with_suffix(path.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as file:
        while chunk := response.read(1 << 20):
            file.write(chunk)
    if sha256(partial) != digest:
        partial.unlink()
        raise SystemExit(f"SHA-256 does not match: {url}")
    partial.replace(path)


def export(output: Path) -> None:
    """
    Download of the parts of the treebanks and the description of the sources into a directory

    Arguments:
        output (Path): Directory of the export
    """
    output.mkdir(parents=True, exist_ok=True)
    for treebank, (commit, files) in SOURCES.items():
        for name, digest in files.items():
            url = f"https://raw.githubusercontent.com/UniversalDependencies/{treebank}/{commit}/{name}"
            download(url, output / name, digest)
    sources = {
        "release": RELEASE,
        "licenses": LICENSES,
        "treebanks": {treebank: commit for treebank, (commit, _) in SOURCES.items()},
        "files": {name: digest for _, files in SOURCES.values() for name, digest in files.items()},
    }
    (output / "sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("output", type=Path, help="directory of the export")
    export(parser.parse_args().output)


if __name__ == "__main__":
    main()
