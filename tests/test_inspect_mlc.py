import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import sys
import unittest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.dicom_loader import load_dicom_or_image
from app.comparator import compare_deliveries

class TestInspectMLC(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.img1_path = os.path.join(self.root_dir, "image1.dcm")
        self.img2_path = os.path.join(self.root_dir, "image2.dcm")

    def test_health(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_sample_images(self):
        res = self.client.get("/api/sample-images")
        self.assertEqual(res.status_code, 200)
        files = res.json()["sample_files"]
        filenames = [f["filename"] for f in files]
        self.assertIn("image1.dcm", filenames)
        self.assertIn("image2.dcm", filenames)

    def test_dicom_loader(self):
        res1 = load_dicom_or_image(self.img1_path)
        self.assertEqual(res1["metadata"]["modality"], "RTIMAGE")
        self.assertEqual(res1["metadata"]["rows"], 1280)
        self.assertEqual(res1["metadata"]["columns"], 1280)
        self.assertIn("data:image/png;base64,", res1["preview_png_b64"])

    def test_mlc_comparison_api(self):
        res = self.client.post("/api/compare-mlc", json={
            "file_a": self.img1_path,
            "file_b": self.img2_path,
            "warn_thresh_mm": 0.5,
            "fail_thresh_mm": 1.0,
            "enable_registration": True
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        summary = data["summary"]
        self.assertGreater(summary["total_leaves_analyzed"], 0)
        self.assertGreater(summary["pass_rate_pct"], 0)
        self.assertEqual(len(data["leaf_results"]), 56)

    def test_leaf_profile_api(self):
        self.client.post("/api/compare-mlc", json={
            "file_a": self.img1_path,
            "file_b": self.img2_path
        })
        res = self.client.get("/api/leaf-profile/10")
        self.assertEqual(res.status_code, 200)
        prof = res.json()
        self.assertEqual(prof["track_index"], 10)
        self.assertEqual(len(prof["profile_a"]), 1280)
        self.assertEqual(len(prof["profile_b"]), 1280)

if __name__ == "__main__":
    unittest.main()
