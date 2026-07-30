import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import sys
import numpy as np
import unittest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.analysis_engine import fit_subpixel_edge_fast, fit_leaf_edges_track, correct_epid_flex, calculate_gravity_sag, analyze_gantry_frame
from app.simulator import generate_synthetic_mlc_image, save_synthetic_dicom_rtimage, simulate_plan_fluence_map

class TestSagSimulator(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.sample_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
        os.makedirs(self.sample_dir, exist_ok=True)
        self.plan_path = os.path.join(self.sample_dir, "halcyon_sag_qc_plan.dcm")

    def test_subpixel_precision(self):
        dx = 0.336  # mm/px
        cols = 1280
        iso_x = 640.0
        
        gt_x0 = 500.35
        x_pts = np.arange(cols)
        profile = np.full(cols, 5000.0, dtype=np.float32)
        profile[x_pts >= gt_x0] = 55000.0
        
        w_start = 490
        w_end = 510
        fitted_x0 = fit_subpixel_edge_fast(profile[w_start:w_end], np.arange(w_start, w_end), is_rising=True)
        
        err_px = abs(fitted_x0 - gt_x0)
        err_mm = err_px * dx
        print(f"Sub-pixel fitting error: {err_px:.4f} px ({err_mm:.4f} mm)")
        self.assertLessEqual(err_mm, 0.1)

    def test_simulator_and_sag_recovery(self):
        dx, dy = 0.336, 0.336
        injected_sag_mm = 1.5

        arr_0 = generate_synthetic_mlc_image(gantry_angle=0.0, pattern_type="picket_fence", faults_dict={"sag_amplitude_mm": injected_sag_mm})
        frame_0 = analyze_gantry_frame(arr_0, gantry_angle=0.0, dx=dx, dy=dy, apply_flex_correction=False)

        arr_90 = generate_synthetic_mlc_image(gantry_angle=90.0, pattern_type="picket_fence", faults_dict={"sag_amplitude_mm": injected_sag_mm})
        frame_90 = analyze_gantry_frame(arr_90, gantry_angle=90.0, dx=dx, dy=dy, apply_flex_correction=False)

        arr_270 = generate_synthetic_mlc_image(gantry_angle=270.0, pattern_type="picket_fence", faults_dict={"sag_amplitude_mm": injected_sag_mm})
        frame_270 = analyze_gantry_frame(arr_270, gantry_angle=270.0, dx=dx, dy=dy, apply_flex_correction=False)

        results = calculate_gravity_sag([frame_0, frame_90, frame_270])
        summary = results["summary"]

        recovered_max_sag = summary["max_sag_amplitude_mm"]
        print(f"Injected Sag: {injected_sag_mm} mm | Recovered Max Sag: {recovered_max_sag} mm")
        
        self.assertAlmostEqual(recovered_max_sag, injected_sag_mm, delta=0.20)
        self.assertEqual(summary["fail_count"], 56)

    def test_demo_series_api(self):
        res = self.client.post("/api/generate-demo-series")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(len(data["files"]), 4)

    def test_simulate_plan_fluence_api(self):
        res = self.client.post("/api/simulate-plan-fluence", json={
            "plan_path": self.plan_path,
            "beam_number": 1,
            "focal_spot_sigma": 2.5,
            "leaf_transmission": 0.018
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("data:image/png;base64,", data["preview_png_b64"])
        self.assertTrue(os.path.exists(data["dicom_rtimage_path"]))

if __name__ == "__main__":
    unittest.main()
