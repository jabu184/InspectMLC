import os
import pydicom
import numpy as np
from typing import Dict, Any, Union

def extract_panel_offset(
    open_input: Union[str, os.PathLike, np.ndarray, pydicom.dataset.FileDataset],
    dx: float = 0.336,
    dy: float = 0.336
) -> Dict[str, Any]:
    """
    Step 1: Panel Flex & CAX Centering + Open Field Width for Magnification Analysis
    Extracts EPID detector panel displacement delta_X_panel(theta) & delta_Y_panel(theta)
    relative to ideal CAX using 50% FWHM field boundaries and center-of-mass analysis of an Open Field image.
    Also extracts empirical horizontal and vertical open field FWHM widths in mm.
    """
    sid = 1000.0
    gantry = 0.0

    if isinstance(open_input, (str, os.PathLike)):
        dcm = pydicom.dcmread(open_input)
        pixel_array = dcm.pixel_array.astype(np.float32)
        ps = getattr(dcm, "ImagePlanePixelSpacing", getattr(dcm, "PixelSpacing", [dx, dy]))
        dx, dy = float(ps[0]), float(ps[1])
        gantry = float(getattr(dcm, "GantryAngle", 0.0))
        sid = float(getattr(dcm, "RTImageSID", 1000.0))
    elif isinstance(open_input, pydicom.dataset.FileDataset):
        pixel_array = open_input.pixel_array.astype(np.float32)
        ps = getattr(open_input, "ImagePlanePixelSpacing", getattr(open_input, "PixelSpacing", [dx, dy]))
        dx, dy = float(ps[0]), float(ps[1])
        gantry = float(getattr(open_input, "GantryAngle", 0.0))
        sid = float(getattr(open_input, "RTImageSID", 1000.0))
    elif isinstance(open_input, np.ndarray):
        pixel_array = open_input.astype(np.float32)
        gantry = 0.0
    else:
        raise ValueError("Invalid open field input format.")

    rows, cols = pixel_array.shape
    iso_x = cols / 2.0
    iso_y = rows / 2.0

    # 1. Horizontal profile across middle region
    mid_r_start = int(iso_y - 40)
    mid_r_end = int(iso_y + 40)
    col_profile = pixel_array[mid_r_start:mid_r_end, :].mean(axis=0)

    p_min_x = np.percentile(col_profile, 5)
    p_max_x = np.percentile(col_profile, 95)
    thresh_x = p_min_x + 0.5 * (p_max_x - p_min_x)

    above_x = np.where(col_profile > thresh_x)[0]
    if len(above_x) > 0:
        left_px = float(above_x[0])
        right_px = float(above_x[-1])
        fwhm_center_px = (left_px + right_px) / 2.0
        open_width_x_mm = (right_px - left_px) * dx
    else:
        fwhm_center_px = iso_x
        open_width_x_mm = 0.0

    # 2. Vertical profile down center region
    mid_c_start = int(iso_x - 40)
    mid_c_end = int(iso_x + 40)
    row_profile = pixel_array[:, mid_c_start:mid_c_end].mean(axis=1)

    p_min_y = np.percentile(row_profile, 5)
    p_max_y = np.percentile(row_profile, 95)
    thresh_y = p_min_y + 0.5 * (p_max_y - p_min_y)

    above_y = np.where(row_profile > thresh_y)[0]
    if len(above_y) > 0:
        top_px = float(above_y[0])
        bottom_px = float(above_y[-1])
        fwhm_center_y_px = (top_px + bottom_px) / 2.0
        open_width_y_mm = (bottom_px - top_px) * dy
    else:
        fwhm_center_y_px = iso_y
        open_width_y_mm = 0.0

    # 3. Center of Mass verification
    bg_sub_x = np.maximum(0, col_profile - p_min_x)
    com_center_px = float((np.arange(cols) * bg_sub_x).sum() / bg_sub_x.sum()) if bg_sub_x.sum() > 0 else iso_x

    # Blend FWHM midpoint and Center of Mass for robust sub-pixel panel center
    x_measured_px = 0.7 * fwhm_center_px + 0.3 * com_center_px
    delta_x_panel_px = x_measured_px - iso_x
    delta_x_panel_mm = delta_x_panel_px * dx

    delta_y_panel_px = fwhm_center_y_px - iso_y
    delta_y_panel_mm = delta_y_panel_px * dy

    warning = abs(delta_x_panel_mm) > 1.0 or abs(delta_y_panel_mm) > 1.0

    return {
        "gantry_angle": gantry,
        "x_ideal_cax_px": iso_x,
        "y_ideal_cax_px": iso_y,
        "x_measured_open_px": float(x_measured_px),
        "y_measured_open_px": float(fwhm_center_y_px),
        "delta_x_panel_px": float(delta_x_panel_px),
        "delta_x_panel_mm": round(float(delta_x_panel_mm), 3),
        "delta_y_panel_px": float(delta_y_panel_px),
        "delta_y_panel_mm": round(float(delta_y_panel_mm), 3),
        "open_width_x_mm": round(float(open_width_x_mm), 2),
        "open_width_y_mm": round(float(open_width_y_mm), 2),
        "nominal_sid_mm": float(sid),
        "warning_panel_offset": warning
    }
