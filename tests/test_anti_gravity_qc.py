import unittest
import numpy as np
from app.dicom_parser import parse_dicom_qc_header
from app.panel_analyzer import extract_panel_offset
from app.mlc_analyzer import analyze_leaf_row_dual_metric, analyze_halcyon_triad, analyze_truebeam_pair
from app.gravity_engine import run_anti_gravity_qc_pipeline

class TestAntiGravityQC(unittest.TestCase):

    def test_analyze_leaf_row_dual_metric(self):
        # Create a 1000-pixel profile with a 50-pixel aperture (500 to 550)
        prof = np.full(1000, 1000.0, dtype=np.float32)
        prof[500:550] = 50000.0
        
        res = analyze_leaf_row_dual_metric(prof, pixel_spacing_mm=0.336)
        self.assertIsNotNone(res["x_raw_mm"])
        self.assertAlmostEqual(res["x_raw_px"], 524.5, delta=1.0)
        self.assertGreater(res["auc_fluence"], 0)

    def test_extract_panel_offset(self):
        # Create an open field profile shifted by +5 pixels
        img = np.full((100, 100), 1000.0, dtype=np.float32)
        img[20:80, 25:85] = 50000.0  # Center is at 55 (ideal is 50)
        
        res = extract_panel_offset(img, dx=0.336, dy=0.336)
        self.assertAlmostEqual(res["delta_x_panel_px"], 5.0, delta=1.5)
        self.assertAlmostEqual(res["delta_x_panel_mm"], 5.0 * 0.336, delta=0.5)

    def test_halcyon_triad_pipeline(self):
        open_img = np.full((1280, 1280), 5000.0, dtype=np.float32)
        open_img[200:1080, 200:1080] = 50000.0
        
        picket_img = np.full((1280, 1280), 5000.0, dtype=np.float32)
        picket_img[200:1080, 500:780] = 45000.0
        
        triad = analyze_halcyon_triad(picket_img, picket_img, open_img, gantry_angle=0.0)
        self.assertEqual(triad["total_tracks"], 57)
        self.assertEqual(triad["total_leaves"], 114)

    def test_truebeam_pair_pipeline(self):
        open_img = np.full((1280, 1280), 5000.0, dtype=np.float32)
        open_img[200:1080, 200:1080] = 50000.0
        
        mlc_img = np.full((1280, 1280), 5000.0, dtype=np.float32)
        mlc_img[200:1080, 600:680] = 45000.0
        
        pair = analyze_truebeam_pair(mlc_img, open_img, gantry_angle=0.0)
        self.assertEqual(pair["total_tracks"], 60)
        self.assertEqual(pair["total_leaves"], 120)

    def test_run_anti_gravity_qc_pipeline(self):
        open_img = np.full((1280, 1280), 5000.0, dtype=np.float32)
        open_img[200:1080, 200:1080] = 50000.0
        
        picket_img = np.full((1280, 1280), 5000.0, dtype=np.float32)
        picket_img[200:1080, 500:780] = 45000.0

        cardinals = [
            {"gantry_angle": 0.0, "open_field": open_img, "distal_field": picket_img, "proximal_field": picket_img},
            {"gantry_angle": 90.0, "open_field": open_img, "distal_field": picket_img, "proximal_field": picket_img},
            {"gantry_angle": 180.0, "open_field": open_img, "distal_field": picket_img, "proximal_field": picket_img},
            {"gantry_angle": 270.0, "open_field": open_img, "distal_field": picket_img, "proximal_field": picket_img}
        ]

        res = run_anti_gravity_qc_pipeline(cardinals, machine_type="HALCYON")
        self.assertEqual(res["summary"]["pass_rate_pct"], 100.0)
        self.assertEqual(len(res["combined_metrics"]), 57)

if __name__ == "__main__":
    unittest.main()
