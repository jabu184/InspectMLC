import numpy as np
from scipy.signal import find_peaks

def detect_leaf_edges_1d(profile: np.ndarray, threshold_ratio: float = 0.5):
    """
    Sub-pixel leaf tip detection on a 1D intensity profile.
    Returns:
        (left_edge_px, right_edge_px)
    """
    bg = np.percentile(profile, 5)
    fg = np.percentile(profile, 95)
    if fg - bg < 50:  # empty or blocked track
        return None, None
        
    thresh = bg + threshold_ratio * (fg - bg)
    above = profile > thresh
    indices = np.where(above)[0]
    
    if len(indices) == 0:
        return None, None
        
    left_idx = indices[0]
    right_idx = indices[-1]
    
    # Sub-pixel interpolation for left edge (rising edge)
    if left_idx > 0:
        y1, y2 = profile[left_idx - 1], profile[left_idx]
        if y2 != y1:
            left_edge = (left_idx - 1) + (thresh - y1) / (y2 - y1)
        else:
            left_edge = float(left_idx)
    else:
        left_edge = float(left_idx)
        
    # Sub-pixel interpolation for right edge (falling edge)
    if right_idx < len(profile) - 1:
        y1, y2 = profile[right_idx], profile[right_idx + 1]
        if y2 != y1:
            right_edge = right_idx + (thresh - y1) / (y2 - y1)
        else:
            right_edge = float(right_idx)
    else:
        right_edge = float(right_idx)
        
    return left_edge, right_edge


def analyze_halcyon_leaves(pixel_array: np.ndarray, dx: float, dy: float, threshold_ratio: float = 0.5):
    """
    Analyzes Varian Halcyon Dual-Layer Staggered MLC geometry.
    Halcyon features 2 layers (SX1 Proximal and SX2 Distal) of 28 leaf pairs each (56 total pairs).
    The Distal layer is staggered by 5 mm (half a leaf width) relative to the Proximal layer,
    resulting in 56 effective 5 mm leaf tracks spanning the radiation field.
    """
    rows, cols = pixel_array.shape
    iso_x, iso_y = cols / 2.0, rows / 2.0
    
    num_tracks = 56
    pitch_mm = 5.0  # 5mm effective pitch for staggered dual-layer MLC
    pitch_px = pitch_mm / dy
    
    y_start = iso_y - (num_tracks / 2.0) * pitch_px
    y_centers = [y_start + (i + 0.5) * pitch_px for i in range(num_tracks)]
    
    leaves_data = []
    
    for i, yc in enumerate(y_centers):
        r_idx = int(round(yc))
        
        # Bank assignment (Even = Proximal SX1, Odd = Distal SX2)
        bank = "Proximal (SX1)" if (i % 2 == 0) else "Distal (SX2)"
        pair_num = (i // 2) + 1
        
        if r_idx < 1 or r_idx >= rows - 1:
            leaves_data.append({
                "track_index": i + 1,
                "bank": bank,
                "pair_number": pair_num,
                "label": f"{bank} Pair {pair_num}",
                "y_center_px": yc,
                "y_center_mm": (yc - iso_y) * dy,
                "left_px": None,
                "left_mm": None,
                "right_px": None,
                "right_mm": None
            })
            continue
            
        # Average across 3 adjacent rows for noise smoothing
        prof = pixel_array[r_idx - 1 : r_idx + 2, :].mean(axis=0)
        
        left_px, right_px = detect_leaf_edges_1d(prof, threshold_ratio=threshold_ratio)
        
        left_mm = (left_px - iso_x) * dx if left_px is not None else None
        right_mm = (right_px - iso_x) * dx if right_px is not None else None
        
        leaves_data.append({
            "track_index": i + 1,
            "bank": bank,
            "pair_number": pair_num,
            "label": f"{bank} Pair {pair_num}",
            "y_center_px": float(yc),
            "y_center_mm": float((yc - iso_y) * dy),
            "left_px": float(left_px) if left_px is not None else None,
            "left_mm": float(left_mm) if left_mm is not None else None,
            "right_px": float(right_px) if right_px is not None else None,
            "right_mm": float(right_mm) if right_mm is not None else None
        })
        
    return leaves_data
