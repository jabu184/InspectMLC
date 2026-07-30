import pydicom

def modify_existing_halcyon_plan(
    input_filename="HAL6 Gravity 5mm.dcm", 
    output_filename="HAL6_Gravity_5mm_1mmOffset_Sweeping.dcm"
):
    """
    Loads an existing, valid Halcyon DICOM RTPlan and modifies the leaf 
    positions of the dynamic beams to perform a continuous 5mm sweeping slit 
    with a 1mm secondary bank offset, while preserving all ARIA database tags, 
    Accession Numbers, Machine IDs, and SOP links.
    """
    # 1. Load the valid clinical DICOM plan
    ds = pydicom.dcmread(input_filename)
    print(f"Loaded reference plan: {ds.RTPlanLabel} for Patient ID: {ds.PatientID}")

    # Halcyon SX2 Leaf Pair Counts
    num_proximal_leaves = 28  # MLCX1
    num_distal_leaves = 29    # MLCX2

    # Continuous Sweeping Slit Control Point Positions:
    # 5mm Active Slit: Start (-17.5mm, -12.5mm) -> End (+12.5mm, +17.5mm)
    # 7mm Secondary Window: Start (-18.5mm, -11.5mm) -> End (+11.5mm, +18.5mm)
    cp_positions = [
        # (CP_Index, Weight, 5mm_A, 5mm_B, 7mm_A, 7mm_B)
        (0, "0", "-17.5", "-12.5", "-18.5", "-11.5"),
        (1, "1", "12.5", "17.5", "11.5", "18.5")
    ]

    # 2. Iterate through beams and update dynamic MLC positions
    for beam in ds.BeamSequence:
        b_name = getattr(beam, "BeamName", "")
        b_type = getattr(beam, "BeamType", "")

        # Skip Static Open Field beams (e.g., G0 Open, G90 Open)
        if b_type == "STATIC" or "Open" in b_name:
            print(f"Skipping static calibration beam: {b_name}")
            continue

        # Determine if this beam tests the DISTAL or PROXIMAL layer
        is_distal_test = "Dist" in b_name
        is_proximal_test = "Prox" in b_name

        if not (is_distal_test or is_proximal_test):
            print(f"Skipping unrecognized beam: {b_name}")
            continue

        # Reconstruct ControlPointSequence to have 2 continuous sweeping CPs
        # (Preserving base CP structure attributes like Gantry Angle and Energy)
        base_cp0 = beam.ControlPointSequence[0]
        base_cp1 = beam.ControlPointSequence[-1]

        # Ensure Meterset weights are set for a 2-point sweep
        base_cp0.CumulativeMetersetWeight = "0"
        base_cp1.CumulativeMetersetWeight = "1"
        
        beam.ControlPointSequence = pydicom.sequence.Sequence([base_cp0, base_cp1])
        beam.NumberOfControlPoints = 2

        for cp, (cp_idx, weight, s_left, s_right, o_left, o_right) in zip(beam.ControlPointSequence, cp_positions):
            cp.ControlPointIndex = cp_idx
            cp.CumulativeMetersetWeight = weight

            if is_distal_test:
                # Distal (MLCX2) gets 5mm test gap
                # Proximal (MLCX1) gets 7mm window (offset 1mm wider per side)
                x1_A, x1_B = o_left, o_right
                x2_A, x2_B = s_left, s_right
            else:  # Proximal Test
                # Proximal (MLCX1) gets 5mm test gap
                # Distal (MLCX2) gets 7mm window (offset 1mm wider per side)
                x1_A, x1_B = s_left, s_right
                x2_A, x2_B = o_left, o_right

            # Update MLCX1 (Proximal) and MLCX2 (Distal) leaf position arrays
            for bld in cp.BeamLimitingDevicePositionSequence:
                dev_type = bld.RTBeamLimitingDeviceType
                
                if dev_type == "MLCX1":
                    bld.LeafJawPositions = [x1_A] * num_proximal_leaves + [x1_B] * num_proximal_leaves
                elif dev_type == "MLCX2":
                    bld.LeafJawPositions = [x2_A] * num_distal_leaves + [x2_B] * num_distal_leaves

        print(f"Updated dynamic sweeping positions for beam: {b_name}")

    # 3. Update Plan Label to reflect modifications
    ds.RTPlanLabel = "Grav_5mm_Sweep"
    ds.RTPlanName = "Gravity 5mm Sweeping 1mm"

    # Save modified dataset
    ds.save_as(output_filename)
    print(f"\nSuccessfully saved Eclipse-ready modified plan: {output_filename}")

if __name__ == "__main__":
    modify_existing_halcyon_plan()