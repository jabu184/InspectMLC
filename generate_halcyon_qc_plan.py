import datetime
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

def create_halcyon_gravity_5mm_plan(output_filename="Gravity_5mm_Match.dcm"):
    """
    Generates a DICOM RTPlan file matching the clinical 'Gravity 5mm' Varian Halcyon 
    plan structure, including static open beams and dynamic 5mm/10mm differential 
    passes for Proximal and Distal MLC banks across 0, 90, 180, and 270 degrees.
    """
    # -------------------------------------------------------------------------
    # 1. File Meta & Dataset Setup
    # -------------------------------------------------------------------------
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.481.5'  # RT Plan
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.ImplementationClassUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(output_filename, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    # DICOM Patient / Plan Header
    ds.PatientName = "Halcyon^QC^Gravity"
    ds.PatientID = "HALCYON_GRAVITY_5MM"
    ds.Modality = "RTPLAN"
    ds.Manufacturer = "Varian Medical Systems"
    ds.ManufacturerModelName = "Halcyon"
    ds.RTPlanLabel = "Gravity 5mm"
    ds.RTPlanName = "Gravity 5mm"
    ds.RTPlanGeometry = "PATIENT"

    now = datetime.datetime.now()
    ds.RTPlanDate = now.strftime("%Y%m%d")
    ds.RTPlanTime = now.strftime("%H%M%S")

    # Halcyon SX2 Geometry Parameters
    num_proximal_leaves = 28  # MLCX1 (Even indices in sequence)
    num_distal_leaves = 29    # MLCX2 (Odd indices in sequence)
    
    leaf_boundaries_x1 = [float(x) for x in range(-140, 150, 10)]
    leaf_boundaries_x2 = [float(x) for x in range(-145, 155, 10)]

    # Beam Definitions: (BeamNumber, BeamName, BeamType, GantryAngle, MU, ActiveBank)
    beams_to_create = [
        # Gantry 0° Set
        (1, "G0 Open", "STATIC", 0.0, 1.0, "OPEN"),
        (2, "G0 5mm Dist", "DYNAMIC", 0.0, 15.0, "DISTAL"),
        (3, "G0 5mm Prox", "DYNAMIC", 0.0, 15.0, "PROXIMAL"),
        # Gantry 90° Set
        (4, "G90 Open", "STATIC", 90.0, 1.0, "OPEN"),
        (5, "G90 5mm Dist", "DYNAMIC", 90.0, 15.0, "DISTAL"),
        (6, "G90 5mm Prox", "DYNAMIC", 90.0, 15.0, "PROXIMAL"),
        # Gantry 180° Set
        (7, "G180 Open", "STATIC", 180.0, 1.0, "OPEN"),
        (8, "G180 5mm Dist", "DYNAMIC", 180.0, 15.0, "DISTAL"),
        (9, "G180 5mm Prox", "DYNAMIC", 180.0, 15.0, "PROXIMAL"),
        # Gantry 270° Set
        (10, "G270 Open", "STATIC", 270.0, 1.0, "OPEN"),
        (11, "G270 5mm Dist", "DYNAMIC", 270.0, 15.0, "DISTAL"),
        (12, "G270 5mm Prox", "DYNAMIC", 270.0, 15.0, "PROXIMAL"),
    ]

    beam_sequence = []
    fraction_group = Dataset()
    fraction_group.FractionGroupNumber = 1
    fraction_group.NumberOfFractionsPlanned = 1
    fraction_group.NumberOfBeams = len(beams_to_create)
    fraction_group.ReferencedBeamSequence = []

    # -------------------------------------------------------------------------
    # 2. Build Each Beam Sequence
    # -------------------------------------------------------------------------
    for b_num, b_name, b_type, g_angle, mu, bank in beams_to_create:
        beam = Dataset()
        beam.BeamNumber = b_num
        beam.BeamName = b_name
        beam.BeamType = b_type
        beam.RadiationType = "PHOTON"
        beam.TreatmentMachineName = "Halcyon"
        beam.PrimaryDosimeterUnit = "MU"
        beam.SourceAxisDistance = 1000.0

        # MLC Device Definitions
        mlc_x1 = Dataset()
        mlc_x1.RTBeamLimitingDeviceType = "MLCX1"
        mlc_x1.NumberOfLeafPositionPairs = num_proximal_leaves
        mlc_x1.LeafPositionBoundaries = leaf_boundaries_x1

        mlc_x2 = Dataset()
        mlc_x2.RTBeamLimitingDeviceType = "MLCX2"
        mlc_x2.NumberOfLeafPositionPairs = num_distal_leaves
        mlc_x2.LeafPositionBoundaries = leaf_boundaries_x2

        beam.BeamLimitingDeviceSequence = [mlc_x1, mlc_x2]

        # Build Control Points
        cp_sequence = []

        if b_type == "STATIC":
            # Open Field Calibration Beams
            for cp_idx in [0, 1]:
                cp = Dataset()
                cp.ControlPointIndex = cp_idx
                cp.NominalBeamEnergy = 6.0
                cp.GantryAngle = float(g_angle)
                cp.GantryRotationDirection = "NONE"
                cp.BeamLimitingDeviceAngle = 0.0
                cp.PatientSupportAngle = 0.0
                cp.CumulativeMetersetWeight = float(cp_idx)

                # Open aperture (-75mm to +75mm)
                pos_x1_A = [-75.0] * num_proximal_leaves
                pos_x1_B = [75.0] * num_proximal_leaves
                pos_x2_A = [-75.0] * num_distal_leaves
                pos_x2_B = [75.0] * num_distal_leaves

                mlc_x1_pos = Dataset()
                mlc_x1_pos.RTBeamLimitingDeviceType = "MLCX1"
                mlc_x1_pos.LeafJawPositions = [str(p) for p in (pos_x1_A + pos_x1_B)]

                mlc_x2_pos = Dataset()
                mlc_x2_pos.RTBeamLimitingDeviceType = "MLCX2"
                mlc_x2_pos.LeafJawPositions = [str(p) for p in (pos_x2_A + pos_x2_B)]

                cp.BeamLimitingDevicePositionSequence = [mlc_x1_pos, mlc_x2_pos]
                cp_sequence.append(cp)

        else:  # DYNAMIC SWEEPING SLIT BEAMS
            # Picket positions for sweeping window (-70mm to +70mm across field)
            positions = [
                (-70.0, -60.0, -69.0, -64.0),  # CP 0
                (-40.0, -30.0, -39.0, -34.0),  # CP 1
                (-10.0,  0.0,  -9.0,  -4.0),  # CP 2
                ( 20.0, 30.0,   21.0,  26.0),  # CP 3
                ( 50.0, 60.0,   51.0,  56.0),  # CP 4
            ]
            num_cps = len(positions)

            for cp_idx, (p_left, p_right, d_left, d_right) in enumerate(positions):
                cp = Dataset()
                cp.ControlPointIndex = cp_idx
                cp.NominalBeamEnergy = 6.0
                cp.GantryAngle = float(g_angle)
                cp.GantryRotationDirection = "NONE"
                cp.BeamLimitingDeviceAngle = 0.0
                cp.PatientSupportAngle = 0.0
                cp.CumulativeMetersetWeight = float(cp_idx) / float(num_cps - 1)

                if bank == "DISTAL":
                    # Distal forms inner 5mm slit, Proximal forms outer 10mm roof
                    x1_A, x1_B = p_left, p_right
                    x2_A, x2_B = d_left, d_right
                else:  # PROXIMAL
                    # Proximal forms inner 5mm slit, Distal forms outer 10mm roof
                    x1_A, x1_B = d_left, d_right
                    x2_A, x2_B = p_left, p_right

                mlc_x1_pos = Dataset()
                mlc_x1_pos.RTBeamLimitingDeviceType = "MLCX1"
                mlc_x1_pos.LeafJawPositions = [str(x1_A)] * num_proximal_leaves + [str(x1_B)] * num_proximal_leaves

                mlc_x2_pos = Dataset()
                mlc_x2_pos.RTBeamLimitingDeviceType = "MLCX2"
                mlc_x2_pos.LeafJawPositions = [str(x2_A)] * num_distal_leaves + [str(x2_B)] * num_distal_leaves

                cp.BeamLimitingDevicePositionSequence = [mlc_x1_pos, mlc_x2_pos]
                cp_sequence.append(cp)

        beam.ControlPointSequence = cp_sequence
        beam.NumberOfControlPoints = len(cp_sequence)
        beam.FinalMetersetWeight = float(mu)
        beam_sequence.append(beam)

        # Fraction Group Reference
        ref_beam = Dataset()
        ref_beam.ReferencedBeamNumber = b_num
        ref_beam.BeamMeterset = float(mu)
        fraction_group.ReferencedBeamSequence.append(ref_beam)

    ds.BeamSequence = beam_sequence
    ds.FractionGroupSequence = [fraction_group]

    # Save
    ds.save_as(output_filename)
    print(f"Successfully generated matching plan: {output_filename} ({len(beam_sequence)} Beams)")

if __name__ == "__main__":
    create_halcyon_gravity_5mm_plan()