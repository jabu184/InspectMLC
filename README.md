# InspectMLC - Multi-Platform Linac & MLC Delivery Quality Assurance Tool

InspectMLC is an advanced, automated Quality Assurance (QA) and Analysis software suite designed for medical physics and radiation oncology teams. It provides high-precision ML&C leaf position analysis, EPID delivery verification, geometric sag shift quantification, and real-time DICOM folder monitoring across Varian Halcyon (Dual-Layer SX1/SX2) and TrueBeam (Millennium 120) Linear Accelerators.

---

## 🎯 Key Features

- **Multi-Platform Support**:
  - **Varian Halcyon Dual-Layer SX2**: 114 leaves (SX1 Proximal & SX2 Distal banks).
  - **Varian TrueBeam Millennium 120**: 120 leaves (60 leaf pairs).
- **Automated EPID & DICOM Analysis**:
  - EPID image normalization, magnification correction, and leaf position calibration.
  - Per-leaf sag shift amplitude tracking across cardinal gantry angles (0°, 90°, 180°, 270°).
  - Picket Fence & Dosimetric Fluence Comparison engine.
- **Real-Time DICOM Directory Watcher**:
  - Live directory monitoring with automatic field classification and completeness checking.
  - Interactive expected field checklist with readiness gating before running analysis.
- **QATrack+ REST API Integration**:
  - Direct integration with QATrack+ for pushing QA metrics (`sag_max_mm`, `pass_rate_pct`, `dlg_0deg_mm`, `max_fluence_delta_pct`, `qc_status`).
- **Standalone Portable Build**:
  - Single standalone Windows desktop app bundle (`InspectMLC.exe`) requiring zero installation or Python environment setup.

---

## 🚀 Getting Started

### Running from Source
1. **Clone the repository**:
   ```bash
   git clone https://github.com/jabu184/InspectMLC.git
   cd InspectMLC
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch Application**:
   ```bash
   python run.py
   ```
   The application will automatically start the FastAPI server on `http://127.0.0.1:8522` and launch a native desktop GUI window.

---

## 📦 Building Standalone Executable

To build the portable Windows application:
```bash
python -m PyInstaller --clean InspectMLC.spec
```
The compiled output will be generated in `dist/InspectMLC/InspectMLC.exe`.

---

## ⚙️ Requirements
- Python 3.10+
- `fastapi`, `uvicorn`, `pydicom`, `scipy`, `numpy`, `pillow`, `matplotlib`, `pywebview`

---

## 📄 License
MIT License
