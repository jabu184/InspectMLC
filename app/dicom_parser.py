import os
import re
import pydicom
import numpy as np
from typing import Dict, Any, Tuple

def extract_gantry_and_bank(input_source) -> Dict[str, Any]:
    """
    Robust DICOM metadata parser for Halcyon/Ethos and TrueBeam deliveries:
    Extracts Gantry Angle (e.g. 0, 90, 180, 270) and MLC Leaf Bank ('Proximal', 'Distal', or 'Open').
    Performs regular expression parsing on primary descriptive tags, nested sequences, and filename fallbacks.
    """
    if isinstance(input_source, (str, os.PathLike)):
        if not os.path.exists(input_source):
            raise FileNotFoundError(f"DICOM file not found: {input_source}")
        dcm = pydicom.dcmread(input_source, stop_before_pixels=True)
        fname = os.path.basename(input_source)
    elif isinstance(input_source, pydicom.dataset.FileDataset):
        dcm = input_source
        fname = getattr(dcm, "filename", "dicom_image.dcm")
    else:
        raise ValueError("Invalid DICOM input source.")

    # 1. Primary Descriptive DICOM Text Tags
    tag_sources = [
        str(getattr(dcm, "RTImageLabel", "")),
        str(getattr(dcm, "RTImageDescription", "")),
        str(getattr(dcm, "ImageComments", "")),
        str(getattr(dcm, "SeriesDescription", "")),
        str(getattr(dcm, "RTImageName", "")),
        str(getattr(dcm, "BeamName", ""))
    ]

    # Include Curve Label (5000, 2500) if present
    try:
        if (0x5000, 0x2500) in dcm:
            tag_sources.append(str(dcm[(0x5000, 0x2500)].value))
    except Exception:
        pass

    primary_text = " ".join(tag_sources)

    # 2. Regex Parsing for Gantry Angle & Leaf Bank
    gantry_match = re.search(r'G(\d+)|GANTRY\s*(\d+)|MV_(\d+)|(\d+)\s*DEG', primary_text, re.IGNORECASE)
    bank_match = re.search(r'\b(Proximal|Distal|Open|SX1|SX2)\b', primary_text, re.IGNORECASE)

    raw_label = ""
    if gantry_match or bank_match:
        label_match = re.search(r'([A-Za-z0-9_\-\s]*\(G\d+\s*(?:Distal|Proximal|Open)\))', primary_text, re.IGNORECASE)
        if label_match:
            raw_label = label_match.group(1).strip()
        else:
            raw_label = primary_text.strip()

    # Fallback 1: Nested Sequence / Stringified Dataset Scan
    if not gantry_match or not bank_match:
        full_str = str(dcm)
        if not gantry_match:
            gantry_match = re.search(r'G(\d+)|GANTRY\s*(\d+)|MV_(\d+)|(\d+)\s*DEG', full_str, re.IGNORECASE)
        if not bank_match:
            bank_match = re.search(r'\b(Proximal|Distal|Open|SX1|SX2)\b', full_str, re.IGNORECASE)

    # Fallback 2: Filename Scan
    if not gantry_match:
        gantry_match = re.search(r'G(\d+)|(\d+)\s*DEG', fname, re.IGNORECASE)
    if not bank_match:
        bank_match = re.search(r'\b(Proximal|Distal|Open|SX1|SX2)\b', fname, re.IGNORECASE)

    # Extract Integer Gantry Angle
    gantry_angle = 0
    if gantry_match:
        for grp in gantry_match.groups():
            if grp is not None:
                gantry_angle = int(grp)
                break
    else:
        # Fallback 3: Standard numeric GantryAngle tag (300A, 011E)
        raw_g = float(getattr(dcm, "GantryAngle", 0.0))
        g_mod = raw_g % 360.0
        if g_mod < 45.0 or g_mod >= 315.0:
            gantry_angle = 0
        elif 45.0 <= g_mod < 135.0:
            gantry_angle = 90
        elif 135.0 <= g_mod < 225.0:
            gantry_angle = 180
        else:
            gantry_angle = 270

    # Determine Leaf Bank String
    leaf_bank = "Distal"
    if bank_match:
        b_str = bank_match.group(1).upper()
        if "PROX" in b_str or "SX1" in b_str:
            leaf_bank = "Proximal"
        elif "OPEN" in b_str:
            leaf_bank = "Open"
        else:
            leaf_bank = "Distal"
    else:
        fname_up = fname.upper()
        if "PROX" in fname_up or "SX1" in fname_up:
            leaf_bank = "Proximal"
        elif "OPEN" in fname_up:
            leaf_bank = "Open"
        else:
            leaf_bank = "Distal"

    if not raw_label:
        raw_label = f"G{gantry_angle} {leaf_bank}"

    return {
        "gantry_angle": gantry_angle,
        "leaf_bank": leaf_bank,
        "raw_label": raw_label
    }


def parse_dicom_qc_header(input_source) -> Dict[str, Any]:
    """
    Smart Multi-Platform DICOM Field Classifier:
    Combines extract_gantry_and_bank metadata parser with image geometry checks
    to map DICOM files to target slots: open_0, dist_90, prox_180, etc.
    """
    meta_info = extract_gantry_and_bank(input_source)

    if isinstance(input_source, (str, os.PathLike)):
        dcm = pydicom.dcmread(input_source, stop_before_pixels=True)
        file_name = os.path.basename(input_source)
    else:
        dcm = input_source
        file_name = getattr(dcm, "filename", "dicom_image.dcm")

    rows = int(getattr(dcm, "Rows", 1280))
    cols = int(getattr(dcm, "Columns", 1280))
    station_name = str(getattr(dcm, "StationName", "")).upper()
    model_name = str(getattr(dcm, "ManufacturerModelName", "")).upper()
    full_text = f"{file_name.upper()} {station_name} {model_name} {meta_info['raw_label'].upper()}"

    # Machine Architecture Auto-Detection
    if (rows == 768 and cols == 1024) or (rows == 1024 and cols == 768) or "GRAVITYTB" in full_text or "TRUEBEAM" in full_text:
        machine_type = "TRUEBEAM"
    else:
        machine_type = "HALCYON"

    cardinal_angle = float(meta_info["gantry_angle"])
    leaf_bank = meta_info["leaf_bank"]

    if leaf_bank == "Open":
        beam_type = "OPEN"
    elif leaf_bank == "Proximal":
        beam_type = "HALCYON_PROXIMAL"
    else:
        beam_type = "TRUEBEAM_MLC" if machine_type == "TRUEBEAM" else "HALCYON_DISTAL"

    # Map to Target Slot Name
    angle_str = str(int(cardinal_angle))
    if beam_type == "OPEN":
        target_slot = f"open_{angle_str}"
    elif beam_type == "HALCYON_PROXIMAL":
        target_slot = f"prox_{angle_str}"
    else:
        target_slot = f"dist_{angle_str}"

    pixel_spacing = getattr(dcm, "ImagePlanePixelSpacing", getattr(dcm, "PixelSpacing", [0.336, 0.336]))

    return {
        "machine_type": machine_type,
        "beam_type": beam_type,
        "gantry_angle": cardinal_angle,
        "raw_gantry_angle": float(meta_info["gantry_angle"]),
        "leaf_bank": leaf_bank,
        "raw_label": meta_info["raw_label"],
        "target_slot": target_slot,
        "pixel_spacing_x": float(pixel_spacing[0]),
        "pixel_spacing_y": float(pixel_spacing[1]),
        "rows": rows,
        "cols": cols,
        "filename": file_name
    }
