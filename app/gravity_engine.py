import os
import pydicom
import numpy as np
from typing import List, Dict, Any, Optional
from app.mlc_analyzer import analyze_halcyon_triad, analyze_truebeam_pair

def fit_robust_epid_tilt(y_coords, x_coords):
    """
    Fits EPID detector panel rotation/tilt slope using robust median-of-slopes (Theil-Sen / RANSAC)
    so that single or multiple faulty offset leaves do NOT distort baseline panel tilt estimation.
    """
    y_v = np.asarray(y_coords, dtype=np.float64)
    x_v = np.asarray(x_coords, dtype=np.float64)
    valid = ~np.isnan(x_v) & (x_v != 0.0)
    y_v, x_v = y_v[valid], x_v[valid]
    if len(x_v) < 4:
        return 0.0, float(np.median(x_v)) if len(x_v) > 0 else 0.0
    slopes = []
    n = len(y_v)
    for i in range(n):
        for j in range(i + 1, n):
            dy = y_v[j] - y_v[i]
            if abs(dy) > 20.0:
                slopes.append((x_v[j] - x_v[i]) / dy)
    slope = float(np.median(slopes)) if slopes else 0.0
    intercept = float(np.median(x_v - slope * y_v))
    return slope, intercept

def run_anti_gravity_qc_pipeline(
    cardinal_datasets: List[Dict[str, Any]],
    machine_type: str = "HALCYON",
    warn_sag_mm: float = 0.5,
    action_sag_mm: float = 1.0,
    warn_fluence_pct: float = 5.0,
    apply_magnification_correction: bool = True,
    dx: float = 0.336,
    dy: float = 0.336
) -> Dict[str, Any]:
    """
    Complete Multi-Platform Anti-Gravity QC Engine (5-Step Pipeline):
    Step 1: Extract Panel Flex Offset ΔX_panel(θ) & ΔY_panel(θ) from Open Field images.
    Step 2: Calculate Gantry-Dependent EPID Magnification Factor k_mag(θ) = W_open(0°) / W_open(θ).
    Step 3: Sub-Pixel Edge Detection & True Sag ΔX_sag(θ) for Slit Center AND Individual Leaves (Bank A vs B).
    Step 4: Area Under Curve Integration AUC_i & Dosimetric Fluence Delta ΔD_i(θ).
    Step 5: Baseline 0° System DLG (W_measured - 5mm) & TG-142 Warning/Action Thresholds.
    """
    machine_type = machine_type.upper()
    analyzed_angles = []

    for ds in cardinal_datasets:
        ang = float(ds.get("gantry_angle", 0.0))
        open_f = ds.get("open_field")
        
        if machine_type == "HALCYON":
            dist_f = ds.get("distal_field", ds.get("picket_field"))
            prox_f = ds.get("proximal_field", dist_f)
            res = analyze_halcyon_triad(
                distal_input=dist_f,
                proximal_input=prox_f,
                open_input=open_f,
                gantry_angle=ang,
                dx=dx,
                dy=dy
            )
        else:
            mlc_f = ds.get("mlc_field", ds.get("picket_field", ds.get("distal_field")))
            res = analyze_truebeam_pair(
                mlc_input=mlc_f,
                open_input=open_f,
                gantry_angle=ang,
                dx=0.385,
                dy=0.385
            )
        analyzed_angles.append(res)

    angle_0 = next((a for a in analyzed_angles if abs(a["gantry_angle"] - 0.0) < 45.0), analyzed_angles[0])
    angle_90 = next((a for a in analyzed_angles if abs(a["gantry_angle"] - 90.0) < 45.0), None)
    angle_180 = next((a for a in analyzed_angles if abs(a["gantry_angle"] - 180.0) < 45.0), None)
    angle_270 = next((a for a in analyzed_angles if abs(a["gantry_angle"] - 270.0) < 45.0), None)

    # Extract Baseline 0° Open Field Width for Magnification Correction
    open_w0 = angle_0["panel_offset"].get("open_width_x_mm", 0.0)

    # Compute Gantry-Dependent Relative Magnification Factor k_mag(θ)
    for res in analyzed_angles:
        p_off = res["panel_offset"]
        w_ang = p_off.get("open_width_x_mm", 0.0)
        
        if apply_magnification_correction and open_w0 > 0 and w_ang > 0:
            k_mag = open_w0 / w_ang
        else:
            k_mag = 1.0

        p_off["k_mag"] = round(float(k_mag), 5)
        p_off["effective_sid_mm"] = round(float(p_off.get("nominal_sid_mm", 1000.0) / k_mag), 1)

        # Apply k_mag correction to track true positions and aperture widths
        for tr in res["tracks"]:
            if tr["x_true_mm"] is not None:
                tr["x_true_mm"] = round(tr["x_true_mm"] * k_mag, 3)
            if tr["aperture_width_mm"] is not None:
                tr["aperture_width_mm"] = round(tr["aperture_width_mm"] * k_mag, 3)

    ref_tracks = {t["track_index"]: t for t in angle_0["tracks"]}

    # Fit Robust Bank-Specific EPID Detector Rotation/Tilt Slope at Gantry 0°
    dist_y_0 = [t.get("y_center_mm", 0.0) for t in angle_0["tracks"] if "Distal" in t["bank"] and t["x_true_mm"] is not None]
    dist_x_0 = [t["x_true_mm"] for t in angle_0["tracks"] if "Distal" in t["bank"] and t["x_true_mm"] is not None]
    prox_y_0 = [t.get("y_center_mm", 0.0) for t in angle_0["tracks"] if "Proximal" in t["bank"] and t["x_true_mm"] is not None]
    prox_x_0 = [t["x_true_mm"] for t in angle_0["tracks"] if "Proximal" in t["bank"] and t["x_true_mm"] is not None]

    slope_dist_0, intercept_dist_0 = fit_robust_epid_tilt(dist_y_0, dist_x_0)
    slope_prox_0, intercept_prox_0 = fit_robust_epid_tilt(prox_y_0, prox_x_0)

    # Compute median bank sag shifts at 90° and 270° to isolate individual leaf sags from global panel sag
    dist_sag90_raw, prox_sag90_raw = [], []
    dist_sag270_raw, prox_sag270_raw = [], []

    p_off_0 = angle_0["panel_offset"]
    p_off_90 = angle_90["panel_offset"] if angle_90 else None
    p_off_180 = angle_180["panel_offset"] if angle_180 else None
    p_off_270 = angle_270["panel_offset"] if angle_270 else None

    if angle_90 and p_off_90:
        for t0 in angle_0["tracks"]:
            t90 = next((t for t in angle_90["tracks"] if t["track_index"] == t0["track_index"]), None)
            if t90 and t0.get("x_left_mm") is not None and t90.get("x_left_mm") is not None:
                x_left_0 = (t0["x_left_mm"] - p_off_0["delta_x_panel_mm"]) * p_off_0["k_mag"]
                x_left_90 = (t90["x_left_mm"] - p_off_90["delta_x_panel_mm"]) * p_off_90["k_mag"]
                raw_s90 = x_left_90 - x_left_0
                if "Distal" in t0["bank"]:
                    dist_sag90_raw.append(raw_s90)
                else:
                    prox_sag90_raw.append(raw_s90)

    if angle_270 and p_off_270:
        for t0 in angle_0["tracks"]:
            t270 = next((t for t in angle_270["tracks"] if t["track_index"] == t0["track_index"]), None)
            if t270 and t0.get("x_left_mm") is not None and t270.get("x_left_mm") is not None:
                x_left_0 = (t0["x_left_mm"] - p_off_0["delta_x_panel_mm"]) * p_off_0["k_mag"]
                x_left_270 = (t270["x_left_mm"] - p_off_270["delta_x_panel_mm"]) * p_off_270["k_mag"]
                raw_s270 = x_left_270 - x_left_0
                if "Distal" in t0["bank"]:
                    dist_sag270_raw.append(raw_s270)
                else:
                    prox_sag270_raw.append(raw_s270)

    med_dist_s90 = float(np.median(dist_sag90_raw)) if dist_sag90_raw else 0.0
    med_prox_s90 = float(np.median(prox_sag90_raw)) if prox_sag90_raw else 0.0
    med_dist_s270 = float(np.median(dist_sag270_raw)) if dist_sag270_raw else 0.0
    med_prox_s270 = float(np.median(prox_sag270_raw)) if prox_sag270_raw else 0.0

    nominal_gap_mm = 5.0
    dlg_prox_list, dlg_dist_list = [], []
    for t in angle_0["tracks"]:
        w = t.get("aperture_width_mm")
        if w is not None and 0.5 <= w <= 35.0:
            dlg_val = w - nominal_gap_mm
            if "Proximal" in t["bank"]:
                dlg_prox_list.append(dlg_val)
            elif "Distal" in t["bank"]:
                dlg_dist_list.append(dlg_val)
            else:
                dlg_dist_list.append(dlg_val)

    dlg_prox_mean = round(float(np.mean(dlg_prox_list)), 3) if dlg_prox_list else 0.0
    dlg_dist_mean = round(float(np.mean(dlg_dist_list)), 3) if dlg_dist_list else 0.0
    all_dlgs = dlg_prox_list + dlg_dist_list
    dlg_sys_mean = round(float(np.mean(all_dlgs)), 3) if all_dlgs else 0.0

    combined_metrics = []
    pass_count, warn_count, fail_count = 0, 0, 0
    max_sags = []
    max_individual_leaf_sags = []
    leaf_uncertainties = []
    fluence_deltas = []

    for tr in angle_0["tracks"]:
        idx = tr["track_index"]
        bank = tr["bank"]
        pair_num = tr["pair_number"]
        label = tr["label"]
        y_center_mm = tr.get("y_center_mm", 0.0)
        is_distal = "Distal" in bank

        slope_0 = slope_dist_0 if is_distal else slope_prox_0
        intercept_0 = intercept_dist_0 if is_distal else intercept_prox_0
        med_s90 = med_dist_s90 if is_distal else med_prox_s90
        med_s270 = med_dist_s270 if is_distal else med_prox_s270

        ref_t = ref_tracks.get(idx)
        ref_x = ref_t["x_true_mm"] if ref_t else None
        ref_left_mm = ref_t.get("x_left_mm") if ref_t else None
        ref_right_mm = ref_t.get("x_right_mm") if ref_t else None
        ref_raw_mm = ref_t.get("x_raw_mm") if ref_t else None

        # Calculate True Left & Right positions @ 0°
        x_left_true_0 = ((ref_left_mm - p_off_0["delta_x_panel_mm"]) * p_off_0["k_mag"]) if (ref_left_mm is not None) else None
        x_right_true_0 = ((ref_right_mm - p_off_0["delta_x_panel_mm"]) * p_off_0["k_mag"]) if (ref_right_mm is not None) else None

        # Calculate 0° Leaf Position Calibration Offset Error relative to Bank Detector Baseline
        expected_x0 = intercept_0 + slope_0 * y_center_mm
        calib_offset_mm = (ref_x - expected_x0) if (ref_x is not None) else 0.0

        ref_auc = ref_t["auc_fluence"] if ref_t else 0.0
        ref_w = ref_t.get("aperture_width_mm") if ref_t else None
        ref_dlg = (ref_w - nominal_gap_mm) if (ref_w is not None and 0.5 <= ref_w <= 35.0) else 0.0

        sag_90, sag_180, sag_270 = None, None, None
        sag_left_90, sag_right_90 = None, None
        sag_left_270, sag_right_270 = None, None
        delta_d_90, delta_d_180, delta_d_270 = None, None, None

        t90_left, t90_right, t90_raw = None, None, None
        t270_left, t270_right, t270_raw = None, None, None

        all_left_true = [x_left_true_0] if x_left_true_0 is not None else []
        all_right_true = [x_right_true_0] if x_right_true_0 is not None else []

        if angle_90 and p_off_90:
            t90 = next((t for t in angle_90["tracks"] if t["track_index"] == idx), None)
            if t90:
                t90_left = t90.get("x_left_mm")
                t90_right = t90.get("x_right_mm")
                t90_raw = t90.get("x_raw_mm")
                
                if t90_left is not None and x_left_true_0 is not None:
                    x_left_true_90 = (t90_left - p_off_90["delta_x_panel_mm"]) * p_off_90["k_mag"]
                    sag_left_90 = (x_left_true_90 - x_left_true_0) - med_s90
                    all_left_true.append(x_left_true_90)
                
                if t90_right is not None and x_right_true_0 is not None:
                    x_right_true_90 = (t90_right - p_off_90["delta_x_panel_mm"]) * p_off_90["k_mag"]
                    sag_right_90 = (x_right_true_90 - x_right_true_0) - med_s90
                    all_right_true.append(x_right_true_90)

                if ref_x is not None and t90["x_true_mm"] is not None:
                    sag_90 = (t90["x_true_mm"] - ref_x) - med_s90
                if ref_auc > 0 and t90["auc_fluence"] > 0:
                    delta_d_90 = (t90["auc_fluence"] / ref_auc - 1.0) * 100.0

        if angle_180 and p_off_180:
            t180 = next((t for t in angle_180["tracks"] if t["track_index"] == idx), None)
            if t180:
                if t180.get("x_left_mm") is not None and x_left_true_0 is not None:
                    all_left_true.append((t180["x_left_mm"] - p_off_180["delta_x_panel_mm"]) * p_off_180["k_mag"])
                if t180.get("x_right_mm") is not None and x_right_true_0 is not None:
                    all_right_true.append((t180["x_right_mm"] - p_off_180["delta_x_panel_mm"]) * p_off_180["k_mag"])
                if ref_x is not None and t180["x_true_mm"] is not None:
                    sag_180 = t180["x_true_mm"] - ref_x
                if ref_auc > 0 and t180["auc_fluence"] > 0:
                    delta_d_180 = (t180["auc_fluence"] / ref_auc - 1.0) * 100.0

        if angle_270 and p_off_270:
            t270 = next((t for t in angle_270["tracks"] if t["track_index"] == idx), None)
            if t270:
                t270_left = t270.get("x_left_mm")
                t270_right = t270.get("x_right_mm")
                t270_raw = t270.get("x_raw_mm")

                if t270_left is not None and x_left_true_0 is not None:
                    x_left_true_270 = (t270_left - p_off_270["delta_x_panel_mm"]) * p_off_270["k_mag"]
                    sag_left_270 = (x_left_true_270 - x_left_true_0) - med_s270
                    all_left_true.append(x_left_true_270)

                if t270_right is not None and x_right_true_0 is not None:
                    x_right_true_270 = (t270_right - p_off_270["delta_x_panel_mm"]) * p_off_270["k_mag"]
                    sag_right_270 = (x_right_true_270 - x_right_true_0) - med_s270
                    all_right_true.append(x_right_true_270)

                if ref_x is not None and t270["x_true_mm"] is not None:
                    sag_270 = (t270["x_true_mm"] - ref_x) - med_s270
                if ref_auc > 0 and t270["auc_fluence"] > 0:
                    delta_d_270 = (t270["auc_fluence"] / ref_auc - 1.0) * 100.0

        all_sags = [abs(s) for s in [sag_90, sag_180, sag_270] if s is not None]
        max_s = max(all_sags) if all_sags else 0.0
        max_sags.append(max_s)

        # Per-Leaf Individual Max Sag & Positional Uncertainty Range
        all_individual_leaf_sags = [abs(s) for s in [sag_left_90, sag_right_90, sag_left_270, sag_right_270] if s is not None]
        max_leaf_sag = max(all_individual_leaf_sags) if all_individual_leaf_sags else max_s
        max_individual_leaf_sags.append(max_leaf_sag)

        left_range = (max(all_left_true) - min(all_left_true)) if len(all_left_true) > 1 else 0.0
        right_range = (max(all_right_true) - min(all_right_true)) if len(all_right_true) > 1 else 0.0
        leaf_uncertainty = max(left_range, right_range)
        leaf_uncertainties.append(leaf_uncertainty)

        all_deltas = [abs(d) for d in [delta_d_90, delta_d_180, delta_d_270] if d is not None]
        max_d_pct = max(all_deltas) if all_deltas else 0.0
        fluence_deltas.append(max_d_pct)

        # Combined Positional Deviation (Max of Gravitational Sag and Positional Calibration Offset Error)
        max_leaf_deviation = max(max_leaf_sag, abs(calib_offset_mm))

        status = "PASS"
        if max_leaf_deviation >= action_sag_mm or max_d_pct > (2.0 * warn_fluence_pct):
            status = "FAIL"
            fail_count += 1
        elif max_leaf_deviation >= warn_sag_mm or max_d_pct > warn_fluence_pct:
            status = "WARN"
            warn_count += 1
        else:
            status = "PASS"
            pass_count += 1

        raw_left_shift_90 = (t90_left - ref_left_mm) if (t90_left is not None and ref_left_mm is not None) else None
        raw_right_shift_90 = (t90_right - ref_right_mm) if (t90_right is not None and ref_right_mm is not None) else None

        combined_metrics.append({
            "track_index": idx,
            "bank": bank,
            "pair_number": pair_num,
            "label": label,
            "neutral_0_x_true_mm": ref_x,
            "neutral_0_x_left_mm": round(ref_left_mm, 3) if ref_left_mm is not None else None,
            "neutral_0_x_right_mm": round(ref_right_mm, 3) if ref_right_mm is not None else None,
            "neutral_0_x_raw_mm": round(ref_raw_mm, 3) if ref_raw_mm is not None else None,
            "leaf_calibration_offset_mm": round(calib_offset_mm, 3),
            "neutral_0_auc": round(ref_auc, 3),
            "baseline_0_dlg_mm": round(ref_dlg, 3),
            "raw_left_shift_90_mm": round(raw_left_shift_90, 3) if raw_left_shift_90 is not None else None,
            "raw_right_shift_90_mm": round(raw_right_shift_90, 3) if raw_right_shift_90 is not None else None,
            "sag_left_90_mm": round(sag_left_90, 3) if sag_left_90 is not None else None,
            "sag_right_90_mm": round(sag_right_90, 3) if sag_right_90 is not None else None,
            "sag_left_270_mm": round(sag_left_270, 3) if sag_left_270 is not None else None,
            "sag_right_270_mm": round(sag_right_270, 3) if sag_right_270 is not None else None,
            "sag_90_mm": round(sag_90, 3) if sag_90 is not None else None,
            "sag_180_mm": round(sag_180, 3) if sag_180 is not None else None,
            "sag_270_mm": round(sag_270, 3) if sag_270 is not None else None,
            "delta_d_90_pct": round(delta_d_90, 2) if delta_d_90 is not None else None,
            "delta_d_180_pct": round(delta_d_180, 2) if delta_d_180 is not None else None,
            "delta_d_270_pct": round(delta_d_270, 2) if delta_d_270 is not None else None,
            "max_sag_mm": round(max_s, 3),
            "max_leaf_sag_mm": round(max_leaf_sag, 3),
            "max_leaf_deviation_mm": round(max_leaf_deviation, 3),
            "leaf_positional_uncertainty_mm": round(leaf_uncertainty, 3),
            "max_fluence_delta_pct": round(max_d_pct, 2),
            "status": status
        })

    # Attach per-leaf sag metrics to analyzed_angles tracks for viewer heatmaps
    metrics_by_track = {m["track_index"]: m for m in combined_metrics}
    for a in analyzed_angles:
        for tr in a["tracks"]:
            t_idx = tr["track_index"]
            if t_idx in metrics_by_track:
                m = metrics_by_track[t_idx]
                tr["sag_left_90_mm"] = m["sag_left_90_mm"]
                tr["sag_right_90_mm"] = m["sag_right_90_mm"]
                tr["sag_left_270_mm"] = m["sag_left_270_mm"]
                tr["sag_right_270_mm"] = m["sag_right_270_mm"]
                tr["max_leaf_sag_mm"] = m["max_leaf_sag_mm"]
                tr["status"] = m["status"]

    tot_tracks = len(combined_metrics)
    pass_rate = round((pass_count / tot_tracks * 100.0), 1) if tot_tracks > 0 else 0.0
    max_amp = round(max(max_sags), 3) if max_sags else 0.0
    max_indiv_leaf_sag = round(max(max_individual_leaf_sags), 3) if max_individual_leaf_sags else 0.0
    mean_uncertainty = round(float(np.mean(leaf_uncertainties)), 3) if leaf_uncertainties else 0.0
    mae_sag = round(float(np.mean(max_sags)), 3) if max_sags else 0.0
    max_f_delta = round(max(fluence_deltas), 2) if fluence_deltas else 0.0

    worst_leaf_metric = max(combined_metrics, key=lambda m: m["max_leaf_sag_mm"]) if combined_metrics else None
    worst_leaf_label = f"Track {worst_leaf_metric['track_index']} ({worst_leaf_metric['bank']})" if worst_leaf_metric else "--"

    panel_offsets = {
        int(a["gantry_angle"]): a["panel_offset"] for a in analyzed_angles
    }

    summary = {
        "machine_type": machine_type.upper(),
        "total_tracks_analyzed": tot_tracks,
        "total_leaves": analyzed_angles[0]["total_leaves"],
        "baseline_g0_dlg": {
            "dlg_proximal_mm": dlg_prox_mean,
            "dlg_distal_mm": dlg_dist_mean,
            "dlg_system_mm": dlg_sys_mean
        },
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "pass_rate_pct": pass_rate,
        "max_sag_amplitude_mm": max_amp,
        "max_individual_leaf_sag_mm": max_indiv_leaf_sag,
        "worst_leaf_label": worst_leaf_label,
        "mean_leaf_positional_uncertainty_mm": mean_uncertainty,
        "mean_abs_sag_mm": mae_sag,
        "max_dosimetric_delta_pct": max_f_delta,
        "panel_offsets": panel_offsets,
        "magnification_correction_applied": apply_magnification_correction,
        "sag_warn_threshold_mm": warn_sag_mm,
        "sag_action_threshold_mm": action_sag_mm,
        "fluence_warn_threshold_pct": warn_fluence_pct
    }

    return {
        "summary": summary,
        "analyzed_angles": analyzed_angles,
        "combined_metrics": combined_metrics
    }
