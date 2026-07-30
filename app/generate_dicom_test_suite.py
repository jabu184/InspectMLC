import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from app.simulator import generate_synthetic_mlc_image, save_synthetic_dicom_rtimage

def generate_sample_rtplan(output_path: str):
    """
    Generates a valid DICOM RT Plan (RTPLAN) file for Varian Halcyon dual-layer MLC QA testing.
    Includes 4 gantry control points (0°, 90°, 180°, 270°) with Proximal (SX1) and Distal (SX2) leaf positions.
    """
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = pydicom.uid.RTPlanStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(output_path, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.SOPClassUID = pydicom.uid.RTPlanStorage
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = "RTPLAN"
    ds.Manufacturer = "Varian Medical Systems"
    ds.ManufacturerModelName = "Halcyon - PVA"
    ds.StationName = "HAL7_2024"
    ds.RTPlanLabel = "HAL_SAG_QC"
    ds.RTPlanName = "HALCYON_SAG_TEST"
    ds.RTPlanGeometry = "PATIENT"

    ds.PatientName = "Halcyon^QC^Test"
    ds.PatientID = "HAL7-QC-001"
    ds.PatientSex = "O"

    ds.FrameOfReferenceUID = generate_uid()
    ds.PositionReferenceIndicator = ""

    beam = Dataset()
    beam.BeamNumber = 1
    beam.BeamName = "HAL_SAG_4ANGLE"
    beam.BeamType = "STATIC"
    beam.RadiationType = "PHOTON"
    beam.TreatmentMachineName = "HAL7_2024"
    beam.Manufacturer = "Varian"
    beam.PrimaryDosimeterUnit = "MU"
    beam.SourceAxisDistance = 1000.0

    num_pairs = 28
    leaf_boundaries = [float(-140.0 + i * 10.0) for i in range(num_pairs + 1)]
    
    bld_spec = Dataset()
    bld_spec.RTBeamLimitingDeviceType = "MLCX"
    bld_spec.NumberOfLeafPositionPairs = num_pairs
    bld_spec.LeafPositionBoundaries = leaf_boundaries
    beam.BeamLimitingDeviceSequence = Sequence([bld_spec])

    angles = [0.0, 90.0, 180.0, 270.0]
    cp_seq = []

    for idx, angle in enumerate(angles):
        cp = Dataset()
        cp.ControlPointIndex = idx
        cp.NominalBeamEnergy = 6.0
        cp.GantryAngle = float(angle)
        cp.GantryRotationDirection = "NONE"
        cp.BeamLimitingDeviceAngle = 0.0
        cp.PatientSupportAngle = 0.0
        cp.TableTopVerticalPosition = 0.0
        cp.TableTopLongitudinalPosition = 0.0
        cp.TableTopLateralPosition = 0.0
        cp.IsocenterPosition = [0.0, 0.0, 0.0]

        sag_shift = 1.2 * np.sin(np.radians(angle))
        
        bank_a = [float(-100.0 + sag_shift) for _ in range(num_pairs)]
        bank_b = [float(100.0 + sag_shift) for _ in range(num_pairs)]

        bank_a[9] = 15.0
        bank_b[9] = 35.0

        bank_a[14] += 0.8
        bank_b[14] += 0.8

        bld_pos = Dataset()
        bld_pos.RTBeamLimitingDeviceType = "MLCX"
        bld_pos.LeafJawPositions = bank_a + bank_b

        cp.BeamLimitingDevicePositionSequence = Sequence([bld_pos])
        cp_seq.append(cp)

    beam.ControlPointSequence = Sequence(cp_seq)
    ds.BeamSequence = Sequence([beam])

    ds.save_as(output_path)
    print(f"Generated synthetic DICOM RT Plan: {output_path}")
    return output_path


def generate_full_test_suite():
    """
    Generates complete DICOM RT Plan (.dcm) and 4-angle DICOM RT Image series (.dcm)
    into sample_data/ directory.
    """
    sample_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
    os.makedirs(sample_dir, exist_ok=True)

    # 1. Generate RT Plan
    plan_path = os.path.join(sample_dir, "halcyon_sag_qc_plan.dcm")
    generate_sample_rtplan(plan_path)

    # 2. Generate 4-Angle RTIMAGE Series (0°, 90°, 180°, 270°)
    angles = [0.0, 90.0, 180.0, 270.0]
    faults = {
        "sag_amplitude_mm": 1.2,
        "stuck_leaves": {10: 25.0},
        "calibration_offsets": {15: 0.8},
        "gaussian_noise_std": 200.0
    }

    generated_rtimages = []
    for angle in angles:
        arr = generate_synthetic_mlc_image(
            gantry_angle=angle,
            pattern_type="picket_fence",
            faults_dict=faults
        )
        fname = f"halcyon_gantry_{int(angle)}deg.dcm"
        fpath = os.path.join(sample_dir, fname)
        save_synthetic_dicom_rtimage(arr, fpath, gantry_angle=angle, label=f"HAL_GANTRY_{int(angle)}")
        generated_rtimages.append(fpath)

    print(f"Generated {len(generated_rtimages)} DICOM RTIMAGE test files in: {sample_dir}")
    return plan_path, generated_rtimages


if __name__ == "__main__":
    generate_full_test_suite()
