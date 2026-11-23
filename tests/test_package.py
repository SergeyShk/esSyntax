import importlib
import importlib.metadata
import re
import shutil
import subprocess
import sys
import sysconfig
import tomllib
import zipfile
from pathlib import Path

import pytest

import essyntax

ROOT = Path(__file__).parents[1]


def test_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", essyntax.__version__)
    assert essyntax.__version__ != "0.0.0"


def test_metadata():
    assert "dependency parser" in essyntax.__description__
    assert {"Parser", "__version__"} <= set(essyntax.__all__)
    assert essyntax.__all__ == sorted(essyntax.__all__)


def test_version_matches_metadata():
    # The version comes from the extension module, without slow importlib.metadata on import
    assert essyntax.__version__ == importlib.metadata.version("essyntax")


def test_crate_version():
    with (ROOT / "Cargo.toml").open("rb") as file:
        crate = tomllib.load(file)["workspace"]["package"]["version"]
    with (ROOT / "pyproject.toml").open("rb") as file:
        package = tomllib.load(file)["project"]["version"]
    assert crate == re.sub(r"\.dev(\d+)$", r"-dev.\1", package)


def test_model_cache_key():
    # uv rebuilds the module when the model embedded in it changes
    with (ROOT / "pyproject.toml").open("rb") as file:
        keys = tomllib.load(file)["tool"]["uv"]["cache-keys"]
    assert {"file": "data/es-syntax.bin"} in keys


def test_extension():
    extension = importlib.import_module("essyntax._essyntax")
    assert Path(extension.__file__).parent == Path(essyntax.__file__).parent


def test_package_data():
    assert (Path(essyntax.__file__).parent / "py.typed").is_file()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv builds the wheel")
def test_wheel_contents(tmp_path):
    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--python",
            sys.executable,
            "--out-dir",
            str(tmp_path),
            str(ROOT),
        ],
        capture_output=True,
        check=True,
    )
    (wheel,) = tmp_path.glob("*.whl")
    assert ("-abi3-" in wheel.name) != bool(sysconfig.get_config_var("Py_GIL_DISABLED"))
    with zipfile.ZipFile(wheel) as archive:
        sizes = {info.filename: info.file_size for info in archive.infolist()}
    names = set(sizes)
    assert "essyntax/py.typed" in names
    modules = [
        name for name in names if re.fullmatch(r"essyntax/_essyntax(\.[\w-]+)?\.(so|pyd)", name)
    ]
    assert len(modules) == 1
    # The model is embedded in the module, not a file of the package
    assert sizes[modules[0]] > (ROOT / "data" / "es-syntax.bin").stat().st_size
    assert all(name.startswith(("essyntax/", "essyntax-")) for name in names)
    licenses = {name.rsplit("/", 1)[1] for name in names if "/licenses/" in name}
    assert licenses == {"LICENSE.txt", "LICENSE-MODEL.txt", "THIRD-PARTY-NOTICES.txt"}


@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo reads the crates")
def test_third_party_notices(tmp_path):
    # The licenses of the crates of the module follow Cargo.lock: after a change run python scripts/notices.py
    path = tmp_path / "notices.txt"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "notices.py"), str(path)],
        capture_output=True,
        check=True,
    )
    expected = (ROOT / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    assert path.read_text(encoding="utf-8") == expected, "python scripts/notices.py"
