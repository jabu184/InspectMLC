import os
import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from PIL import Image

def gaussian_blur_1d(arr: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    """Fast 1D Gaussian blur using numpy convolution without OpenBLAS calls."""
    radius = int(round(3 * sigma))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-0.5 * (x / sigma) ** 2)
    kernel /= kernel.sum()
    return np.convolve(arr, kernel, mode='same')


def generate_synthetic_mlc_image(
    gantry_angle: float = 0.0,
    pattern_type: str = "picket_fence",
    faults_dict: dict = None,
    rows: int = 1280,
    cols: int = 1280,
    dx: float = 0.336,
    dy: float = 0.336
) -> np.ndarray:
    """
    Generates a realistic 16-bit synthetic Halcyon MV image (1280x1280 array)
    with dual-layer transmission penumbra, customizable gantry angles,
    and injected hardware faults (stuck leaves, calibration offsets, gravitational sag, and noise).
    """
    if faults_dict is None:
        faults_dict = {}

    iso_x, iso_y = cols / 2.0, rows / 2.0
    num_tracks = 56
    pitch_px = 5.0 / dy

    track_positions = {}
    for i in range(1, num_tracks + 1):
        if pattern_type == "picket_fence":
            track_positions[i] = {
                "left_mm": -100.0,
                "right_mm": 100.0
            }
        else:
            track_positions[i] = {
                "left_mm": -120.0,
                "right_mm": 120.0
            }

    cal_offsets = faults_dict.get("calibration_offsets", {})
    bank_sx1_offset = float(faults_dict.get("bank_calibration_offset_sx1", 0.0))
    bank_sx2_offset = float(faults_dict.get("bank_calibration_offset_sx2", 0.0))

    for i in range(1, num_tracks + 1):
        bank_shift = bank_sx1_offset if (i % 2 != 0) else bank_sx2_offset
        indiv_shift = float(cal_offsets.get(i, cal_offsets.get(str(i), 0.0)))
        tot_shift = bank_shift + indiv_shift
        track_positions[i]["left_mm"] += tot_shift
        track_positions[i]["right_mm"] += tot_shift

    sag_amp = float(faults_dict.get("sag_amplitude_mm", 0.0))
    if sag_amp != 0.0:
        angle_rad = np.radians(gantry_angle)
        sag_shift = sag_amp * np.sin(angle_rad)
        for i in range(1, num_tracks + 1):
            track_positions[i]["left_mm"] += sag_shift
            track_positions[i]["right_mm"] += sag_shift

    stuck_dict = faults_dict.get("stuck_leaves", {})
    for i in range(1, num_tracks + 1):
        if i in stuck_dict or str(i) in stuck_dict:
            fixed_pos = float(stuck_dict.get(i, stuck_dict.get(str(i))))
            track_positions[i]["left_mm"] = fixed_pos - 10.0
            track_positions[i]["right_mm"] = fixed_pos + 10.0

    bg_val = 5000.0
    fg_val = 55000.0
    img_arr = np.full((rows, cols), bg_val, dtype=np.float32)

    y_start = iso_y - (num_tracks / 2.0) * pitch_px
    y_centers = [y_start + (i - 0.5) * pitch_px for i in range(1, num_tracks + 1)]
    x_indices = np.arange(cols)

    prof_buf = np.full(cols, bg_val, dtype=np.float32)

    for i, yc in enumerate(y_centers):
        r_idx = int(round(yc))
        half_w = int(round(pitch_px / 2.0))
        r_min = max(0, r_idx - half_w)
        r_max = min(rows, r_idx + half_w)

        pos = track_positions[i + 1]
        l_px = iso_x + (pos["left_mm"] / dx)
        r_px = iso_x + (pos["right_mm"] / dx)

        prof_buf.fill(bg_val)
        in_field = (x_indices >= l_px) & (x_indices <= r_px)
        prof_buf[in_field] = fg_val

        prof_smooth = gaussian_blur_1d(prof_buf, sigma=1.0)
        img_arr[r_min:r_max, :] = prof_smooth

    noise_std = float(faults_dict.get("gaussian_noise_std", 0.0))
    if noise_std > 0:
        g_noise = np.random.normal(0, noise_std, (rows, cols)).astype(np.float32)
        img_arr += g_noise

    img_arr = np.clip(img_arr, 0, 65535).astype(np.float32)
    return img_arr


def parse_cp_blds(cp):
    """Parses Jaw and MLC leaf position arrays from a DICOM ControlPoint dataset."""
    jaw_x = [-140.0, 140.0]
    jaw_y = [-140.0, 140.0]
    mlcx1_pos = None
    mlcx2_pos = None

    if hasattr(cp, "BeamLimitingDevicePositionSequence"):
        for bld in cp.BeamLimitingDevicePositionSequence:
            dev_type = str(getattr(bld, "RTBeamLimitingDeviceType", "")).upper()
            pos = [float(val) for val in getattr(bld, "LeafJawPositions", [])]
            
            if dev_type in ["X", "ASYMX"] and len(pos) >= 2:
                jaw_x = [pos[0], pos[1]]
            elif dev_type in ["Y", "ASYMY"] and len(pos) >= 2:
                jaw_y = [pos[0], pos[1]]
            elif dev_type in ["MLCX1", "MLCX"]:
                mlcx1_pos = pos
            elif dev_type == "MLCX2":
                mlcx2_pos = pos

    return jaw_x, jaw_y, mlcx1_pos, mlcx2_pos


def render_aperture_transmission(
    mlcx1_pos,
    mlcx2_pos,
    jaw_x,
    jaw_y,
    leaf_transmission: float,
    focal_spot_sigma: float,
    rows: int = 1280,
    cols: int = 1280,
    dx: float = 0.336,
    dy: float = 0.336
):
    """Renders 2D transmission array T(x, y) for a specific interpolated MLC aperture."""
    iso_x, iso_y = cols / 2.0, rows / 2.0
    x_indices = np.arange(cols)

    layer1_trans = np.full((rows, cols), leaf_transmission, dtype=np.float32)
    layer2_trans = np.full((rows, cols), leaf_transmission, dtype=np.float32)

    # 1. Process MLCX1 (Proximal - 28 pairs, 10mm width)
    if mlcx1_pos and len(mlcx1_pos) >= 56:
        half_len = len(mlcx1_pos) // 2
        bank_a = mlcx1_pos[:half_len]
        bank_b = mlcx1_pos[half_len:]
        
        w_px = 10.0 / dy
        y_centers = [iso_y + (i - (half_len / 2.0) + 0.5) * w_px for i in range(half_len)]
        prof_buf = np.full(cols, leaf_transmission, dtype=np.float32)

        for i, yc in enumerate(y_centers):
            r_idx = int(round(yc))
            half_w = int(round(w_px / 2.0))
            r_min = max(0, r_idx - half_w)
            r_max = min(rows, r_idx + half_w)

            left_mm = float(bank_a[i])
            right_mm = float(bank_b[i])
            l_px = iso_x + (left_mm / dx)
            r_px = iso_x + (right_mm / dx)

            prof_buf.fill(leaf_transmission)
            if r_px > l_px:
                in_field = (x_indices >= l_px) & (x_indices <= r_px)
                prof_buf[in_field] = 1.0

            prof_smooth = gaussian_blur_1d(prof_buf, sigma=focal_spot_sigma)
            layer1_trans[r_min:r_max, :] = prof_smooth
    else:
        layer1_trans.fill(1.0)

    # 2. Process MLCX2 (Distal - 29 pairs, 10mm width, staggered)
    if mlcx2_pos and len(mlcx2_pos) >= 58:
        half_len = len(mlcx2_pos) // 2
        bank_a = mlcx2_pos[:half_len]
        bank_b = mlcx2_pos[half_len:]
        
        w_px = 10.0 / dy
        y_centers = [iso_y + (i - (half_len / 2.0) + 0.5) * w_px for i in range(half_len)]
        prof_buf = np.full(cols, leaf_transmission, dtype=np.float32)

        for i, yc in enumerate(y_centers):
            r_idx = int(round(yc))
            half_w = int(round(w_px / 2.0))
            r_min = max(0, r_idx - half_w)
            r_max = min(rows, r_idx + half_w)

            left_mm = float(bank_a[i])
            right_mm = float(bank_b[i])
            l_px = iso_x + (left_mm / dx)
            r_px = iso_x + (right_mm / dx)

            prof_buf.fill(leaf_transmission)
            if r_px > l_px:
                in_field = (x_indices >= l_px) & (x_indices <= r_px)
                prof_buf[in_field] = 1.0

            prof_smooth = gaussian_blur_1d(prof_buf, sigma=focal_spot_sigma)
            layer2_trans[r_min:r_max, :] = prof_smooth
    else:
        layer2_trans.fill(1.0)

    # Combined Dual-Layer Transmission
    cp_fluence = layer1_trans * layer2_trans

    # 3. Apply Jaw Bounding Box Mask
    jx_min_px = int(round(iso_x + (jaw_x[0] / dx)))
    jx_max_px = int(round(iso_x + (jaw_x[1] / dx)))
    jy_min_px = int(round(iso_y + (jaw_y[0] / dy)))
    jy_max_px = int(round(iso_y + (jaw_y[1] / dy)))

    cp_fluence[:max(0, jy_min_px), :] = 0.001
    cp_fluence[min(rows, jy_max_px):, :] = 0.001
    cp_fluence[:, :max(0, jx_min_px)] = 0.001
    cp_fluence[:, min(cols, jx_max_px):] = 0.001

    return cp_fluence


def simulate_plan_fluence_map(
    input_plan_path: str,
    beam_number: int = 1,
    control_point_index: Optional[int] = None,
    focal_spot_sigma: float = 1.0,
    leaf_transmission: float = 0.13,
    sub_steps_per_segment: int = 8,
    rows: int = 1280,
    cols: int = 1280,
    dx: float = 0.336,
    dy: float = 0.336
):
    """
    Simulates a Linac MV Imager 2D Pseudo-Fluence Map from an input DICOM RT Plan (RTPLAN).
    Models S-curve velocity deceleration profiles at control point picket boundaries,
    dual-layer MLC transmission, Jaw masking, and in-field EPID contrast scaling to match
    real machine portal image outputs (sampleimage.dcm).
    """
    if not os.path.exists(input_plan_path):
        raise FileNotFoundError(f"Input RT Plan file not found: {input_plan_path}")

    dcm = pydicom.dcmread(input_plan_path)
    
    plan_meta = {
        "plan_name": str(getattr(dcm, "RTPlanName", "UNNAMED_PLAN")),
        "patient_name": str(getattr(dcm, "PatientName", "ANONYMOUS")),
        "beam_number": beam_number,
        "gantry_angle": 0.0,
        "collimator_angle": 0.0,
        "total_control_points": 0
    }

    beam = None
    if hasattr(dcm, "BeamSequence"):
        for b in dcm.BeamSequence:
            if getattr(b, "BeamNumber", 1) == beam_number:
                beam = b
                break
        if beam is None and len(dcm.BeamSequence) > 0:
            beam = dcm.BeamSequence[0]

    if beam is None or not hasattr(beam, "ControlPointSequence"):
        raise ValueError("Selected DICOM RT Plan has no valid Beam or ControlPointSequence.")

    cp_seq = list(beam.ControlPointSequence)
    plan_meta["total_control_points"] = len(cp_seq)

    total_fluence = np.zeros((rows, cols), dtype=np.float32)

    if control_point_index is not None and 0 <= control_point_index < len(cp_seq):
        cp = cp_seq[control_point_index]
        gantry_angle = float(getattr(cp, "GantryAngle", 0.0))
        coll_angle = float(getattr(cp, "BeamLimitingDeviceAngle", 0.0))
        plan_meta["gantry_angle"] = gantry_angle
        plan_meta["collimator_angle"] = coll_angle

        jaw_x, jaw_y, mlcx1, mlcx2 = parse_cp_blds(cp)
        total_fluence = render_aperture_transmission(
            mlcx1, mlcx2, jaw_x, jaw_y, leaf_transmission, focal_spot_sigma, rows, cols, dx, dy
        )

        if abs(coll_angle) > 0.1:
            pil_cp = Image.fromarray(total_fluence)
            pil_cp_rot = pil_cp.rotate(coll_angle, resample=Image.BICUBIC)
            total_fluence = np.array(pil_cp_rot, dtype=np.float32)

    else:
        plan_meta["gantry_angle"] = float(getattr(cp_seq[0], "GantryAngle", 0.0))
        plan_meta["collimator_angle"] = float(getattr(cp_seq[0], "BeamLimitingDeviceAngle", 0.0))

        for cp_idx in range(len(cp_seq) - 1):
            cp_curr = cp_seq[cp_idx]
            cp_next = cp_seq[cp_idx + 1]

            m_curr = float(getattr(cp_curr, "CumulativeMetersetWeight", cp_idx / (len(cp_seq) - 1)))
            m_next = float(getattr(cp_next, "CumulativeMetersetWeight", (cp_idx + 1) / (len(cp_seq) - 1)))
            delta_mu = max(1e-6, m_next - m_curr)

            jaw_x_0, jaw_y_0, mlcx1_0, mlcx2_0 = parse_cp_blds(cp_curr)
            jaw_x_1, jaw_y_1, mlcx1_1, mlcx2_1 = parse_cp_blds(cp_next)

            for sub in range(sub_steps_per_segment):
                s = (sub + 0.5) / sub_steps_per_segment
                # Cosine velocity S-curve interpolation
                t = 0.5 * (1.0 - np.cos(np.pi * s))
                sub_weight = delta_mu / sub_steps_per_segment

                j_x_t = [(1 - t) * jaw_x_0[0] + t * jaw_x_1[0], (1 - t) * jaw_x_0[1] + t * jaw_x_1[1]]
                j_y_t = [(1 - t) * jaw_y_0[0] + t * jaw_y_1[0], (1 - t) * jaw_y_0[1] + t * jaw_y_1[1]]

                m1_t = None
                if mlcx1_0 and mlcx1_1 and len(mlcx1_0) == len(mlcx1_1):
                    m1_t = [(1 - t) * mlcx1_0[k] + t * mlcx1_1[k] for k in range(len(mlcx1_0))]
                elif mlcx1_0:
                    m1_t = mlcx1_0

                m2_t = None
                if mlcx2_0 and mlcx2_1 and len(mlcx2_0) == len(mlcx2_1):
                    m2_t = [(1 - t) * mlcx2_0[k] + t * mlcx2_1[k] for k in range(len(mlcx2_0))]
                elif mlcx2_0:
                    m2_t = mlcx2_0

                sub_fluence = render_aperture_transmission(
                    m1_t, m2_t, j_x_t, j_y_t, leaf_transmission, focal_spot_sigma, rows, cols, dx, dy
                )

                coll_angle = float(getattr(cp_curr, "BeamLimitingDeviceAngle", 0.0))
                if abs(coll_angle) > 0.1:
                    pil_cp = Image.fromarray(sub_fluence)
                    pil_cp_rot = pil_cp.rotate(coll_angle, resample=Image.BICUBIC)
                    sub_fluence = np.array(pil_cp_rot, dtype=np.float32)

                total_fluence += sub_fluence * sub_weight

    # Calculate Linac Primary Beam Radial Profile I_beam(r)
    iso_x, iso_y = cols / 2.0, rows / 2.0
    y_grid, x_grid = np.ogrid[:rows, :cols]
    r_mm = np.sqrt((x_grid - iso_x)**2 * (dx**2) + (y_grid - iso_y)**2 * (dy**2))
    radial_beam_profile = np.exp(-0.5 * (r_mm / 260.0)**2).astype(np.float32)

    # In-Field Jaw contrast windowing matching machine EPID display
    j_min_x, j_max_x = max(0, int(iso_x - 140 / dx)), min(cols, int(iso_x + 140 / dx))
    j_min_y, j_max_y = max(0, int(iso_y - 140 / dy)), min(rows, int(iso_y + 140 / dy))

    jaw_region = total_fluence[j_min_y:j_max_y, j_min_x:j_max_x]
    p_min = np.percentile(jaw_region, 1)
    p_max = np.percentile(jaw_region, 99)

    norm_in_field = np.clip((jaw_region - p_min) / (p_max - p_min + 1e-6), 0.0, 1.0)
    
    scaled_pixel_array = np.full((rows, cols), 1320.0, dtype=np.float32)
    scaled_pixel_array[j_min_y:j_max_y, j_min_x:j_max_x] = (
        1320.0 + norm_in_field * radial_beam_profile[j_min_y:j_max_y, j_min_x:j_max_x] * 57000.0
    ).astype(np.float32)

    return scaled_pixel_array, plan_meta["gantry_angle"], plan_meta


def save_synthetic_dicom_rtimage(
    pixel_array: np.ndarray,
    output_path: str,
    gantry_angle: float = 0.0,
    label: str = "HAL_MV_SIM"
):
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = pydicom.uid.RTImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(output_path, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.SOPClassUID = pydicom.uid.RTImageStorage
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = "RTIMAGE"
    ds.Manufacturer = "Varian"
    ds.ManufacturerModelName = "Halcyon-QC"
    ds.StationName = "HAL7_SIM"
    ds.RTImageLabel = str(label)[:16]
    ds.GantryAngle = float(gantry_angle)
    ds.BeamLimitingDeviceAngle = 0.0
    ds.RadiationMachineSAD = 1000.0
    ds.ImagePlanePixelSpacing = [0.336, 0.336]
    ds.PixelSpacing = [0.336, 0.336]

    rows, cols = pixel_array.shape
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"

    ds.PixelData = pixel_array.astype(np.uint16).tobytes()
    ds.save_as(output_path)
    return output_path


def modify_rtplan(input_plan_path: str, output_plan_path: str, faults_dict: dict):
    if not os.path.exists(input_plan_path):
        raise FileNotFoundError(f"Input RT Plan file not found: {input_plan_path}")

    dcm = pydicom.dcmread(input_plan_path)
    
    stuck_leaves = faults_dict.get("stuck_leaves", {})
    cal_offsets = faults_dict.get("calibration_offsets", {})
    bank_sx1_offset = float(faults_dict.get("bank_calibration_offset_sx1", 0.0))
    bank_sx2_offset = float(faults_dict.get("bank_calibration_offset_sx2", 0.0))

    if hasattr(dcm, "BeamSequence"):
        for beam in dcm.BeamSequence:
            if hasattr(beam, "ControlPointSequence"):
                for cp in beam.ControlPointSequence:
                    if hasattr(cp, "BeamLimitingDevicePositionSequence"):
                        for bld in cp.BeamLimitingDevicePositionSequence:
                            if hasattr(bld, "LeafPositionBoundaries") or hasattr(bld, "LeafJawPositions"):
                                pos_list = list(bld.LeafJawPositions)
                                num_pos = len(pos_list)
                                half_pos = num_pos // 2
                                
                                for idx in range(num_pos):
                                    track_i = (idx % half_pos) + 1
                                    bank_offset = bank_sx1_offset if (track_i % 2 != 0) else bank_sx2_offset
                                    indiv_offset = float(cal_offsets.get(track_i, cal_offsets.get(str(track_i), 0.0)))
                                    
                                    pos_list[idx] += (bank_offset + indiv_offset)
                                    
                                    if track_i in stuck_leaves or str(track_i) in stuck_leaves:
                                        fixed_val = float(stuck_leaves.get(track_i, stuck_leaves.get(str(track_i))))
                                        pos_list[idx] = fixed_val
                                        
                                bld.LeafJawPositions = pos_list

    dcm.save_as(output_plan_path)
    return output_plan_path