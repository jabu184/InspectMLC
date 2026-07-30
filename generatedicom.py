import datetime
import numpy as np
from scipy.ndimage import gaussian_filter
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

def create_synthetic_halcyon_mv_image(
    output_filename="halcyon_picket_fence_g90.dcm",
    gantry_angle=90.0,
    simulate_gravitational_sag=True,
    stuck_leaf_index=14
):
    """
    Generates a synthetic RTIMAGE DICOM simulating a Halcyon Picket Fence
    at a specific gantry angle with optional gravitational sag & MLC faults.
    """
    # -------------------------------------------------------------------------
    # 1. EPID & Image Geometry Setup (Varian Halcyon EPID specs)
    # -------------------------------------------------------------------------
    pixel_spacing = 0.384  # mm/pixel at ISOCENTER (1000mm SAD)
    image_dim = 1024       # 1024x1024 pixel matrix
    field_size_mm = image_dim * pixel_spacing # ~393 mm
    
    # Grid in mm relative to beam axis (0,0 at CAX)
    x = (np.arange(image_dim) - image_dim / 2.0) * pixel_spacing
    y = (np.arange(image_dim) - image_dim / 2.0) * pixel_spacing
    xx, yy = np.meshgrid(x, y)

    # -------------------------------------------------------------------------
    # 2. Build Base Field Transmission (Picket Fence Gaps)
    # -------------------------------------------------------------------------
    # Background transmission through closed double-layer MLC (~0.5%)
    base_transmission = 0.005
    pixel_array = np.full((image_dim, image_dim), base_transmission, dtype=np.float32)

    # Standard Picket Fence gaps (e.g., 5 pickets spaced 50 mm apart)
    picket_centers = [-100.0, -50.0, 0.0, 50.0, 100.0]  # mm
    picket_width = 15.0  # mm wide opening per picket

    # Halcyon SX2 MLC: 28 leaf pairs (width ~10mm at iso) across Y [-140mm to +140mm]
    num_leaf_pairs = 28
    leaf_pitch_mm = 10.0
    y_min_mlc = -140.0

    # Simulate EPID flex (sag of panel at lateral angles)
    epid_panel_flex_x = 0.4 if gantry_angle in [90.0, 270.0] else 0.0

    for leaf_idx in range(num_leaf_pairs):
        # Y-boundaries for this leaf row
        y1 = y_min_mlc + leaf_idx * leaf_pitch_mm
        y2 = y1 + leaf_pitch_mm
        in_leaf_row = (yy >= y1) & (yy < y2)

        # Distinguish Proximal (even) vs Distal (odd) layers for Halcyon transmission
        is_proximal = (leaf_idx % 2 == 0)
        open_transmission = 1.0 if is_proximal else 0.96 # Slight energy spectral difference

        # Apply Gravitational Shift if gantry is horizontal (90° / 270°)
        grav_shift = 0.0
        if simulate_gravitational_sag and gantry_angle in [90.0, 270.0]:
            # Apply ~0.6mm sag towards gravity direction
            direction = 1.0 if gantry_angle == 90.0 else -1.0
            grav_shift = 0.6 * direction

        # Apply specific MLC Fault (e.g., Stuck Leaf)
        fault_offset = 0.0
        if leaf_idx == stuck_leaf_index:
            fault_offset = -3.5  # 3.5mm offset on stuck leaf

        total_x_shift = grav_shift + fault_offset + epid_panel_flex_x

        # Create pickets along this leaf row
        for center in picket_centers:
            x_left = (center - picket_width / 2.0) + total_x_shift
            x_right = (center + picket_width / 2.0) + total_x_shift
            
            in_picket_gap = (xx >= x_left) & (xx <= x_right)
            pixel_array[in_leaf_row & in_picket_gap] = open_transmission

    # -------------------------------------------------------------------------
    # 3. Realistic Physics Blur (Penumbra) & Noise Injection
    # -------------------------------------------------------------------------
    # Apply Gaussian blur to simulate radiation penumbra (FWHM ~3-4mm)
    sigma_pixels = (3.0 / 2.355) / pixel_spacing
    pixel_array = gaussian_filter(pixel_array, sigma=sigma_pixels)

    # Convert to 16-bit raw pixel values (EPID Digital Counts)
    counts_scale = 30000.0
    raw_counts = (pixel_array * counts_scale).astype(np.uint16)

    # Add Gaussian EPID detector noise
    noise = np.random.normal(0, 150, raw_counts.shape)
    raw_counts = np.clip(raw_counts + noise, 0, 65535).astype(np.uint16)

    # -------------------------------------------------------------------------
    # 4. Construct DICOM Dataset Structure (RTIMAGE)
    # -------------------------------------------------------------------------
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.481.1' # RTIMAGE
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.ImplementationClassUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(output_filename, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    # DICOM Patient / Study / Series Module
    ds.PatientName = "Halcyon^Simulated^QC"
    ds.PatientID = "HALCYON_QC_001"
    ds.Modality = "RTIMAGE"
    ds.Manufacturer = "Varian Medical Systems"
    ds.ManufacturerModelName = "Halcyon"
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID

    # Image Plane Module Attributes
    ds.ImageType = ["ORIGINAL", "PRIMARY", "PORTAL"]
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = image_dim
    ds.Columns = image_dim
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelSpacing = [str(pixel_spacing), str(pixel_spacing)]
    ds.RTImagePosition = [str(-field_size_mm / 2.0), str(-field_size_mm / 2.0)]
    ds.RadiationMachineSAD = "1000.0"
    ds.RadiationMachineSAD = "1000.0"
    ds.RTImageSID = "1500.0"

    # Beam / Geometry Module Attributes
    ds.GantryAngle = str(gantry_angle)
    ds.BeamLimitingDeviceAngle = "0.0"
    ds.PatientSupportAngle = "0.0"

    # Set Pixel Data
    ds.PixelData = raw_counts.tobytes()

    # Save
    ds.save_as(output_filename)
    print(f"Successfully generated: {output_filename} (Gantry: {gantry_angle}°)")

if __name__ == "__main__":
    # Generate Neutral baseline (0°) and Gravity-affected (90°) test DICOMs
    create_synthetic_halcyon_mv_image("halcyon_pf_gantry0.dcm", gantry_angle=0.0)
    create_synthetic_halcyon_mv_image("halcyon_pf_gantry90.dcm", gantry_angle=90.0)