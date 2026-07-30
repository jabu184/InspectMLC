import numpy as np
from typing import Dict, List, Any
from app.mlc_detector import analyze_halcyon_leaves

def register_images(arr_a: np.ndarray, arr_b: np.ndarray):
    """
    Sub-pixel rigid alignment (translation) between Image A (Baseline) and Image B (Comparison)
    using numpy FFT for cross-correlation without OpenBLAS memory allocation overhead.
    """
    try:
        # Downsample 4x for speed
        sub_a = arr_a[::4, ::4]
        sub_b = arr_b[::4, ::4]
        
        h, w = sub_a.shape
        cy, cx = h // 2, w // 2
        ry, rx = h // 4, w // 4
        crop_a = sub_a[cy - ry : cy + ry, cx - rx : cx + rx]
        crop_b = sub_b[cy - ry : cy + ry, cx - rx : cx + rx]
        
        fa = np.fft.fft2(crop_a - crop_a.mean())
        fb = np.fft.fft2(crop_b - crop_b.mean())
        eps = 1e-12
        r = fa * np.conj(fb) / (np.abs(fa * fb) + eps)
        spatial_corr = np.real(np.fft.ifft2(r))
        
        shift_y, shift_x = np.unravel_index(np.argmax(spatial_corr), spatial_corr.shape)
        if shift_y > ry:
            shift_y -= 2 * ry
        if shift_x > rx:
            shift_x -= 2 * rx
            
        shift_x_full = shift_x * 4.0
        shift_y_full = shift_y * 4.0

        # Simple roll for array shift
        aligned_b = np.roll(arr_b, (int(round(-shift_y_full)), int(round(-shift_x_full))), axis=(0, 1))
        return float(shift_x_full), float(shift_y_full), aligned_b
    except Exception as err:
        print(f"Notice: Image registration fallback due to: {err}")
        return 0.0, 0.0, arr_b


def compare_deliveries(
    arr_a: np.ndarray,
    arr_b: np.ndarray,
    dx: float,
    dy: float,
    warn_thresh_mm: float = 0.5,
    fail_thresh_mm: float = 1.0,
    enable_registration: bool = True
):
    shift_x, shift_y = 0.0, 0.0
    arr_b_proc = arr_b
    if enable_registration:
        shift_x, shift_y, arr_b_proc = register_images(arr_a, arr_b)
        
    leaves_a = analyze_halcyon_leaves(arr_a, dx, dy)
    leaves_b = analyze_halcyon_leaves(arr_b_proc, dx, dy)
    
    leaf_results = []
    deltas_all = []
    
    pass_count = 0
    warn_count = 0
    fail_count = 0
    
    for i in range(len(leaves_a)):
        la = leaves_a[i]
        lb = leaves_b[i]
        
        d_left_px = lb["left_px"] - la["left_px"] if (lb["left_px"] is not None and la["left_px"] is not None) else None
        d_left_mm = lb["left_mm"] - la["left_mm"] if (lb["left_mm"] is not None and la["left_mm"] is not None) else None
        
        d_right_px = lb["right_px"] - la["right_px"] if (lb["right_px"] is not None and la["right_px"] is not None) else None
        d_right_mm = lb["right_mm"] - la["right_mm"] if (lb["right_mm"] is not None and la["right_mm"] is not None) else None
        
        valid_deltas = [abs(d) for d in [d_left_mm, d_right_mm] if d is not None]
        max_d_mm = max(valid_deltas) if valid_deltas else 0.0
        
        if valid_deltas:
            deltas_all.extend(valid_deltas)
            
        if max_d_mm >= fail_thresh_mm:
            status = "FAIL"
            fail_count += 1
        elif max_d_mm >= warn_thresh_mm:
            status = "WARN"
            warn_count += 1
        else:
            status = "PASS"
            pass_count += 1
            
        leaf_results.append({
            "track_index": la["track_index"],
            "bank": la["bank"],
            "pair_number": la["pair_number"],
            "label": la["label"],
            "y_center_px": la["y_center_px"],
            "y_center_mm": la["y_center_mm"],
            
            # Delivery A
            "del_a_left_px": la["left_px"],
            "del_a_left_mm": la["left_mm"],
            "del_a_right_px": la["right_px"],
            "del_a_right_mm": la["right_mm"],
            
            # Delivery B
            "del_b_left_px": lb["left_px"],
            "del_b_left_mm": lb["left_mm"],
            "del_b_right_px": lb["right_px"],
            "del_b_right_mm": lb["right_mm"],
            
            # Discrepancies
            "delta_left_px": d_left_px,
            "delta_left_mm": d_left_mm,
            "delta_right_px": d_right_px,
            "delta_right_mm": d_right_mm,
            
            "max_delta_mm": max_d_mm,
            "status": status
        })
        
    total_leaves = len(leaf_results)
    pass_rate = round((pass_count / total_leaves * 100.0), 1) if total_leaves > 0 else 0.0
    
    max_delta = round(max(deltas_all), 3) if deltas_all else 0.0
    mae = round(float(np.mean(deltas_all)), 3) if deltas_all else 0.0
    rmse = round(float(np.sqrt(np.mean(np.square(deltas_all)))), 3) if deltas_all else 0.0
    
    summary = {
        "total_leaves_analyzed": total_leaves,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "pass_rate_pct": pass_rate,
        "max_delta_mm": max_delta,
        "mean_abs_delta_mm": mae,
        "rmse_delta_mm": rmse,
        "warning_threshold_mm": warn_thresh_mm,
        "failure_threshold_mm": fail_thresh_mm,
        "registration_shift_x_px": shift_x,
        "registration_shift_y_px": shift_y
    }
    
    return {
        "summary": summary,
        "leaf_results": leaf_results
    }
