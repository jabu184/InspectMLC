import os
import io
import base64
import numpy as np
from PIL import Image
import pydicom

def load_dicom_or_image(file_path: str):
    """
    Loads a DICOM RTIMAGE file or standard image file.
    Safely handles non-image DICOM files (e.g. RTPLAN, RTSTRUCT).
    Extracts GantryAngle, PixelSpacing, SAD, and generates base64 preview PNG.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    metadata = {
        "filename": os.path.basename(file_path),
        "modality": "RTIMAGE",
        "manufacturer": "Varian Medical Systems",
        "model": "Halcyon",
        "station_name": "HAL7",
        "label": os.path.basename(file_path),
        "gantry_angle": 0.0,
        "collimator_angle": 0.0,
        "sad_mm": 1000.0,
        "columns": 1280,
        "rows": 1280,
        "pixel_spacing_x": 0.336,
        "pixel_spacing_y": 0.336,
    }

    pixel_array = None

    try:
        dcm = pydicom.dcmread(file_path)
        metadata["modality"] = str(getattr(dcm, "Modality", "RTIMAGE"))
        metadata["manufacturer"] = str(getattr(dcm, "Manufacturer", "Varian Medical Systems"))
        metadata["model"] = str(getattr(dcm, "ManufacturerModelName", "Halcyon"))
        metadata["station_name"] = str(getattr(dcm, "StationName", "HAL7"))
        metadata["label"] = str(getattr(dcm, "RTImageLabel", os.path.basename(file_path)))

        if hasattr(dcm, "GantryAngle"):
            metadata["gantry_angle"] = float(dcm.GantryAngle)
        if hasattr(dcm, "BeamLimitingDeviceAngle"):
            metadata["collimator_angle"] = float(dcm.BeamLimitingDeviceAngle)
        if hasattr(dcm, "RadiationMachineSAD"):
            metadata["sad_mm"] = float(dcm.RadiationMachineSAD)

        ps = getattr(dcm, "PixelSpacing", getattr(dcm, "ImagePlanePixelSpacing", [0.336, 0.336]))
        if len(ps) >= 2:
            metadata["pixel_spacing_y"] = float(ps[0])
            metadata["pixel_spacing_x"] = float(ps[1])

        if hasattr(dcm, "pixel_array"):
            pixel_array = dcm.pixel_array.astype(np.float32)
            metadata["rows"], metadata["columns"] = pixel_array.shape[0], pixel_array.shape[1]
    except Exception:
        pass

    if pixel_array is None:
        try:
            img = Image.open(file_path).convert("L")
            pixel_array = np.array(img, dtype=np.float32)
            metadata["rows"], metadata["columns"] = pixel_array.shape[0], pixel_array.shape[1]
            metadata["modality"] = "IMAGE"
            metadata["label"] = os.path.basename(file_path)
        except Exception:
            # Fallback 512x512 matrix for non-image files (e.g. RT PLAN)
            pixel_array = np.full((512, 512), 1000.0, dtype=np.float32)
            metadata["rows"], metadata["columns"] = 512, 512
            metadata["label"] = f"Non-Image File ({os.path.basename(file_path)})"

    metadata["min_val"] = float(pixel_array.min())
    metadata["max_val"] = float(pixel_array.max())
    metadata["mean_val"] = float(pixel_array.mean())

    p_min, p_max = np.percentile(pixel_array, 1), np.percentile(pixel_array, 99)
    if p_max <= p_min:
        p_min, p_max = pixel_array.min(), pixel_array.max()
    if p_max <= p_min:
        p_max = p_min + 1.0

    norm_arr = np.clip((pixel_array - p_min) / (p_max - p_min) * 255.0, 0, 255).astype(np.uint8)
    pil_img = Image.fromarray(norm_arr)
    
    buffered = io.BytesIO()
    pil_img.save(buffered, format="PNG")
    b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    preview_data_url = f"data:image/png;base64,{b64_str}"

    return {
        "pixel_array": pixel_array,
        "metadata": metadata,
        "preview_png_b64": preview_data_url
    }
