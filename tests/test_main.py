import shutil
from glob import glob
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from typer.testing import CliRunner

from process_dcm import __version__
from process_dcm.const import RESERVED_CSV
from process_dcm.main import app
from process_dcm.utils import get_md5
from tests.conftest import bottom, remove_ansi_codes

# ~625 MB of sample DICOMs deliberately kept out of git (see README "Test data")
EXAMPLE_DIR = Path("tests/example_dir")
requires_example_dir = pytest.mark.skipif(not EXAMPLE_DIR.is_dir(), reason="tests/example_dir is not available")


def test_main_defaults(runner: CliRunner) -> None:
    result = runner.invoke(app, ["input_path"])
    output = remove_ansi_codes(result.stdout) + remove_ansi_codes(result.stderr)
    assert result.exit_code == 1
    assert "Input path 'input_path' does not exist\nAborted.\n" in output


# Manual debugging hook, not a test: point the path at a local DICOM export, remove the skip marker temporarily, and
# run it alone under the IDE debugger (or `uv run pytest tests/test_main.py::test_main_debug -n0 --no-cov`).
# It stays skipped in the suite because the path exists only on the developer's machine.
@pytest.mark.skip(reason="for debug")
def test_main_debug(runner: CliRunner) -> None:
    result = runner.invoke(app, ["/Users/alan/Downloads/CE/Alan_Dicom_Exported", "-q", "-k", "pndg"])
    assert result.exit_code == 0
    # assert "Processed" in result.output


def test_main_version(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"Process DCM Version: {__version__}" in result.output


@pytest.mark.parametrize(
    "input_path, image_format, output_dir, additional_args, expected_output",
    [
        ("path/to/dcm", "jpg", "/tmp/exported_data", [], "Aborted"),
    ],
)
def test_main_with_options(
    input_path: str,
    image_format: str,
    output_dir: str,
    additional_args: list[str],
    expected_output: str,
    runner: CliRunner,
) -> None:
    args = [
        input_path,
        "--image_format",
        image_format,
        "--output_dir",
        output_dir,
        "--overwrite",
        *additional_args,
    ]

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert expected_output in result.output


# PNG bytes depend on the Pillow encoder version even though pixels are identical
PNG_MD5S = [
    "5ba37cc43233db423394cf98c81d5fbc",  # GH, Pillow < 12
    "a726b59587ca4ea1a478802e3ee9235c",  # local, Pillow < 12
    "19a3a9b1922447053ca0bce8ba785767",  # Pillow >= 12
]


def test_cli_without_args(runner: CliRunner) -> None:
    result = runner.invoke(app)
    assert result.exit_code == 2
    output = remove_ansi_codes(result.stderr)
    assert "Missing argument" in output  # metavar rendering differs across typer versions


@pytest.mark.parametrize(
    "md5, meta, keep, key",
    [
        (
            PNG_MD5S,
            "928eaea84dcf85d710192981663be425",
            "pndg",
            "bbff7a25-d32c-4192-9330-0bb01d49f746",
        ),
        (
            PNG_MD5S,
            "27eb9a93abfa43a7e6d6828bd14e9644",
            "pnDg",
            "bbff7a25-d32c-4192-9330-0bb01d49f746",
        ),
        (
            PNG_MD5S,
            "72a8d7f0f7f043a6746056ba6e826b25",
            "",
            "0780320450",
        ),
    ],
)
def test_main(md5: list[str], meta: str, keep: str, key: str, janitor: list[str], runner: CliRunner) -> None:
    janitor.append("study_2_patient.csv")
    janitor.append("study_2_patient_1.csv")
    janitor.append("study_2_patient_2.csv")
    # Create a temporary directory using the tempfile module
    with TemporaryDirectory() as tmpdirname:
        output_dir = Path(tmpdirname)
        args = [
            "tests/example-dcms",
            "--output_dir",
            tmpdirname,
            "--overwrite",
            "--keep",
            keep,
        ]
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        tof = sorted(glob(f"{output_dir}/**/*"))
        of = [x for x in tof if "metadata.json" not in x]
        assert len(tof) == 51
        assert (
            get_md5(
                output_dir / f"{key}_20150624_144600_2e3f4b_OD_OCT.DCM" / "metadata.json",
                bottom,
            )
            == meta
        )
        assert get_md5(of) in md5


def test_main_group(janitor: list[str], runner: CliRunner) -> None:
    janitor.append("study_2_patient.csv")
    janitor.append("study_2_patient_1.csv")
    janitor.append("study_2_patient_2.csv")
    with TemporaryDirectory() as tmpdirname:
        output_dir = Path(tmpdirname)
        args = ["tests", "-o", tmpdirname, "-k", "gD", "-g"]
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert "Found DICOMDIR file at tests/DICOMDIR" in result.output
        tof = sorted(output_dir.rglob("*.*"))
        of = sorted(output_dir.rglob("*.png"))
        assert len(tof) == 52
        assert (
            get_md5(output_dir / "0780320450_20150624_144600_OD_OCT.DCM" / "metadata.json", bottom)
            == "103860e71d8cf0e3cef29d5b8fa44739"
        )
        assert get_md5(of) in PNG_MD5S
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert "0780320450_20150624_144600_OD_OCT.DCM' already exists with metadata" in result.output


def test_main_dummy(janitor: list[str], runner: CliRunner) -> None:
    janitor.append("dummy_dir")
    args = ["tests/dummy_ex", "-o", "dummy_dir", "-k", "p"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    tof = sorted(glob("dummy_dir/**/*"))
    of = [x for x in tof if "metadata.json" not in x]
    assert len(tof) == 3
    # one value only: input files are processed in sorted order, so the image order no longer depends on the filesystem
    assert (
        get_md5(Path("dummy_dir") / "123456__340692_OU_U.DCM" / "metadata.json", bottom)
        == "c7ba10772ba3a04c18b1616c7bf3df92"
    )
    assert get_md5(of) in [
        "fb7c7e0fe4e7d3e89e0daae479d013c4",  # local, Pillow < 12
        "77bb205173d3b15f6131b530a29c2ab7",  # GH, Pillow < 12
        "8e1531010084c8681f3e21d27206f086",  # Pillow >= 12
    ]


def test_main_abort(runner: CliRunner) -> None:
    # Expect the typer.Abort exception to be raised
    args = ["tests/example-dcms", "--keep", "p", "--mapping", RESERVED_CSV]
    result = runner.invoke(app, args)

    # Strip ANSI codes from the output
    output = remove_ansi_codes(result.stdout) + remove_ansi_codes(result.stderr)

    assert result.exit_code == 1
    assert output == "'--mapping' x '--keep p': are mutually excluding options\nAborted.\n"


def test_main_abort_reserved_csv(runner: CliRunner) -> None:
    # Expect the typer.Abort exception to be raised
    args = ["tests/example-dcms", "--mapping", RESERVED_CSV]
    result = runner.invoke(app, args)

    # Strip ANSI codes from the output
    output = remove_ansi_codes(result.stdout) + remove_ansi_codes(result.stderr)

    assert result.exit_code == 1
    assert output == f"Can't use reserved CSV file name: {RESERVED_CSV}\nAborted.\n"


def test_main_no_dicom(runner: CliRunner, tmp_path: Path) -> None:
    args = [tmp_path.as_posix()]
    result = runner.invoke(app, args)

    # Strip ANSI codes from the output
    output = remove_ansi_codes(result.stdout)

    assert result.exit_code == 0
    assert output == f"\nNo DICOM files found in {tmp_path}\n"


@requires_example_dir
def test_main_mapping_example_dir(janitor: list[str], runner: CliRunner) -> None:
    janitor.append("study_2_patient.csv")
    janitor.append("study_2_patient_1.csv")
    janitor.append("study_2_patient_2.csv")
    with TemporaryDirectory() as tmpdirname:
        output_dir = Path(tmpdirname)
        args = ["tests/example_dir", "-o", tmpdirname, "-j", "2", "-w", "-k", "nDg", "-m", "tests/map.csv"]
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        of = sorted([p for p in output_dir.rglob("*") if p.is_file()])
        assert len(of) == 264
        assert (
            get_md5(output_dir / "2910892726_20180724_161901_477b53_OS_OCT.DCM" / "metadata.json", bottom)
            == "6b022a883bd309be2779a32d3dc4a994"
        )
        assert (
            get_md5(output_dir / "3517807670_20180926_140517_600177_OD_OCT.DCM" / "metadata.json", bottom)
            == "e921b5336d467eb82107bf4b5e4c6282"
        )
        args = ["tests/example_dir", "-o", str(output_dir), "-j", "2", "-k", "nDg", "-m", "tests/map.csv"]
        # result = runner.invoke(app, args)
        shutil.rmtree(output_dir / "3517807670_20180926_140517_600177_OD_OCT.DCM")
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert "\nProcessed 1 DICOM folders\nSkipped 3 DICOM folders\n" in result.output


def test_main_optos_fa(janitor: list[str], runner: CliRunner) -> None:
    janitor.append("study_2_patient.csv")
    janitor.append("study_2_patient_1.csv")
    janitor.append("study_2_patient_2.csv")
    with TemporaryDirectory() as tmpdirname:
        output_dir = Path(tmpdirname)
        input_path = "tests/optos_fa/"
        args = [input_path, "-o", tmpdirname, "-k", "pndg"]
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        of = sorted(glob(f"{output_dir}/**/*"))
        assert len(of) == 2
        # the folder now carries the acquisition date: this Optos file stores it with a UTC offset (-0400)
        assert (
            get_md5(output_dir / "1840002001_20231013_112320_44fd1d_OD_OPTOS_FA.DCM" / "metadata.json", bottom)
            == "f7d628532ddc8b4e3ff35d0a716fd9b1"
        )


def test_same_time(runner: CliRunner) -> None:
    with TemporaryDirectory() as tmpdirname:
        args = ["tests/same-time", "-gk", "pndg", "-t", "0.0", "-o", tmpdirname]
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert "WARN: Number of groups (2) differs from processed (1)" in result.output
        args = ["tests/same-time", "-rgk", "pndg", "-t", "1", "-o", tmpdirname]
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        args = ["tests/same-time", "-rk", "pndg", "-t", "1", "-o", tmpdirname]
        result = runner.invoke(app, args)
        assert "'--tol' option can only be used when '--group' is set." in result.output


def test_optomap(runner: CliRunner) -> None:
    with TemporaryDirectory() as tmpdirname:
        output_dir = Path(tmpdirname)
        args = ["tests/rg_optomap/example.dcm", "-k", "pndg", "-o", tmpdirname]
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        # the folder now carries the acquisition date: this Optos file stores it with a UTC offset (-0500)
        md5 = get_md5(output_dir / "252-1052_20250102_100023_4eb9d4_OS_PCUWF.DCM/PCUWF-0_0.png")
        assert md5 in [
            "8ef9cf6a4eb98b80129c398368cf1925",  # Pillow < 12
            "6124405b60c88310f072fb31b207805d",  # Pillow < 12
            "c3fa82e02662f5bd24e18768c0440204",  # Pillow >= 12
        ]
        assert (
            get_md5(output_dir / "252-1052_20250102_100023_4eb9d4_OS_PCUWF.DCM/metadata.json", bottom)
            == "3d7ac9c2b41a55e720fad699e7958f01"
        )
