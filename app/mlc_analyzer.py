import os
import pydicom
import numpy as np
from typing import Dict, Any, List, Union
from app.panel_analyzer import extract_panel_offset

def analyze_leaf_row_dual_metric(
    profile_1d: np.ndarray,
    pixel_spacing_mm: float = 0.336,
    nominal_gap_mm: float = 5.0
) -> Dict[str, Any]:
    """
    Sub-Pixel Dual-Metric Leaf Pair Profile Analyzer:
    Analyzes a 1D intensity profile along a single leaf track (perpendicular to leaf travel direction).
    Computes:
    1. FWHM Sub-Pixel Edge Detection (Rising & Falling 50% threshold edges) -> X_raw, X_left, X_right
    2. Area Under Curve Integration (AUC_i) -> Fluence Transmission Metric
    """
    profile_1d = profile_1d.astype(np.float32)
    rows_len = len(profile_1d)

    p_min = float(np.percentile(profile_1d, 5))
    p_max = float(np.percentile(profile_1d, 95))
    p_range = p_max - p_min

    if p_range < 50.0:
        return {
            "x_left_px": None,
            "x_left_mm": None,
            "x_right_px": None,
            "x_right_mm": None,
            "x_raw_px": None,
            "x_raw_mm": None,
            "aperture_width_mm": None,
            "auc_fluence": 0.0
        }

    thresh = p_min + 0.5 * p_range
    above = np.where(profile_1d >= thresh)[0]

    if len(above) < 2:
        return {
            "x_left_px": None,
            "x_left_mm": None,
            "x_right_px": None,
            "x_right_mm": None,
            "x_raw_px": None,
            "x_raw_mm": None,
            "aperture_width_mm": None,
            "auc_fluence": 0.0
        }

    iso_x = rows_len / 2.0

    # 1. Rising Edge (Left Leaf Bank Tip)
    left_i = above[0]
    if left_i > 0:
        y1, y2 = profile_1d[left_i - 1], profile_1d[left_i]
        frac_l = (thresh - y1) / (y2 - y1 + 1e-12)
        left_px = float(left_i - 1 + frac_l)
    else:
        left_px = float(left_i)

    # 2. Falling Edge (Right Leaf Bank Tip)
    right_i = above[-1]
    if right_i < rows_len - 1:
        y1, y2 = profile_1d[right_i], profile_1d[right_i + 1]
        frac_r = (thresh - y1) / (y2 - y1 + 1e-12)
        right_px = float(right_i + frac_r)
    else:
        right_px = float(right_i)

    # Geometric Sub-Pixel Center & Tips
    x_raw_px = (left_px + right_px) / 2.0
    x_left_mm = (left_px - iso_x) * pixel_spacing_mm
    x_right_mm = (right_px - iso_x) * pixel_spacing_mm
    x_raw_mm = (x_raw_px - iso_x) * pixel_spacing_mm
    width_mm = (right_px - left_px) * pixel_spacing_mm

    # Step 3: Area Fluence Integration (AUC_i) under profile curve
    w_start = max(0, int(round(left_px - 10)))
    w_end = min(rows_len, int(round(right_px + 10)))
    auc_region = np.maximum(0, profile_1d[w_start:w_end] - p_min)
    auc_fluence = float(auc_region.sum() * pixel_spacing_mm)

    return {
        "x_left_px": float(left_px),
        "x_left_mm": float(x_left_mm),
        "x_right_px": float(right_px),
        "x_right_mm": float(x_right_mm),
        "x_raw_px": float(x_raw_px),
        "x_raw_mm": float(x_raw_mm),
        "aperture_width_mm": float(width_mm),
        "auc_fluence": float(auc_fluence)
    }


def analyze_halcyon_triad(
    distal_input: Union[str, np.ndarray],
    proximal_input: Union[str, np.ndarray],
    open_input: Union[str, np.ndarray],
    gantry_angle: float = 0.0,
    dx: float = 0.336,
    dy: float = 0.336
) -> Dict[str, Any]:
    """
    Halcyon Dual-Layer Architecture Pipeline (3-Image Triad per Angle):
    1. Open Field -> extract_panel_offset
    2. Distal Test (MLCX2, 29 pairs) -> analyze_leaf_row_dual_metric
    3. Proximal Test (MLCX1, 28 pairs) -> analyze_leaf_row_dual_metric
    """
    panel_info = extract_panel_offset(open_input, dx=dx, dy=dy)
    delta_x_panel_mm = panel_info["delta_x_panel_mm"]

    def _get_array_and_spacing(inp, default_dx, default_dy):
        if isinstance(inp, (str, os.PathLike)):
            ds = pydicom.dcmread(inp)
            arr = ds.pixel_array.astype(np.float32)
            sid = float(getattr(ds, "RTImageSID", 1000.0))
            sad = float(getattr(ds, "RadiationMachineSAD", 1000.0))
            mag = (sad / sid) if sid > 0 else 1.0
            ps = getattr(ds, "ImagePlanePixelSpacing", [default_dx, default_dy])
            return arr, float(ps[0]) * mag, float(ps[1]) * mag
        return inp.astype(np.float32), default_dx, default_dy

    dist_arr, dx_iso, dy_iso = _get_array_and_spacing(distal_input, dx, dy)
    prox_arr, _, _ = _get_array_and_spacing(proximal_input, dx, dy)

    rows, cols = dist_arr.shape
    iso_x, iso_y = cols / 2.0, rows / 2.0
    pitch_px = 5.0 / dy_iso

    num_tracks = 57
    tracks = []

    dist_p, prox_p = 0, 0
    y_centers = [iso_y + (k - 28) * pitch_px for k in range(num_tracks)]

    for k in range(num_tracks):
        yc = y_centers[k]
        r_idx = int(round(yc))

        if k % 2 == 0:
            dist_p += 1
            bank_name = "Distal (SX2)"
            pair_num = dist_p
            src_arr = dist_arr
        else:
            prox_p += 1
            bank_name = "Proximal (SX1)"
            pair_num = prox_p
            src_arr = prox_arr

        if r_idx < 1 or r_idx >= rows - 1:
            prof = np.zeros(cols, dtype=np.float32)
        else:
            prof = src_arr[r_idx - 1 : r_idx + 2, :].mean(axis=0)

        row_metrics = analyze_leaf_row_dual_metric(prof, pixel_spacing_mm=dx_iso)

        x_raw_mm = row_metrics["x_raw_mm"]
        x_true_mm = (x_raw_mm - delta_x_panel_mm) if x_raw_mm is not None else None

        tracks.append({
            "track_index": k + 1,
            "bank": bank_name,
            "pair_number": pair_num,
            "label": f"{bank_name} Pair {pair_num}",
            "y_center_px": float(yc),
            "y_center_mm": float((yc - iso_y) * dy_iso),
            "x_left_px": row_metrics.get("x_left_px"),
            "x_right_px": row_metrics.get("x_right_px"),
            "x_left_mm": row_metrics.get("x_left_mm"),
            "x_right_mm": row_metrics.get("x_right_mm"),
            "x_raw_px": row_metrics.get("x_raw_px"),
            "x_raw_mm": x_raw_mm,
            "x_true_mm": round(x_true_mm, 3) if x_true_mm is not None else None,
            "auc_fluence": row_metrics["auc_fluence"],
            "aperture_width_mm": row_metrics["aperture_width_mm"]
        })

    return {
        "machine_type": "HALCYON",
        "gantry_angle": float(gantry_angle),
        "panel_offset": panel_info,
        "total_tracks": num_tracks,
        "total_leaves": 114,
        "tracks": tracks
    }


def analyze_truebeam_pair(
    mlc_input: Union[str, np.ndarray],
    open_input: Union[str, np.ndarray],
    gantry_angle: float = 0.0,
    dx: float = 0.385,
    dy: float = 0.385
) -> Dict[str, Any]:
    """
    TrueBeam Single-Layer Millennium 120 Architecture Pipeline (2-Image Pair per Angle):
    1. Open Field -> extract_panel_offset
    2. Combined MLC Slit (60 leaf pairs: Central 40 @ 5mm, Outer 20 @ 10mm) -> analyze_leaf_row_dual_metric
    """
    panel_info = extract_panel_offset(open_input, dx=dx, dy=dy)
    delta_x_panel_mm = panel_info["delta_x_panel_mm"]

    def _get_array_and_spacing(inp, default_dx, default_dy):
        if isinstance(inp, (str, os.PathLike)):
            ds = pydicom.dcmread(inp)
            arr = ds.pixel_array.astype(np.float32)
            sid = float(getattr(ds, "RTImageSID", 1000.0))
            sad = float(getattr(ds, "RadiationMachineSAD", 1000.0))
            mag = (sad / sid) if sid > 0 else 1.0
            ps = getattr(ds, "ImagePlanePixelSpacing", [default_dx, default_dy])
            return arr, float(ps[0]) * mag, float(ps[1]) * mag
        return inp.astype(np.float32), default_dx, default_dy

    mlc_arr, dx_iso, dy_iso = _get_array_and_spacing(mlc_input, dx, dy)
    rows, cols = mlc_arr.shape
    iso_x, iso_y = cols / 2.0, rows / 2.0

    y_positions_mm = []
    # Outer top 10
    for i in range(10):
        y_positions_mm.append(-195.0 + i * 10.0)
    # Central 40
    for i in range(40):
        y_positions_mm.append(-97.5 + i * 5.0)
    # Outer bottom 10
    for i in range(10):
        y_positions_mm.append(105.0 + i * 10.0)

    tracks = []
    for pair_i, y_mm in enumerate(y_positions_mm):
        yc = iso_y + (y_mm / dy_iso)
        r_idx = int(round(yc))

        if r_idx < 1 or r_idx >= rows - 1:
            prof = np.zeros(cols, dtype=np.float32)
        else:
            prof = mlc_arr[r_idx - 1 : r_idx + 2, :].mean(axis=0)

        row_metrics = analyze_leaf_row_dual_metric(prof, pixel_spacing_mm=dx_iso)

        x_raw_mm = row_metrics["x_raw_mm"]
        x_true_mm = (x_raw_mm - delta_x_panel_mm) if x_raw_mm is not None else None

        tracks.append({
            "track_index": pair_i + 1,
            "bank": "Millennium 120",
            "pair_number": pair_i + 1,
            "label": f"Leaf Pair {pair_i + 1}",
            "y_center_px": float(yc),
            "y_center_mm": float(y_mm),
            "x_left_px": row_metrics.get("x_left_px"),
            "x_right_px": row_metrics.get("x_right_px"),
            "x_left_mm": row_metrics.get("x_left_mm"),
            "x_right_mm": row_metrics.get("x_right_mm"),
            "x_raw_px": row_metrics.get("x_raw_px"),
            "x_raw_mm": x_raw_mm,
            "x_true_mm": round(x_true_mm, 3) if x_true_mm is not None else None,
            "auc_fluence": row_metrics["auc_fluence"],
            "aperture_width_mm": row_metrics["aperture_width_mm"]
        })

    return {
        "machine_type": "TRUEBEAM",
        "gantry_angle": float(gantry_angle),
        "panel_offset": panel_info,
        "total_tracks": 60,
        "total_leaves": 120,
        "tracks": tracks
    }
