import os
import io
import base64
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import random
import json
import urllib.request
import urllib.error
from datetime import datetime
import numpy as np
import pydicom
from PIL import Image

from app.dicom_loader import load_dicom_or_image
from app.dicom_parser import parse_dicom_qc_header
from app.analysis_engine import analyze_gantry_frame, calculate_gravity_sag
from app.comparator import compare_deliveries
from app.simulator import generate_synthetic_mlc_image, save_synthetic_dicom_rtimage, simulate_plan_fluence_map
from app.qc_report import generate_qc_report
from app.gravity_engine import run_anti_gravity_qc_pipeline

logger = logging.getLogger("inspect_mlc")

class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app = FastAPI(title="Anti-Gravity QC API", version="3.1")
app.add_middleware(NoCacheStaticMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import sys

def get_base_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

base_dir = get_base_dir()

static_dir = os.path.join(base_dir, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

if getattr(sys, 'frozen', False):
    user_appdata = os.path.join(os.path.expanduser("~"), ".inspect_mlc")
    sample_dir = os.path.join(user_appdata, "sample_data")
else:
    sample_dir = os.path.join(base_dir, "sample_data")

temp_upload_dir = os.path.join(sample_dir, "temp_uploads")
os.makedirs(temp_upload_dir, exist_ok=True)

current_data: Dict[str, Any] = {
    "image_a": None,
    "image_b": None,
    "last_simulated_fluence": None
}

def normalize_path(p: str) -> str:
    if not p:
        return ""
    return os.path.abspath(p).replace("\\", "/")

def get_app_version() -> str:
    root_dir = get_base_dir()
    v_file = os.path.join(root_dir, "version.txt")
    base_version = "v1"
    if os.path.exists(v_file):
        try:
            with open(v_file, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val:
                    base_version = val
        except Exception:
            pass

    build_file = os.path.join(root_dir, "build_version.txt")
    build_num = ""
    if os.path.exists(build_file):
        try:
            with open(build_file, "r", encoding="utf-8") as f:
                build_num = f.read().strip()
        except Exception:
            pass

    if not build_num:
        build_num = str(random.randint(1000, 9999))
        try:
            with open(build_file, "w", encoding="utf-8") as f:
                f.write(build_num)
        except Exception:
            pass

    clean_base = base_version if base_version.startswith("v") else f"v{base_version}"
    return f"{clean_base}.{build_num}"

@app.get("/api/version")
def get_version_endpoint():
    ver = get_app_version()
    return {
        "status": "success",
        "version": ver,
        "base_version": "v1",
        "app_name": "InspectMLC - Multi-Platform Linac & MLC Quality Assurance Suite",
        "build_date": "2026-07-31",
        "supported_linacs": ["Varian Halcyon Dual-Layer SX2 (114 Leaves)", "Varian TrueBeam Millennium 120 (120 Leaves)"]
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "version": get_app_version(),
        "app": "Anti-Gravity QC - TrueBeam GravityTB & Halcyon Multi-Platform Engine",
        "supported_linacs": ["Varian Halcyon Dual-Layer SX2 (114 Leaves)", "Varian TrueBeam Millennium 120 (120 Leaves)"]
    }

@app.get("/api/dicom-file")
def get_dicom_file(file_path: str):
    target_path = normalize_path(file_path)
    if not os.path.exists(target_path):
        root_dir = os.path.dirname(os.path.dirname(__file__))
        alt1 = normalize_path(os.path.join(root_dir, file_path))
        alt2 = normalize_path(os.path.join(sample_dir, os.path.basename(file_path)))
        alt3 = normalize_path(os.path.join(sample_dir, "GravityTB", os.path.basename(file_path)))
        alt4 = normalize_path(os.path.join(root_dir, "Test Images", "Gravity ETHOS", "Normal", os.path.basename(file_path)))
        alt5 = normalize_path(os.path.join(temp_upload_dir, os.path.basename(file_path)))
        if os.path.exists(alt1):
            target_path = alt1
        elif os.path.exists(alt2):
            target_path = alt2
        elif os.path.exists(alt3):
            target_path = alt3
        elif os.path.exists(alt4):
            target_path = alt4
        elif os.path.exists(alt5):
            target_path = alt5
        else:
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    fname = os.path.basename(target_path)
    return FileResponse(path=target_path, filename=fname, media_type="application/dicom")

@app.get("/api/sample-images")
def list_sample_images():
    root_dir = os.path.dirname(os.path.dirname(__file__))
    gravity_tb_dir = os.path.join(sample_dir, "GravityTB")
    ethos_dir = os.path.join(root_dir, "Test Images", "Gravity ETHOS", "Normal")
    files = []
    
    for folder in [root_dir, sample_dir, gravity_tb_dir, ethos_dir, temp_upload_dir]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.lower().endswith(".dcm") or f.lower().endswith(".dicom") or f.startswith("temp_"):
                    full_p = normalize_path(os.path.join(folder, f))
                    if os.path.isfile(full_p):
                        files.append({
                            "filename": f,
                            "path": full_p,
                            "is_temp": folder == temp_upload_dir,
                            "folder": os.path.basename(folder)
                        })
    return {"sample_files": files}

@app.post("/api/upload-field-image")
def upload_field_image_endpoint(file: UploadFile = File(...), target_slot: str = Form("default")):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    clean_filename = os.path.basename(file.filename)
    safe_name = f"temp_{target_slot}_{clean_filename}"
    temp_path = os.path.join(temp_upload_dir, safe_name)

    try:
        file.file.seek(0)
        content = file.file.read()
        with open(temp_path, "wb") as f:
            f.write(content)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to save temporary file '{clean_filename}': {err}")

    norm_path = normalize_path(temp_path)
    gantry_angle = 0.0
    beam_type = "UNKNOWN"
    machine_type = "HALCYON"

    try:
        meta = parse_dicom_qc_header(temp_path)
        gantry_angle = meta["gantry_angle"]
        beam_type = meta["beam_type"]
        machine_type = meta["machine_type"]
    except Exception as parse_err:
        logger.warning(f"Header parsing warning for {clean_filename}: {parse_err}")

    return {
        "status": "success",
        "filename": safe_name,
        "original_filename": clean_filename,
        "saved_path": norm_path,
        "target_slot": target_slot,
        "gantry_angle": gantry_angle,
        "beam_type": beam_type,
        "machine_type": machine_type
    }

@app.post("/api/upload-dicom-series")
def upload_dicom_series_endpoint(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    uploaded_results = []
    errors = []

    for file in files:
        if not file.filename:
            continue
        clean_filename = os.path.basename(file.filename)
        safe_name = f"temp_batch_{clean_filename}"
        temp_path = os.path.join(temp_upload_dir, safe_name)
        
        try:
            file.file.seek(0)
            content = file.file.read()
            with open(temp_path, "wb") as f:
                f.write(content)
        except Exception as write_err:
            errors.append(f"Failed to write {clean_filename}: {write_err}")
            continue

        norm_path = normalize_path(temp_path)
        try:
            meta = parse_dicom_qc_header(temp_path)
            uploaded_results.append({
                "filename": clean_filename,
                "saved_path": norm_path,
                "gantry_angle": meta["gantry_angle"],
                "beam_type": meta["beam_type"],
                "machine_type": meta["machine_type"],
                "target_slot": meta["target_slot"]
            })
        except Exception as parse_err:
            errors.append(f"Header parse warning for {clean_filename}: {parse_err}")
            uploaded_results.append({
                "filename": clean_filename,
                "saved_path": norm_path,
                "gantry_angle": 0.0,
                "beam_type": "UNKNOWN",
                "machine_type": "HALCYON",
                "target_slot": "dist_0"
            })

    return {
        "status": "success",
        "message": f"Smart Auto-Classifier analyzed and mapped {len(uploaded_results)} DICOM image(s) to target fields.",
        "uploaded_files": uploaded_results,
        "errors": errors
    }

class WatchFolderRequest(BaseModel):
    folder_path: str
    machine_type: Optional[str] = "HALCYON"

@app.post("/api/watch-folder")
def watch_folder_endpoint(req: WatchFolderRequest):
    if not req.folder_path:
        raise HTTPException(status_code=400, detail="No folder path provided.")

    target_path = normalize_path(req.folder_path)
    if not os.path.exists(target_path) or not os.path.isdir(target_path):
        root_dir = os.path.dirname(os.path.dirname(__file__))
        alt1 = normalize_path(os.path.join(root_dir, req.folder_path))
        if os.path.exists(alt1) and os.path.isdir(alt1):
            target_path = alt1
        else:
            raise HTTPException(status_code=404, detail=f"Directory not found: '{req.folder_path}'")

    detected_files = []
    mapped_slots = {}
    unmapped_files = []

    try:
        dir_entries = sorted(os.listdir(target_path))
    except Exception as dir_err:
        raise HTTPException(status_code=500, detail=f"Failed to read directory '{target_path}': {dir_err}")

    # Determine pre-selected or expected machine type
    req_machine = (req.machine_type or "HALCYON").upper()

    expected_slots = [
        "dist_0", "dist_90", "dist_180", "dist_270",
        "open_0", "open_90", "open_180", "open_270"
    ]
    if req_machine == "HALCYON":
        expected_slots.extend(["prox_0", "prox_90", "prox_180", "prox_270"])

    for f in dir_entries:
        full_p = os.path.join(target_path, f)
        if not os.path.isfile(full_p):
            continue

        norm_p = normalize_path(full_p)
        try:
            meta = parse_dicom_qc_header(full_p)
            slot = meta["target_slot"]

            file_info = {
                "filename": f,
                "saved_path": norm_p,
                "gantry_angle": meta["gantry_angle"],
                "beam_type": meta["beam_type"],
                "machine_type": meta["machine_type"],
                "leaf_bank": meta["leaf_bank"],
                "target_slot": slot,
                "raw_label": meta["raw_label"],
                "file_size": os.path.getsize(full_p)
            }
            detected_files.append(file_info)

            if slot in expected_slots and slot not in mapped_slots:
                mapped_slots[slot] = file_info
            else:
                unmapped_files.append(file_info)

        except Exception as parse_err:
            logger.debug(f"File '{f}' is unmapped/non-DICOM: {parse_err}")
            unmapped_files.append({
                "filename": f,
                "saved_path": norm_p,
                "raw_label": "Unknown / Non-DICOM File",
                "error": str(parse_err)
            })

    mapped_count = sum(1 for s in expected_slots if s in mapped_slots)
    is_complete = (mapped_count >= len(expected_slots))

    return {
        "status": "success",
        "folder_path": target_path,
        "total_dicom_files": len(detected_files),
        "machine_type": req_machine,
        "mapped_count": mapped_count,
        "required_count": len(expected_slots),
        "is_complete": is_complete,
        "expected_slots": expected_slots,
        "mapped_slots": mapped_slots,
        "unmapped_files": unmapped_files,
        "files": detected_files
    }

@app.post("/api/open-folder-dialog")
def open_folder_dialog_endpoint():
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder_path = filedialog.askdirectory(title="Select Watched DICOM Image Directory")
        root.destroy()

        if folder_path:
            norm_p = normalize_path(folder_path)
            return {
                "status": "success",
                "folder_path": norm_p,
                "canceled": False
            }
        else:
            return {
                "status": "success",
                "folder_path": "",
                "canceled": True
            }
    except Exception as err:
        logger.error(f"Native folder dialog error: {err}")
        raise HTTPException(status_code=500, detail=f"Failed to open native Windows folder dialog: {err}")

# ----------------------------------------------------
# QATRACK+ SETTINGS & REST API INTEGRATION ENDPOINTS
# ----------------------------------------------------
settings_file = os.path.join(sample_dir, "qatrack_settings.json")

def load_qatrack_settings():
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "qatrack_url": "http://localhost:8000",
        "qatrack_token": "",
        "unit_name": "Halcyon_1",
        "test_list_slug": "anti_gravity_mlc_qc",
        "macro_max_sag": "sag_max_mm",
        "macro_max_leaf_sag": "sag_max_leaf_mm",
        "macro_pass_rate": "pass_rate_pct",
        "macro_dlg_baseline": "dlg_0deg_mm",
        "macro_max_fluence": "max_fluence_delta_pct",
        "macro_qc_status": "qc_status"
    }

def save_qatrack_settings(settings_dict):
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(settings_dict, f, indent=2)

class QATrackSettingsModel(BaseModel):
    qatrack_url: str = "http://localhost:8000"
    qatrack_token: Optional[str] = ""
    unit_name: str = "Halcyon_1"
    test_list_slug: str = "anti_gravity_mlc_qc"
    macro_max_sag: str = "sag_max_mm"
    macro_max_leaf_sag: str = "sag_max_leaf_mm"
    macro_pass_rate: str = "pass_rate_pct"
    macro_dlg_baseline: str = "dlg_0deg_mm"
    macro_max_fluence: str = "max_fluence_delta_pct"
    macro_qc_status: str = "qc_status"

@app.get("/api/settings")
def get_settings_endpoint():
    return {
        "status": "success",
        "settings": load_qatrack_settings()
    }

@app.post("/api/settings")
def update_settings_endpoint(settings: QATrackSettingsModel):
    s_dict = settings.dict()
    save_qatrack_settings(s_dict)
    return {
        "status": "success",
        "message": "QATrack+ settings saved successfully",
        "settings": s_dict
    }

@app.post("/api/test-qatrack-connection")
def test_qatrack_connection_endpoint(settings: QATrackSettingsModel):
    base_url = settings.qatrack_url.rstrip("/")
    
    candidate_urls = []
    if "/api/" in base_url:
        candidate_urls.append(base_url if base_url.endswith("/") else base_url + "/")

    root_host = base_url.split("/api")[0].rstrip("/") if "/api" in base_url else base_url
    std_paths = [
        "/api/qa/test-lists/",
        "/api/v1/qa/test-lists/",
        "/api/qa/unittestcollections/",
        "/api/v1/qa/unittestcollections/",
        "/api/test-lists/",
        root_host
    ]
    for path in std_paths:
        full = path if path.startswith("http") else root_host + path
        if full not in candidate_urls:
            candidate_urls.append(full)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    if settings.qatrack_token:
        headers["Authorization"] = f"Token {settings.qatrack_token}"

    last_err = None
    for url in candidate_urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                return {
                    "status": "success",
                    "message": f"Successfully connected to QATrack+ server ({settings.qatrack_url})",
                    "endpoint_used": url,
                    "http_status": resp.status
                }
        except urllib.error.HTTPError as http_err:
            last_err = f"HTTP {http_err.code}: {http_err.reason}"
            if http_err.code in [401, 403]:
                return {
                    "status": "error",
                    "message": f"QATrack+ Authentication Failed ({last_err}). Please verify your API Token.",
                    "http_status": http_err.code
                }
            if http_err.code == 404:
                continue
        except Exception as err:
            last_err = str(err)

    return {
        "status": "error",
        "message": f"Could not connect to QATrack+ server ({settings.qatrack_url}). Error: {last_err}"
    }

class PushQATrackRequest(BaseModel):
    summary: Dict[str, Any]

@app.post("/api/push-qatrack-results")
def push_qatrack_results_endpoint(req: PushQATrackRequest):
    settings = load_qatrack_settings()
    raw_url = settings.get("qatrack_url", "http://localhost:8000").strip()
    base_url = raw_url.rstrip("/")
    
    # Strip GET-only suffixes if user pasted a test-lists endpoint in settings
    for get_suffix in ["/test-lists", "/test-lists/", "/testlists", "/testlists/"]:
        if base_url.endswith(get_suffix):
            base_url = base_url[:-len(get_suffix)].rstrip("/")

    summary = req.summary
    max_sag = float(summary.get("max_sag_amplitude_mm", 0.0))
    max_leaf_sag = float(summary.get("max_individual_leaf_sag_mm", max_sag))
    pass_rate = float(summary.get("pass_rate_pct", 100.0))
    dlg_info = summary.get("baseline_g0_dlg", {})
    dlg = float(dlg_info.get("dlg_system_mm", 0.0)) if isinstance(dlg_info, dict) else 0.0
    max_fluence = float(summary.get("max_dosimetric_delta_pct", 0.0))
    status_str = "PASS" if pass_rate >= 95 else ("WARN" if pass_rate >= 85 else "FAIL")

    results_payload = {
        settings.get("macro_max_sag", "sag_max_mm"): {"val": round(max_sag, 4)},
        settings.get("macro_max_leaf_sag", "sag_max_leaf_mm"): {"val": round(max_leaf_sag, 4)},
        settings.get("macro_pass_rate", "pass_rate_pct"): {"val": round(pass_rate, 2)},
        settings.get("macro_dlg_baseline", "dlg_0deg_mm"): {"val": round(dlg, 4)},
        settings.get("macro_max_fluence", "max_fluence_delta_pct"): {"val": round(max_fluence, 2)},
        settings.get("macro_qc_status", "qc_status"): {"val": status_str}
    }

    payload = {
        "unit": settings.get("unit_name", "Halcyon_1"),
        "test_list": settings.get("test_list_slug", "anti_gravity_mlc_qc"),
        "work_completed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status_str,
        "results": results_payload,
        "comment": f"Auto-pushed from Anti-Gravity QC Engine (Linac: {summary.get('machine_type', 'HALCYON')})"
    }

    candidate_urls = []
    if base_url.endswith("/unittestcollections") or base_url.endswith("/test-list-instances") or base_url.endswith("/testlistinstances"):
        candidate_urls.append(base_url if base_url.endswith("/") else base_url + "/")

    root_host = base_url.split("/api")[0].rstrip("/") if "/api" in base_url else base_url
    api_prefix = ""
    if "/api/v1" in base_url:
        api_prefix = "/api/v1"
    elif "/api" in base_url:
        api_prefix = "/api"

    std_paths = []
    if api_prefix:
        std_paths.extend([
            f"{api_prefix}/qa/unittestcollections/",
            f"{api_prefix}/qa/test-list-instances/",
            f"{api_prefix}/unittestcollections/",
            f"{api_prefix}/test-list-instances/",
        ])

    std_paths.extend([
        "/api/qa/unittestcollections/",
        "/api/v1/qa/unittestcollections/",
        "/api/qa/test-list-instances/",
        "/api/v1/qa/test-list-instances/",
        "/api/unittestcollections/",
        "/api/v1/unittestcollections/",
        "/api/qa/testlistinstances/",
        "/api/v1/qa/testlistinstances/"
    ])

    for path in std_paths:
        full = path if path.startswith("http") else root_host + path
        if full not in candidate_urls:
            candidate_urls.append(full)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    if settings.get("qatrack_token"):
        headers["Authorization"] = f"Token {settings['qatrack_token']}"

    json_bytes = json.dumps(payload).encode("utf-8")
    last_err_msg = ""
    attempted_urls = []

    for url in candidate_urls:
        attempted_urls.append(url)
        try:
            h_req = urllib.request.Request(url, data=json_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(h_req, timeout=10) as resp:
                resp_str = resp.read().decode("utf-8")
                try:
                    resp_data = json.loads(resp_str)
                except Exception:
                    resp_data = {"raw_response": resp_str}

                return {
                    "status": "success",
                    "message": f"Successfully pushed results to QATrack+ ({settings.get('unit_name')} / {settings.get('test_list_slug')})",
                    "endpoint_used": url,
                    "payload_sent": payload,
                    "qatrack_response": resp_data
                }
        except urllib.error.HTTPError as http_err:
            err_body = http_err.read().decode("utf-8", errors="ignore")
            last_err_msg = f"HTTP {http_err.code} ({http_err.reason}): {err_body[:300]}"
            if http_err.code in (404, 405):
                logger.info(f"QATrack+ candidate endpoint '{url}' returned {http_err.code}. Trying next candidate...")
                continue

            return {
                "status": "error",
                "message": f"QATrack+ Push Error ({last_err_msg})",
                "endpoint_used": url,
                "payload_sent": payload,
                "http_status": http_err.code,
                "details": err_body
            }
        except Exception as push_err:
            last_err_msg = str(push_err)

    return {
        "status": "error",
        "message": f"QATrack+ Push Failed: None of the candidate endpoints succeeded on {base_url}. Error: {last_err_msg}",
        "attempted_urls": attempted_urls,
        "payload_sent": payload
    }

@app.get("/api/plan-info")
def get_plan_info_endpoint(plan_path: str):
    target_path = normalize_path(plan_path)
    if not os.path.exists(target_path):
        root_dir = os.path.dirname(os.path.dirname(__file__))
        alt1 = normalize_path(os.path.join(root_dir, plan_path))
        alt2 = normalize_path(os.path.join(sample_dir, os.path.basename(plan_path)))
        if os.path.exists(alt1):
            target_path = alt1
        elif os.path.exists(alt2):
            target_path = alt2
        else:
            raise HTTPException(status_code=404, detail=f"RT Plan file not found: {plan_path}")

    try:
        dcm = pydicom.dcmread(target_path)
    except Exception as err:
        raise HTTPException(status_code=400, detail=f"Failed to parse DICOM RT Plan: {err}")

    beams = []
    if hasattr(dcm, "BeamSequence"):
        for i, b in enumerate(dcm.BeamSequence):
            b_num = int(getattr(b, "BeamNumber", i + 1))
            b_name = str(getattr(b, "BeamName", f"Beam_{i+1}"))
            b_type = str(getattr(b, "TreatmentDeliveryType", getattr(b, "BeamType", "STATIC")))
            cps = getattr(b, "ControlPointSequence", [])
            cp_count = len(cps)
            gantry = float(getattr(cps[0], "GantryAngle", 0.0)) if cp_count > 0 else 0.0
            coll = float(getattr(cps[0], "BeamLimitingDeviceAngle", 0.0)) if cp_count > 0 else 0.0

            beams.append({
                "beam_index": i + 1,
                "beam_number": b_num,
                "beam_name": b_name,
                "beam_type": b_type,
                "control_points": cp_count,
                "gantry_angle": gantry,
                "collimator_angle": coll
            })

    return {
        "status": "success",
        "plan_name": str(getattr(dcm, "RTPlanName", getattr(dcm, "RTPlanLabel", "UNNAMED_PLAN"))),
        "patient_name": str(getattr(dcm, "PatientName", "ANONYMOUS")),
        "total_beams": len(beams),
        "beams": beams
    }

class AntiGravityQCRequest(BaseModel):
    machine_type: str = "HALCYON"
    cardinal_datasets: List[Dict[str, Any]]
    warn_sag_mm: float = 0.5
    action_sag_mm: float = 1.0
    warn_fluence_pct: float = 5.0
    apply_magnification_correction: bool = True

@app.post("/api/analyze-anti-gravity-qc")
def analyze_anti_gravity_qc_endpoint(req: AntiGravityQCRequest):
    if not req.cardinal_datasets:
        raise HTTPException(status_code=400, detail="No cardinal datasets provided.")

    norm_datasets = []
    for d in req.cardinal_datasets:
        nd = dict(d)
        if "open_field" in nd and nd["open_field"]:
            nd["open_field"] = normalize_path(nd["open_field"])
        if "distal_field" in nd and nd["distal_field"]:
            nd["distal_field"] = normalize_path(nd["distal_field"])
        if "proximal_field" in nd and nd["proximal_field"]:
            nd["proximal_field"] = normalize_path(nd["proximal_field"])
        if "mlc_field" in nd and nd["mlc_field"]:
            nd["mlc_field"] = normalize_path(nd["mlc_field"])
        if "picket_field" in nd and nd["picket_field"]:
            nd["picket_field"] = normalize_path(nd["picket_field"])
        norm_datasets.append(nd)

    try:
        results = run_anti_gravity_qc_pipeline(
            cardinal_datasets=norm_datasets,
            machine_type=req.machine_type,
            warn_sag_mm=req.warn_sag_mm,
            action_sag_mm=req.action_sag_mm,
            warn_fluence_pct=req.warn_fluence_pct,
            apply_magnification_correction=req.apply_magnification_correction
        )
        return {
            "status": "success",
            "summary": results["summary"],
            "analyzed_angles": results["analyzed_angles"],
            "combined_metrics": results["combined_metrics"]
        }
    except Exception as err:
        raise HTTPException(status_code=400, detail=f"Anti-Gravity QC analysis failed: {err}")

@app.post("/api/upload-rtplan")
def upload_rtplan_endpoint(file: UploadFile = File(...)):
    clean_filename = os.path.basename(file.filename) if file.filename else "uploaded_plan.dcm"
    dest_path = os.path.join(sample_dir, f"uploaded_{clean_filename}")
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

    return {
        "status": "success",
        "filename": clean_filename,
        "saved_path": normalize_path(dest_path)
    }

class SimulatePlanFluenceRequest(BaseModel):
    plan_path: str
    beam_number: int = 1
    control_point_index: Optional[int] = None
    focal_spot_sigma: float = 1.0
    leaf_transmission: float = 0.13

@app.post("/api/simulate-plan-fluence")
def simulate_plan_fluence_endpoint(req: SimulatePlanFluenceRequest):
    target_path = normalize_path(req.plan_path)

    if not os.path.exists(target_path):
        root_dir = os.path.dirname(os.path.dirname(__file__))
        alt1 = normalize_path(os.path.join(root_dir, req.plan_path))
        alt2 = normalize_path(os.path.join(sample_dir, os.path.basename(req.plan_path)))
        if os.path.exists(alt1):
            target_path = alt1
        elif os.path.exists(alt2):
            target_path = alt2
        else:
            raise HTTPException(status_code=404, detail=f"RT Plan file not found: {req.plan_path}")

    arr, gantry_angle, plan_meta = simulate_plan_fluence_map(
        input_plan_path=target_path,
        beam_number=req.beam_number,
        control_point_index=req.control_point_index,
        focal_spot_sigma=req.focal_spot_sigma,
        leaf_transmission=req.leaf_transmission
    )

    out_dcm_name = f"simulated_fluence_beam_{req.beam_number}.dcm"
    out_dcm_path = os.path.join(sample_dir, out_dcm_name)
    save_synthetic_dicom_rtimage(arr, out_dcm_path, gantry_angle=gantry_angle, label="HAL_PSEUDO_FLU")

    p_min, p_max = np.percentile(arr, 1), np.percentile(arr, 99)
    norm_arr = np.clip((arr - p_min) / (p_max - p_min + 1e-6) * 255.0, 0, 255).astype(np.uint8)
    pil_img = Image.fromarray(norm_arr)

    buffered = io.BytesIO()
    pil_img.save(buffered, format="PNG")
    b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

    norm_out_path = normalize_path(out_dcm_path)
    current_data["last_simulated_fluence"] = {
        "file_path": norm_out_path,
        "pixel_array": arr
    }

    return {
        "status": "success",
        "plan_metadata": plan_meta,
        "gantry_angle": gantry_angle,
        "preview_png_b64": f"data:image/png;base64,{b64_str}",
        "dicom_rtimage_path": norm_out_path,
        "filename": out_dcm_name
    }

class SimulateAllFieldsRequest(BaseModel):
    plan_path: str
    focal_spot_sigma: float = 1.0
    leaf_transmission: float = 0.13

@app.post("/api/simulate-all-fields")
def simulate_all_fields_endpoint(req: SimulateAllFieldsRequest):
    target_path = normalize_path(req.plan_path)
    if not os.path.exists(target_path):
        root_dir = os.path.dirname(os.path.dirname(__file__))
        alt1 = normalize_path(os.path.join(root_dir, req.plan_path))
        alt2 = normalize_path(os.path.join(sample_dir, os.path.basename(req.plan_path)))
        if os.path.exists(alt1):
            target_path = alt1
        elif os.path.exists(alt2):
            target_path = alt2
        else:
            raise HTTPException(status_code=404, detail=f"RT Plan file not found: {req.plan_path}")

    dcm = pydicom.dcmread(target_path)
    field_results = []

    if hasattr(dcm, "BeamSequence"):
        for i, b in enumerate(dcm.BeamSequence):
            b_num = int(getattr(b, "BeamNumber", i + 1))
            b_name = str(getattr(b, "BeamName", f"Beam_{i+1}"))

            arr, gantry_angle, plan_meta = simulate_plan_fluence_map(
                input_plan_path=target_path,
                beam_number=b_num,
                focal_spot_sigma=req.focal_spot_sigma,
                leaf_transmission=req.leaf_transmission
            )

            out_dcm_name = f"simulated_field_{b_num}_{b_name}.dcm"
            out_dcm_path = os.path.join(sample_dir, out_dcm_name)
            save_synthetic_dicom_rtimage(arr, out_dcm_path, gantry_angle=gantry_angle, label=f"HAL_BEAM_{b_num}")

            p_min, p_max = np.percentile(arr, 1), np.percentile(arr, 99)
            norm_arr = np.clip((arr - p_min) / (p_max - p_min + 1e-6) * 255.0, 0, 255).astype(np.uint8)
            pil_img = Image.fromarray(norm_arr)

            buffered = io.BytesIO()
            pil_img.save(buffered, format="PNG")
            b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

            field_results.append({
                "beam_index": i + 1,
                "beam_number": b_num,
                "beam_name": b_name,
                "gantry_angle": gantry_angle,
                "control_points": plan_meta["total_control_points"],
                "preview_png_b64": f"data:image/png;base64,{b64_str}",
                "dicom_rtimage_path": normalize_path(out_dcm_path),
                "filename": out_dcm_name
            })

    return {
        "status": "success",
        "total_fields": len(field_results),
        "fields": field_results
    }

@app.post("/api/load-image")
def load_image_endpoint(file_path: str = Form(...), slot: str = Form("a")):
    target_path = normalize_path(file_path)
    if not os.path.exists(target_path):
        root_dir = os.path.dirname(os.path.dirname(__file__))
        alt1 = normalize_path(os.path.join(root_dir, file_path))
        alt2 = normalize_path(os.path.join(sample_dir, os.path.basename(file_path)))
        alt3 = normalize_path(os.path.join(sample_dir, "GravityTB", os.path.basename(file_path)))
        alt4 = normalize_path(os.path.join(root_dir, "Test Images", "Gravity ETHOS", "Normal", os.path.basename(file_path)))
        alt5 = normalize_path(os.path.join(temp_upload_dir, os.path.basename(file_path)))
        if os.path.exists(alt1):
            target_path = alt1
        elif os.path.exists(alt2):
            target_path = alt2
        elif os.path.exists(alt3):
            target_path = alt3
        elif os.path.exists(alt4):
            target_path = alt4
        elif os.path.exists(alt5):
            target_path = alt5
        else:
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        
    res = load_dicom_or_image(target_path)
    res["file_path"] = target_path
    
    if slot.lower() == "b":
        current_data["image_b"] = res
    else:
        current_data["image_a"] = res
        
    return {
        "status": "success",
        "slot": slot,
        "metadata": res["metadata"],
        "preview_b64": res["preview_png_b64"]
    }

class CompareRequest(BaseModel):
    file_a: Optional[str] = None
    file_b: Optional[str] = None
    warn_thresh_mm: float = 0.5
    fail_thresh_mm: float = 1.0
    enable_registration: bool = True

@app.post("/api/compare-mlc")
def compare_mlc_endpoint(req: CompareRequest):
    if req.file_a and os.path.exists(req.file_a):
        current_data["image_a"] = load_dicom_or_image(req.file_a)
        current_data["image_a"]["file_path"] = normalize_path(req.file_a)
    if req.file_b and os.path.exists(req.file_b):
        current_data["image_b"] = load_dicom_or_image(req.file_b)
        current_data["image_b"]["file_path"] = normalize_path(req.file_b)

    img_a = current_data.get("image_a")
    img_b = current_data.get("image_b")

    if not img_a or not img_b:
        raise HTTPException(status_code=400, detail="Both Delivery A and Delivery B images must be loaded.")

    arr_a = img_a["pixel_array"]
    arr_b = img_b["pixel_array"]
    dx = img_a["metadata"]["pixel_spacing_x"]
    dy = img_a["metadata"]["pixel_spacing_y"]

    results = compare_deliveries(
        arr_a=arr_a,
        arr_b=arr_b,
        dx=dx,
        dy=dy,
        warn_thresh_mm=req.warn_thresh_mm,
        fail_thresh_mm=req.fail_thresh_mm,
        enable_registration=req.enable_registration
    )

    diff = arr_b - arr_a
    max_abs = max(1.0, np.percentile(np.abs(diff), 99))
    norm_diff = np.clip((diff / (2.0 * max_abs) + 0.5) * 255.0, 0, 255).astype(np.uint8)
    
    pil_diff = Image.fromarray(norm_diff)
    buffered = io.BytesIO()
    pil_diff.save(buffered, format="PNG")
    diff_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return {
        "status": "success",
        "metadata_a": img_a["metadata"],
        "metadata_b": img_b["metadata"],
        "preview_a_b64": img_a["preview_png_b64"],
        "preview_b_b64": img_b["preview_png_b64"],
        "diff_heatmap_b64": f"data:image/png;base64,{diff_b64}",
        "summary": results["summary"],
        "leaf_results": results["leaf_results"]
    }

@app.get("/api/leaf-profile/{track_index}")
def get_leaf_profile_endpoint(track_index: int):
    img_a = current_data.get("image_a")
    img_b = current_data.get("image_b")
    
    if not img_a or not img_b:
        raise HTTPException(status_code=400, detail="Images not loaded.")
        
    arr_a = img_a["pixel_array"]
    arr_b = img_b["pixel_array"]
    dy = img_a["metadata"]["pixel_spacing_y"]
    dx = img_a["metadata"]["pixel_spacing_x"]
    
    rows, cols = arr_a.shape
    iso_y = rows / 2.0
    iso_x = cols / 2.0
    
    num_tracks = 57
    pitch_px = 5.0 / dy
    y_start = iso_y - (num_tracks / 2.0) * pitch_px
    yc = y_start + (track_index - 0.5) * pitch_px
    r_idx = int(round(yc))
    
    if r_idx < 0 or r_idx >= rows:
        raise HTTPException(status_code=400, detail="Track index out of bounds.")
        
    prof_a = arr_a[r_idx - 1 : r_idx + 2, :].mean(axis=0).tolist()
    prof_b = arr_b[r_idx - 1 : r_idx + 2, :].mean(axis=0).tolist()
    
    x_mm = [float((i - iso_x) * dx) for i in range(cols)]
    bank = "Proximal (SX1)" if (track_index % 2 != 0) else "Distal (SX2)"
    pair_num = ((track_index - 1) // 2) + 1

    return {
        "track_index": track_index,
        "bank": bank,
        "pair_number": pair_num,
        "label": f"{bank} Pair {pair_num}",
        "y_center_px": float(yc),
        "y_center_mm": float((yc - iso_y) * dy),
        "x_mm": x_mm,
        "profile_a": prof_a,
        "profile_b": prof_b
    }

@app.post("/api/generate-demo-series")
def generate_demo_series_endpoint(
    sag_amplitude_mm: float = Form(1.2),
    stuck_leaf_index: int = Form(10),
    stuck_leaf_pos_mm: float = Form(25.0),
    calibration_offset_leaf: int = Form(15),
    calibration_offset_mm: float = Form(0.8)
):
    angles = [0.0, 90.0, 180.0, 270.0]
    generated_files = []

    faults = {
        "sag_amplitude_mm": sag_amplitude_mm,
        "stuck_leaves": {stuck_leaf_index: stuck_leaf_pos_mm},
        "calibration_offsets": {calibration_offset_leaf: calibration_offset_mm},
        "gaussian_noise_std": 200.0
    }

    for angle in angles:
        arr = generate_synthetic_mlc_image(
            gantry_angle=angle,
            pattern_type="picket_fence",
            faults_dict=faults
        )
        fname = f"halcyon_gantry_{int(angle)}deg.dcm"
        fpath = os.path.join(sample_dir, fname)
        save_synthetic_dicom_rtimage(arr, fpath, gantry_angle=angle, label=f"HAL_GANTRY_{int(angle)}")
        generated_files.append({"gantry_angle": angle, "path": normalize_path(fpath), "filename": fname})

    return {
        "status": "success",
        "message": "Generated synthetic 4-angle Gantry series (0°, 90°, 180°, 270°)",
        "files": generated_files
    }

class SagAnalysisRequest(BaseModel):
    file_paths: List[str]
    open_file_paths: Optional[List[str]] = None
    apply_open_field_ratio: bool = True
    apply_epid_flex_correction: bool = True
    manual_flex_x_mm: float = 0.0
    manual_flex_y_mm: float = 0.0
    warn_thresh_mm: float = 0.5
    fail_thresh_mm: float = 1.0

@app.post("/api/analyze-sag")
def analyze_sag_endpoint(req: SagAnalysisRequest):
    if not req.file_paths:
        raise HTTPException(status_code=400, detail="No DICOM files provided for analysis.")

    gantry_frames = []
    metadata_list = []

    for i, fpath in enumerate(req.file_paths):
        target_path = normalize_path(fpath)
        if not os.path.exists(target_path):
            root_dir = os.path.dirname(os.path.dirname(__file__))
            alt1 = normalize_path(os.path.join(root_dir, fpath))
            alt2 = normalize_path(os.path.join(sample_dir, os.path.basename(fpath)))
            alt3 = normalize_path(os.path.join(sample_dir, "GravityTB", os.path.basename(fpath)))
            alt4 = normalize_path(os.path.join(root_dir, "Test Images", "Gravity ETHOS", "Normal", os.path.basename(fpath)))
            alt5 = normalize_path(os.path.join(temp_upload_dir, os.path.basename(fpath)))
            if os.path.exists(alt1):
                target_path = alt1
            elif os.path.exists(alt2):
                target_path = alt2
            elif os.path.exists(alt3):
                target_path = alt3
            elif os.path.exists(alt4):
                target_path = alt4
            elif os.path.exists(alt5):
                target_path = alt5
            else:
                continue

        data = load_dicom_or_image(target_path)
        arr = data["pixel_array"].astype(np.float32)
        meta = data["metadata"]
        dx = meta["pixel_spacing_x"]
        dy = meta["pixel_spacing_y"]
        g_angle = meta["gantry_angle"]

        proc_arr = arr
        if req.apply_open_field_ratio and req.open_file_paths and i < len(req.open_file_paths):
            open_path = req.open_file_paths[i]
            if open_path and os.path.exists(open_path):
                open_data = load_dicom_or_image(open_path)
                open_arr = open_data["pixel_array"].astype(np.float32)
                
                mask = open_arr > 1000.0
                ratio = np.where(mask, arr / (open_arr + 1e-5), 0.0).astype(np.float32)
                proc_arr = ratio * 50000.0

        frame_result = analyze_gantry_frame(
            pixel_array=proc_arr,
            gantry_angle=g_angle,
            dx=dx,
            dy=dy,
            apply_flex_correction=req.apply_epid_flex_correction,
            manual_flex_x_mm=req.manual_flex_x_mm,
            manual_flex_y_mm=req.manual_flex_y_mm
        )
        gantry_frames.append(frame_result)
        metadata_list.append(meta)

    if not gantry_frames:
        raise HTTPException(status_code=400, detail="Failed to parse valid DICOM gantry frames.")

    sag_results = calculate_gravity_sag(
        gantry_frames=gantry_frames,
        warn_thresh_mm=req.warn_thresh_mm,
        fail_thresh_mm=req.fail_thresh_mm
    )

    qc_report = generate_qc_report(sag_results, metadata_list)

    return {
        "status": "success",
        "gantry_frames": gantry_frames,
        "summary": sag_results["summary"],
        "sag_metrics": sag_results["sag_metrics"],
        "qc_report": qc_report
    }

class SimulateFaultsRequest(BaseModel):
    gantry_angle: float = 90.0
    sag_amplitude_mm: float = 1.2
    stuck_leaves: Dict[int, float] = {}
    calibration_offsets: Dict[int, float] = {}
    bank_offset_sx1: float = 0.0
    bank_offset_sx2: float = 0.0
    gaussian_noise_std: float = 200.0

@app.post("/api/simulate-faults")
def simulate_faults_endpoint(req: SimulateFaultsRequest):
    faults = {
        "sag_amplitude_mm": req.sag_amplitude_mm,
        "stuck_leaves": req.stuck_leaves,
        "calibration_offsets": req.calibration_offsets,
        "bank_calibration_offset_sx1": req.bank_offset_sx1,
        "bank_calibration_offset_sx2": req.bank_offset_sx2,
        "gaussian_noise_std": req.gaussian_noise_std
    }

    arr = generate_synthetic_mlc_image(
        gantry_angle=req.gantry_angle,
        pattern_type="picket_fence",
        faults_dict=faults
    )

    p_min, p_max = np.percentile(arr, 1), np.percentile(arr, 99)
    norm_arr = np.clip((arr - p_min) / (p_max - p_min + 1e-6) * 255.0, 0, 255).astype(np.uint8)
    pil_img = Image.fromarray(norm_arr)

    buffered = io.BytesIO()
    pil_img.save(buffered, format="PNG")
    b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return {
        "status": "success",
        "gantry_angle": req.gantry_angle,
        "preview_png_b64": f"data:image/png;base64,{b64_str}",
        "min_val": float(arr.min()),
        "max_val": float(arr.max()),
        "mean_val": float(arr.mean())
    }

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            content = f.read()
            return HTMLResponse(content=content, headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            })
    return HTMLResponse("<h1>Anti-Gravity QC v3.1 Operational</h1>")
