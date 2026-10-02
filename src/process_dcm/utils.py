"""utils module."""

import contextlib
import csv
import filecmp
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

import cv2
import numpy as np
import typer
from PIL import Image
from pydicom.dataset import FileDataset
from pydicom.filereader import dcmread
from pydicom.fileset import FileSet
from rich.progress import track

from process_dcm import __version__
from process_dcm.const import RESERVED_CSV, ImageModality

# process-dcm keeps its own per-dataset state in plain snake_case attributes on the pydicom Dataset, which pydicom
# stores without VR validation. Never use real DICOM elements (Modality, AccessionNumber, ReferencedFileID, ...)
# for it: pydicom 3 warns on every non-conformant value and the file's own values would be clobbered.
#   pdcm_modality: ImageModality resolved by update_modality()
#   pdcm_group:    image group counter used in output file names and metadata "group" / "source_id"
#   pdcm_source:   path of the source DICOM file, written to metadata "source_file"

dict_eye = {"R": "OD", "L": "OS"}


def _check_metadata_exists(output_dir: Path) -> bool:
    """Check if metadata.json exists in the output directory."""
    meta_path = output_dir / "metadata.json"
    return meta_path.exists()


_UTC_OFFSET = re.compile(r"[+-]\d{4}$")  # a DICOM DT value may end with a UTC offset, e.g. 20260312123456.789+0000


def strip_utc_offset(date_str: str) -> str:
    """Remove a trailing DICOM UTC offset (``+HHMM`` / ``-HHMM``) so the value matches the naive strptime formats."""
    return _UTC_OFFSET.sub("", date_str)


def do_date(date_str: str, input_format: str, output_format: str) -> str:
    """Convert DCM datetime strings to metadata.json string format."""
    date_str = strip_utc_offset(date_str)
    if "." not in date_str:
        input_format = input_format.split(".")[0]
    try:
        dt = datetime.strptime(date_str, input_format)
        return dt.strftime(output_format)
    except Exception:
        return ""


def set_output_dir(ref_path: str | Path, a_path: str | Path) -> str:
    """Determines the appropriate output directory for a given path.

    This function handles absolute and relative paths, resolving symlinks
    if present. If a path is a broken symlink or a relative path,
    it is combined with a reference path to create the output directory.

    Args:
        ref_path: A reference path used when the given path is relative or broken.
        a_path: The path to be analysed and potentially resolved.

    Returns:
        The determined output directory as a POSIX string (using forward slashes).
        - If `a_path` is absolute and valid, it is returned after symlink resolution.
        - If `a_path` is a broken symlink, it returns the combination of `ref_path` and "exported_data".
        - If `a_path` is relative, it returns the combination of `ref_path` and the resolved relative path.
    """
    path_obj = Path(a_path)

    if path_obj.is_absolute():
        try:
            # Resolve symlinks and return real path
            return path_obj.resolve(strict=False).as_posix()
        except FileNotFoundError:
            return os.path.join(ref_path, "exported_data")  # Handle broken symlink
    else:
        return os.path.join(ref_path, path_obj.as_posix())


def meta_images(dcm_obj: FileDataset) -> dict:
    """Takes a DICOM file dataset and extracts metadata from it to create a dictionary of image metadata.

    Args:
        dcm_obj (FileDataset): The input DICOM file dataset object.

    Returns:
        dict: A dictionary containing the extracted metadata from the input DICOM file dataset.
    """
    meta: dict = defaultdict(dict)
    mod: ImageModality = dcm_obj.pdcm_modality  # set by update_modality()
    group = getattr(dcm_obj, "pdcm_group", 0)
    meta["modality"] = mod.value
    meta["group"] = group
    meta["size"]["width"] = dcm_obj.get("Columns", 0)
    meta["size"]["height"] = dcm_obj.get("Rows", 0)
    meta["field_of_view"] = dcm_obj.get("HorizontalFieldOfView")
    # DICOM instance identity, so downstream tools can associate records with the original objects (parser >= 1.6.0)
    sop_instance_uid = dcm_obj.get("SOPInstanceUID")
    sop_class_uid = dcm_obj.get("SOPClassUID")
    meta["sop_instance_uid"] = str(sop_instance_uid) if sop_instance_uid is not None else None
    meta["sop_class_uid"] = str(sop_class_uid) if sop_class_uid is not None else None
    meta["source_id"] = f"{mod.code}-{group}"

    # Add relative path to source DICOM file if available
    source = getattr(dcm_obj, "pdcm_source", None)
    meta["source_file"] = os.path.relpath(str(source), os.getcwd()) if source is not None else None

    if mod.is_2d_image:
        meta["dimensions_mm"]["width"] = dcm_obj.get("Columns", 0) * dcm_obj.get("PixelSpacing", [0, 0])[1]
        meta["dimensions_mm"]["height"] = dcm_obj.get("Rows", 0) * dcm_obj.get("PixelSpacing", [0, 0])[0]
        meta["resolutions_mm"]["width"] = dcm_obj.get("PixelSpacing", [0, 0])[1]
        meta["resolutions_mm"]["height"] = dcm_obj.get("PixelSpacing", [0, 0])[0]
        meta["contents"] = [{}]  # pyright: ignore[reportArgumentType]
    elif mod.code == "OCT":
        ss = dcm_obj.get("SharedFunctionalGroupsSequence")
        if "OPTOPOL" in dcm_obj.Manufacturer.upper():
            ss = dcm_obj.get("PerFrameFunctionalGroupsSequence")
        if ss:
            try:
                meta["dimensions_mm"]["width"] = (
                    dcm_obj.get("Columns", 0) * ss[0].PixelMeasuresSequence[0].PixelSpacing[1]
                )
                meta["dimensions_mm"]["height"] = (
                    dcm_obj.get("Rows", 0) * ss[0].PixelMeasuresSequence[0].PixelSpacing[0]
                )
                meta["dimensions_mm"]["depth"] = (dcm_obj.get("NumberOfFrames", 1) - 1) * ss[0].PixelMeasuresSequence[
                    0
                ].get("SliceThickness", 0)
                meta["resolutions_mm"]["width"] = ss[0].PixelMeasuresSequence[0].PixelSpacing[1]
                meta["resolutions_mm"]["height"] = ss[0].PixelMeasuresSequence[0].PixelSpacing[0]
                meta["resolutions_mm"]["depth"] = ss[0].PixelMeasuresSequence[0].get("SliceThickness", 0)
            except AttributeError:
                pass
        meta["contents"] = []  # pyright: ignore[reportArgumentType]
        pp = dcm_obj.get("PerFrameFunctionalGroupsSequence")
        if pp:
            for ii in pp:
                # y0, x0, y1, x1
                # [640.0, 128.0, 640.0, 640.0]
                oo = ii.get("OphthalmicFrameLocationSequence")
                if oo:
                    cc = ii.OphthalmicFrameLocationSequence[0].ReferenceCoordinates
                    if len(cc) == 4:
                        # line scan: start and end point
                        locations = [{"start": {"x": cc[1], "y": cc[0]}, "end": {"x": cc[3], "y": cc[2]}}]
                    else:
                        # circular scan: up to four reference points, one entry each (parser >= 1.6.0)
                        locations = [{"start": {"x": cc[i + 1], "y": cc[i]}} for i in range(0, min(len(cc), 8), 2)]
                    meta["contents"].append({"photo_locations": locations})
                else:
                    typer.secho("\nWARN: empty photo_locations", fg=typer.colors.RED)
                    meta["contents"].append({"photo_locations": []})

    return meta


def process_dcm_meta(dcm_objs: list[FileDataset], output_dir: Path, mapping: str = "", keep: str = "") -> None:
    """Extract and save metadata from a list of DICOM files into a JSON file.

    Args:
        dcm_objs (list[FileDataset]): A list of FileDataset objects representing the DICOM files.
        output_dir (Path): The directory where the metadata JSON file will be saved.
        mapping (str, optional): Path to the CSV file containing patient ID to study ID mapping.
                                 If not provided and patient_id is anonymized,
                                 a '{RESERVED_CSV}' file will be generated.
        keep (str, optional): String containing the letters indicating which fields to keep.
                              Options: 'p' for patient key, 'n' for patient names, 'd' for precise date of birth,
                              'D' for anonymized date of birth (year only), and 'g' for gender. Defaults to "".
    """
    meta_file = output_dir / "metadata.json"
    metadata: dict = defaultdict(dict)
    metadata["patient"] = {}
    metadata["exam"] = {}
    metadata["series"] = {}
    metadata["images"]["images"] = []
    metadata["parser_version"] = [1, 6, 0]  # pyright: ignore[reportArgumentType]
    metadata["py_dcm_version"] = [int(x) for x in __version__.split(".") if x.isdigit()]  # pyright: ignore[reportArgumentType]

    keep_gender = "g" in keep
    keep_names = "n" in keep
    anon_pat_key = "p" not in keep
    study_2_patient = {}
    if anon_pat_key and mapping:
        study_2_patient = dict(read_csv(mapping))
        anon_pat_key = False

    for dcm_obj in dcm_objs:
        patient_key = dcm_obj.get("PatientID", "")
        if patient_key in study_2_patient:
            patient_key = study_2_patient[patient_key]
        elif anon_pat_key:
            patient_key = get_hash(patient_key)

        first_name = dcm_obj.get("PatientName.name_prefix")
        last_name = dcm_obj.get("PatientName.name_suffix")
        if not keep_names:
            first_name = None if first_name else first_name
            last_name = None if last_name else last_name

        date_of_birth = do_date(dcm_obj.get("PatientBirthDate", "10010101"), "%Y%m%d", "%Y-%m-%d")
        if "D" in keep:
            year = date_of_birth[:4]
            date_of_birth = f"{year}-01-01"
        elif "d" not in keep:
            date_of_birth = "1001-01-01"

        gender = dcm_obj.get("PatientSex")
        if not keep_gender:
            gender = None if gender else gender

        metadata["patient"]["patient_key"] = patient_key
        metadata["patient"]["first_name"] = first_name
        metadata["patient"]["last_name"] = last_name
        metadata["patient"]["date_of_birth"] = date_of_birth
        metadata["patient"]["gender"] = gender
        metadata["patient"]["source_id"] = dcm_obj.get("FrameOfReferenceUID")

        metadata["exam"]["manufacturer"] = dcm_obj.get("Manufacturer")
        metadata["exam"]["scan_datetime"] = do_date(
            dcm_obj.get("AcquisitionDateTime", "00000000"), "%Y%m%d%H%M%S.%f", "%Y-%m-%d %H:%M:%S"
        )
        metadata["exam"]["scanner_model"] = dcm_obj.get("ManufacturerModelName")
        metadata["exam"]["scanner_serial_number"] = dcm_obj.get("DeviceSerialNumber")
        metadata["exam"]["scanner_software_version"] = str(dcm_obj.get("SoftwareVersions"))
        metadata["exam"]["scanner_last_calibration_date"] = ""
        metadata["exam"]["source_id"] = dcm_obj.get("FrameOfReferenceUID")

        metadata["series"]["laterality"] = dcm_obj.get("ImageLaterality", dcm_obj.get("Laterality"))
        metadata["series"]["fixation"] = ""
        aa = dcm_obj.get("AnatomicRegionSequence")
        if aa:
            metadata["series"]["fixation"] = dcm_obj.get("AnatomicRegionSequence")[0].get("CodeMeaning")
        metadata["series"]["anterior"] = ""  # bool
        metadata["series"]["protocol"] = dcm_obj.get("SeriesDescription")  # Guessing, "Rectangular volume"
        metadata["series"]["source_id"] = dcm_obj.get("FrameOfReferenceUID")
        metadata["images"]["images"].append(meta_images(dcm_obj))
    if len(dcm_objs) > 1:
        metadata["series"]["protocol"] = "OCT ART Volume"

    with open(meta_file, "w") as f:
        json.dump(metadata, f, indent=4)


process_dcm_meta.__doc__ = (
    process_dcm_meta.__doc__.format(RESERVED_CSV=RESERVED_CSV) if process_dcm_meta.__doc__ else None
)


# OPT objects that are rendered reports rather than B-scan acquisitions; they are skipped, not exported as OCT
_OPT_REPORT_DESCRIPTIONS = frozenset({"Angiography Report Analysis"})


def _modality_from_hints(series: str, image_type: list[str]) -> ImageModality | None:
    """Last-resort lookup of a modality code spelled out in SeriesDescription (space-delimited) or in ImageType.

    Args:
        series: The SeriesDescription value, or an empty string.
        image_type: The ImageType values as plain strings.

    Returns:
        The first matching modality in declaration order, or None when nothing matches.
    """
    for modality in ImageModality:
        if modality is ImageModality.UNKNOWN:
            continue
        if f" {modality.code} " in series or modality.code in image_type:
            return modality
    if "FAG" in image_type:  # German "Fluoreszenzangiographie" (Zeiss)
        return ImageModality.FLUORESCEIN_ANGIOGRAPHY
    return None


def _optos_modality(dcm: FileDataset, series: str, image_type: list[str]) -> ImageModality:
    """Classify an Optos OP image from SeriesDescription, ImageType, contrast agent and field of view."""
    series_upper = series.upper()
    has_fluorescein = any("Fluorescein" in str(item) for item in dcm.get("ContrastBolusAgentSequence", []))
    if ("FA " in series and has_fluorescein) or "FA" in image_type:
        return ImageModality.OPTOS_FA
    if "RG OPTOMAP" in series_upper or "OPTOMAPPLUS RG" in image_type:
        return ImageModality.PSEUDOCOLOUR_ULTRAWIDEFIELD
    if "OPTOMAPPLUS ICG" in image_type:
        return ImageModality.OPTOS_ICGA
    if "OPTOMAPPLUS AF" in image_type:
        return ImageModality.OPTOS_AF_IR if "RED" in image_type else ImageModality.UNKNOWN_ULTRAWIDEFIELD
    if dcm.get("HorizontalFieldOfView", 0) == 200:
        return ImageModality.PSEUDOCOLOUR_ULTRAWIDEFIELD  # no cov AWSS
    if "OPTOMAP" in series_upper:
        return ImageModality.UNKNOWN_ULTRAWIDEFIELD
    return ImageModality.UNKNOWN


def _zeiss_modality(image_type: list[str]) -> ImageModality:
    """Classify a Zeiss OP image from its ImageType values."""
    if "COLOR" in image_type:
        return ImageModality.COLOUR_PHOTO
    if "FAFGREEN" in image_type:
        return ImageModality.AUTOFLUORESCENCE_GREEN
    if "FAFBLUE" in image_type:
        return ImageModality.AUTOFLUORESCENCE_BLUE
    if "FA" in image_type:
        return ImageModality.FLUORESCEIN_ANGIOGRAPHY
    if "IR" in image_type:
        return ImageModality.SLO_INFRARED
    return ImageModality.UNKNOWN


def update_modality(dcm: FileDataset) -> bool:
    """Resolves the image modality of a DICOM object from Modality, Manufacturer, SeriesDescription and ImageType.

    The result is stored in the plain attribute ``dcm.pdcm_modality`` (an :class:`ImageModality`); the DICOM
    ``Modality`` element itself is left untouched. OP/OPT images that cannot be classified resolve to
    :attr:`ImageModality.UNKNOWN` and are still exported; other modalities are accepted only when a modality code
    is spelled out in SeriesDescription or ImageType.

    Args:
        dcm (pydicom.dataset.FileDataset): The DICOM object to update.

    Returns:
        bool: True if modality is resolved; False if the object is unsupported and must be skipped.
    """
    modality = dcm.get("Modality")
    if modality is None:
        return False  # No modality, continue # no cov

    series = str(dcm.get("SeriesDescription", ""))
    image_type = [str(value) for value in dcm.get("ImageType", [])]
    manufacturer = str(dcm.get("Manufacturer", "")).upper()
    model = str(dcm.get("ManufacturerModelName", "")).upper()

    resolved = ImageModality.UNKNOWN
    if modality == "OPT":
        if series in _OPT_REPORT_DESCRIPTIONS:
            return False  # rendered report, not a scan
        resolved = ImageModality.OCT
    elif modality == "OP":
        if manufacturer == "TOPCON" or model == "TRITON":
            resolved = ImageModality.INFRARED_PHOTO if " IR" in series else ImageModality.COLOUR_PHOTO
        elif manufacturer == "OPTOS":
            resolved = _optos_modality(dcm, series, image_type)
        elif "ZEISS" in manufacturer:
            resolved = _zeiss_modality(image_type)
        elif " IR" in series or series == "IR":
            resolved = ImageModality.SLO_INFRARED
        elif " BAF " in series:
            resolved = ImageModality.AUTOFLUORESCENCE_BLUE
        elif " ICGA " in series:
            resolved = ImageModality.INDOCYANINE_GREEN_ANGIOGRAPHY
        elif " FA&ICGA " in series:
            resolved = ImageModality.FA_ICGA
        elif " FA " in series:
            resolved = ImageModality.FLUORESCEIN_ANGIOGRAPHY
        elif " RF " in series:
            resolved = ImageModality.RED_FREE
        elif " BR " in series:
            resolved = ImageModality.REFLECTANCE_BLUE
        elif " MColor " in series:
            resolved = ImageModality.REFLECTANCE_MCOLOR
    else:
        # e.g. secondary-capture or converted objects: accepted only when the hints name a modality
        hinted = _modality_from_hints(series, image_type)
        if hinted is None:
            return False  # Unsupported modality, continue
        resolved = hinted

    if resolved is ImageModality.UNKNOWN:
        resolved = _modality_from_hints(series, image_type) or ImageModality.UNKNOWN
    dcm.pdcm_modality = resolved
    return True  # Modality resolved successfully


def group_dcms_by_acquisition_time(dcms: list[FileDataset], tol: float = 2) -> dict[str, list[FileDataset]]:
    """Group DICOM files by AcquisitionDateTime within the specified tolerance.

    Args:
        dcms: List of DICOM FileDataset objects.
        tol: Time tolerance for grouping in seconds.

    Returns:
        Dictionary of grouped DICOM files, keyed by acquisition datetime string.
    """
    grouped_dcms: dict[str, list[FileDataset]] = defaultdict(list)

    def parse_datetime(dt_str: str) -> datetime:
        dt_str = strip_utc_offset(dt_str)
        try:
            return datetime.strptime(dt_str, "%Y%m%d%H%M%S.%f")
        except ValueError:
            return datetime.strptime(dt_str, "%Y%m%d%H%M%S")

    for dcm in dcms:
        acquisition_datetime_str = dcm.get("AcquisitionDateTime", "unknown")
        if acquisition_datetime_str != "unknown":
            try:
                acquisition_datetime = parse_datetime(acquisition_datetime_str)
                # Find the closest group within the tolerance
                for group_time_str in grouped_dcms:
                    if group_time_str != "unknown":
                        group_time = parse_datetime(group_time_str)
                        if abs(acquisition_datetime - group_time) <= timedelta(seconds=tol):
                            grouped_dcms[group_time_str].append(dcm)
                            break
                else:
                    # If no close group found, create a new one
                    grouped_dcms[acquisition_datetime_str].append(dcm)
            except ValueError:
                typer.secho(
                    f"\nWARN: Unexpected AcquisitionDateTime format: {acquisition_datetime_str}", fg=typer.colors.RED
                )
                grouped_dcms["unknown"].append(dcm)
        else:
            grouped_dcms["unknown"].append(dcm)

    return grouped_dcms


def process_dcm_images(
    dcm_objs: list[FileDataset],
    output_dir: Path,
    image_format: str,
    mapping: str,
    keep: str,
    overwrite: bool = False,
    quiet: bool = False,
    time_group: bool = False,
) -> str:
    """Processes DICOM images and saves them to a directory."""
    d0 = dcm_objs[0]
    date_tag = do_date(d0.get("AcquisitionDateTime", "00000000"), "%Y%m%d%H%M%S.%f", "%Y%m%d_%H%M%S")
    if not time_group:
        ref = hex_hash(d0.get("FrameOfReferenceUID", "0"))
        date_tag = f"{do_date(d0.get('AcquisitionDateTime', '00000000'), '%Y%m%d%H%M%S.%f', '%Y%m%d_%H%M%S')}_{ref}"
    lat = dict_eye.get(d0.get("ImageLaterality", d0.get("Laterality")), "OU")
    target_dir = output_dir / f"{d0.PatientID}_{date_tag}_{lat}_{d0.pdcm_modality.code}.DCM"

    if overwrite:
        shutil.rmtree(target_dir, ignore_errors=True)
    else:
        if target_dir.exists():
            # Check if output_dir contains metadata.json and files with the specified image_format
            has_metadata = _check_metadata_exists(target_dir)
            has_images = any(f.endswith(image_format) for f in os.listdir(target_dir))

            if has_metadata and has_images:
                if not quiet:
                    typer.secho(
                        f"\nOutput directory '{target_dir}' already exists with metadata and images. Skipping...",
                        fg="yellow",
                    )
                return "skipped"

    os.makedirs(target_dir, exist_ok=True)

    for dcmO in dcm_objs:
        arr = dcmO.pixel_array

        if dcmO.NumberOfFrames == 1:
            arr = np.expand_dims(arr, axis=0)

        for i in range(dcmO.NumberOfFrames):
            out_img = os.path.join(target_dir, f"{dcmO.pdcm_modality.code}-{dcmO.pdcm_group}_{i}.{image_format}")
            while os.path.exists(out_img):
                dcmO.pdcm_group += 1  # increase group_id
                out_img = os.path.join(target_dir, f"{dcmO.pdcm_modality.code}-{dcmO.pdcm_group}_{i}.{image_format}")

            array = cv2.normalize(arr[i], None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)  # type: ignore #AWSS

            # Adjust array shape if necessary
            if array.ndim == 3:  # Check if the array has a channel dimension
                if array.shape[0] == 1:  # Single channel image
                    array = array[0]  # Remove the channel dimension
                elif array.shape[0] == 3:  # RGB image
                    array = array.transpose(1, 2, 0)  # Change to (height, width, channels)

            image = Image.fromarray(array)
            image.save(out_img)
    process_dcm_meta(dcm_objs=dcm_objs, output_dir=target_dir, mapping=mapping, keep=keep)
    return "processed"


def group_dcms_by_frame_reference(dcms: list[FileDataset]) -> dict[str, list[FileDataset]]:
    """Group DICOM files by FrameOfReferenceUID.

    Args:
        dcms: List of DICOM FileDataset objects.

    Returns:
        Dictionary of grouped DICOM files, keyed by FrameOfReferenceUID.
    """
    grouped_dcms: dict[str, list[FileDataset]] = defaultdict(list)

    for dcm in dcms:
        frame_ref_uid = dcm.get("FrameOfReferenceUID", "unknown")
        grouped_dcms[frame_ref_uid].append(dcm)

    return grouped_dcms


def process_dcm(
    input_path: Path,
    image_format: str = "png",
    output_dir: Path = Path("exported_data"),
    mapping: str = "",
    keep: str = "",
    overwrite: bool = False,
    quiet: bool = False,
    time_group: bool = False,
    tol: float = 2,
    n_jobs: int = 1,
) -> tuple[int, int, list[tuple[str, str]]]:
    """Process DICOM files from the input directory and save images in a specified format.

    Args:
        input_path (Path): The path to a DCM file or a folder containing DICOM files to be processed.
        image_format (str, optional): The format for saving processed images. Defaults to 'png'.
        output_dir (Path, optional): The directory path where images will be saved after processing.
                                     Defaults to 'exported_data'.
        mapping (str, optional): CSV file path for patient ID to study ID mapping.
                                 If not provided and patient_id is anonymized,
                                 a '{RESERVED_CSV}' file will be generated.
        keep (str, optional): A string specifying which fields to retain.
                              Options include: 'p' for patient key,
                              'n' for patient names,
                              'd' for precise date of birth,
                              'D' for anonymized date of birth (keeping year only),
                              and 'g' for gender. Defaults to ''.
        overwrite (bool, optional): Flag to determine whether to overwrite existing files in the output directory.
                                    Defaults to False.
        quiet (bool, optional): Flag to control verbosity of the process. Defaults to False.
        time_group (bool, optional): Determines if DICOM files should be re-grouped by AcquisitionDateTime.
                                     Defaults to False.
        tol (float, optional): Time tolerance in seconds for grouping DICOM files by AcquisitionDateTime. Defaults to 2.
        n_jobs (int, optional): The number of parallel jobs to utilize for processing. Defaults to 1.

    Returns:
        tuple[int, int, list[tuple[str, str]]]: A tuple containing the number of processed files, the number of errors,
                                         and a list of tuples with new patient key and the original patient key.
    """
    pairs: list[tuple[str, str]] = []  # store (new, old) pat_id if updated
    processed = 0
    skipped = 0

    dcm_objs0: list
    dicomdir_path = os.path.join(input_path, "DICOMDIR")
    tmp_dcm_objs = []
    if os.path.exists(dicomdir_path):
        if not quiet:
            typer.secho(f"Found DICOMDIR file at {dicomdir_path}", fg=typer.colors.BRIGHT_YELLOW)
        ds = dcmread(dicomdir_path)
        dicomdir_fs = FileSet(ds)
        dicomdir_fs.remove(dicomdir_fs.find(Modality="OT"))
        for dcmf in dicomdir_fs.find():
            dcm = dcmread(dcmf.path)
            dcm.pdcm_source = dcmf.path
            tmp_dcm_objs.append(dcm)
    elif input_path.is_file():
        dcm = dcmread(input_path)
        dcm.pdcm_source = input_path
        tmp_dcm_objs.append(dcm)
    else:
        for file in sorted(input_path.rglob("*")):  # sorted: deterministic image order across filesystems
            if file.is_file() and is_dicom_file(file):
                dcm = dcmread(file)
                dcm.pdcm_source = file
                tmp_dcm_objs.append(dcm)

    dcm_objs0 = [dcm for dcm in tmp_dcm_objs if dcm.get("Modality")]

    if not dcm_objs0:
        return processed, skipped, pairs

    dcm_objs = [x for x in dcm_objs0 if update_modality(x)]

    if time_group:
        grouped_dcms = group_dcms_by_acquisition_time(dcm_objs, tol=tol)
    else:
        grouped_dcms = group_dcms_by_frame_reference(dcm_objs)

    sorted_groups = sorted(grouped_dcms.items())

    def process_group(group_info: tuple) -> tuple[str, tuple[str, str]]:
        _, group = group_info
        patient_id = group[0].get("PatientID", "")
        keep_patient_key = "p" in keep
        new_patient_key = patient_id

        if not keep_patient_key:
            study_2_patient = {}
            new_patient_key = get_hash(patient_id)
            if mapping:
                study_2_patient = dict(read_csv(mapping))
                patient_2_study = {v: k for k, v in study_2_patient.items()}
                new_patient_key = patient_2_study.get(patient_id, new_patient_key)

        dcms = []
        sorted_group = sorted(group, key=lambda dcm: dcm.pdcm_modality.code)
        for dcm in sorted_group:
            if dcm.pdcm_modality == ImageModality.UNKNOWN:
                typer.secho(
                    f"\nWARN: Unknown modality for {dcm.pdcm_source}\n-> {output_dir}",
                    fg=typer.colors.RED,
                )
            dcm.pdcm_group = 0
            if not dcm.get("NumberOfFrames"):
                dcm.NumberOfFrames = 1
            if not keep_patient_key:
                dcm.PatientID = new_patient_key
            dcms.append(dcm)

        res = process_dcm_images(
            dcm_objs=dcms,
            output_dir=output_dir,
            image_format=image_format,
            mapping=mapping,
            keep=keep,
            overwrite=overwrite,
            quiet=quiet,
            time_group=time_group,
        )
        return res, (new_patient_key, patient_id)

    out_empty = not output_dir.exists() or not any(output_dir.iterdir())
    if n_jobs > 1:
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            futures = [executor.submit(process_group, group_info) for group_info in sorted_groups]
            for future in track(
                as_completed(futures), total=len(sorted_groups), description="Processing groups", disable=quiet
            ):
                res, pair = future.result()
                if res == "processed":
                    processed += 1
                elif res == "skipped":
                    skipped += 1
                pairs.append(pair)
    else:
        for group_info in track(sorted_groups, description="Processing groups", disable=quiet):
            res, pair = process_group(group_info)
            if res == "processed":
                processed += 1
            elif res == "skipped":
                skipped += 1
            pairs.append(pair)

    if time_group and out_empty:
        nn = len(sorted_groups)
        if processed != nn:
            typer.secho(
                f"\nWARN: Number of groups ({nn}) differs from processed ({processed})\nConsider increasing '--tol'",
                fg=typer.colors.RED,
            )

    return processed, skipped, pairs


# Ensure that process_dcm_meta docstring includes RESERVED_CSV
process_dcm.__doc__ = process_dcm.__doc__.format(RESERVED_CSV=RESERVED_CSV) if process_dcm.__doc__ else None


def is_dicom_file(filepath: str | Path) -> bool:
    """Check if it's a DICOM file."""
    try:
        dcmread(filepath, stop_before_pixels=True)
        return True
    except Exception:
        return False


def get_md5(file_path: Path | str | list[str] | list[Path], minus: int = 0) -> str:
    """Calculate the MD5 checksum of a file or list of files, optionally suppressing lines from the bottom."""
    md5_hash = hashlib.md5(usedforsecurity=False)  # checksum only, not a security primitive

    def process_file(file: Path | str) -> None:
        with open(file, "rb") as f:
            lines = f.readlines()
            for line in lines[:-minus] if minus > 0 else lines:
                md5_hash.update(line)

    if isinstance(file_path, str | Path):
        process_file(file_path)
    elif isinstance(file_path, list):
        for fname in file_path:
            process_file(fname)

    return md5_hash.hexdigest()


def get_hash(value: str) -> str:
    """Get a 10 digit hash based on the input string."""
    hex_dig = hashlib.sha256(str(value).encode()).hexdigest()
    return f"{int(hex_dig[:8], 16):010}"


def hex_hash(input_string: str, length: int = 6) -> str:
    """Generate a fast, short hexadecimal hash using blake2b.

    Args:
        input_string (str): The input string to hash.
        length (int): Length of the hex hash output (4, 6, etc.).

    Returns:
        str: A short hexadecimal hash.
    """
    # blake2b is optimized for speed, digest_size=4 gives 8 hex characters
    hash_object = hashlib.blake2b(input_string.encode("utf-8"), digest_size=4)
    return hash_object.hexdigest()[:length]


def get_versioned_filename(base_filename: str | Path, version: int) -> str:
    """Generates a file name with a version suffix.

    Args:
        base_filename (str | Path): The base name of the file.
        version (int): The version number to append.

    Returns:
        str: The generated file name with a version suffix.
    """
    base, ext = os.path.splitext(base_filename)
    return f"{base}_{version}{ext}"


def save_to_temp_file(data: list[list[str]]) -> str:
    """Saves data to a temporary CSV file.

    Args:
        data (list[list[str]]): The data to be written to the temporary file.

    Returns:
        str: The path of the temporary file.
    """
    # Close the NamedTemporaryFile first so it can be reused by write_to_csv
    with tempfile.NamedTemporaryFile(delete=False, mode="w", newline="", suffix=".csv") as temp_file:
        temp_name = temp_file.name
    write_to_csv(temp_name, data, header=["study_id", "patient_id"])
    return temp_name


def files_are_identical(file1: str | Path, file2: str | Path) -> bool:
    """Checks if two files are identical.

    Args:
        file1 (str): The path to the first file.
        file2 (str): The path to the second file.

    Returns:
        bool: True if the files are identical, False otherwise.
    """
    return filecmp.cmp(file1, file2, shallow=False)


def process_and_save_csv(unique_sorted_results: list, reserved_csv: str | Path, quiet: bool = False) -> None:
    """Processes unique sorted results and saves them to the reserved CSV file.

    If the content is identical to the existing file, it leaves the existing file unchanged.
    If the content differs, it renames the existing file with a suffix and saves the new content as the reserved CSV.

    Args:
        unique_sorted_results (list): The data to be written to the CSV file. Each sublist
                                      represents a row with 'study_id' and 'patient_id'.
        reserved_csv (str | Path): The path to the reserved CSV file.
        quiet (bool, optional): Silence verbosity. Defaults to False.
    """
    temp_filename = save_to_temp_file(unique_sorted_results)

    if os.path.exists(reserved_csv):
        if files_are_identical(temp_filename, reserved_csv):
            os.remove(temp_filename)
            if not quiet:
                typer.secho(f"No changes detected. '{reserved_csv}' remains unchanged.", fg="yellow")
        else:
            version = 1
            new_version_filename = get_versioned_filename(reserved_csv, version)
            while os.path.exists(new_version_filename):
                version += 1
                new_version_filename = get_versioned_filename(reserved_csv, version)

            shutil.move(reserved_csv, new_version_filename)
            if not quiet:
                typer.secho(f"Old '{reserved_csv}' renamed to '{new_version_filename}'", fg="yellow")
            shutil.move(temp_filename, reserved_csv)
            if not quiet:
                typer.secho(f"New generated mapping saved to '{reserved_csv}'", fg="yellow")
    else:
        shutil.move(temp_filename, reserved_csv)
        if not quiet:
            typer.secho(f"Generated mapping saved to '{reserved_csv}'", fg="blue")


def read_csv(file_path: str | Path) -> list[list[str]]:
    """Reads a CSV file and returns its contents as a list of rows.

    Each row is represented as a list of strings.

    Args:
        file_path (str|Path): The path to the CSV file to be read.

    Returns:
        list[list[str]]: A list of rows, where each row is a list of strings representing the CSV data.
    """
    with open(file_path) as file:
        reader = csv.reader(file)
        return list(reader)


def write_to_csv(file_path: str | Path, data: list[list[str]], header: list[str] | None = None) -> None:
    """Writes data to a CSV file at the specified file path.

    Args:
        file_path (str|Path): The path to the CSV file.
        data (list[list[str]]): The data to write to the CSV file. Each sublist represents a row.
        header (list[str], optional): An optional list representing the CSV header.
                                      Defaults to None.
    """
    file_path = Path(file_path)
    with file_path.open(mode="w", newline="") as file:
        writer = csv.writer(file)
        if header:
            writer.writerow(header)
        writer.writerows(data)


def delete_if_empty(folder_path: str | Path, n_jobs: int = 1) -> bool:
    """Check if a given path is an empty folder (including empty subfolders) and delete it if so.

    This function recursively checks if the specified path and its subfolders are empty.
    If a folder is empty, it is deleted. The function can operate in parallel for faster
    processing of large directory structures.

    Args:
        folder_path (Union[str, Path]): The path to check and possibly delete.
        n_jobs (int): The number of parallel jobs to run. Default is 1 (sequential processing).

    Returns:
        bool: True if the path was an empty folder (or contained only empty subfolders) and was successfully deleted,
              False otherwise.
    """
    path = Path(folder_path).resolve()

    if not path.is_dir():
        return False

    lock = Lock()

    def process_folder(folder: Path) -> bool:
        is_empty = True
        for item in folder.iterdir():
            if item.is_file():
                is_empty = False
                break
            if item.is_dir() and not delete_if_empty(item, n_jobs=1):  # Recursive call, but without parallelism
                is_empty = False
                break

        if is_empty:
            with lock, contextlib.suppress(FileNotFoundError):
                folder.rmdir()

        return is_empty

    if n_jobs > 1:
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            futures = [executor.submit(process_folder, subfolder) for subfolder in path.iterdir() if subfolder.is_dir()]
            results = [future.result() for future in as_completed(futures)]

            # Check if all subfolders were empty and deleted
            with lock:
                if all(results) and not any(path.glob("*")):
                    path.rmdir()
                    return True
    else:
        return process_folder(path)

    return False


def tree(directory: str | Path, indent: str = "", prefix: str = "") -> str:
    """Recursively returns the directory structure similar to the 'tree' command."""
    result = ""
    if not os.path.isdir(directory):
        return f"Error: '{directory}' is not a valid directory."

    entries = sorted(os.listdir(directory))
    for i, entry in enumerate(entries):
        path = os.path.join(directory, entry)
        is_last = i == len(entries) - 1  # Check if it's the last item
        line = indent + prefix + entry + "\n"
        result += line
        if os.path.isdir(path):
            new_indent = indent + ("    " if is_last else "│   ")
            subtree = tree(path, new_indent, "└── " if is_last else "├── ")
            result += subtree

    return result
