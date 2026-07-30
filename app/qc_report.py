import json
from typing import Dict, List, Any

def generate_qc_report(sag_analysis_result: Dict[str, Any], metadata_series: List[Dict[str, Any]] = None):
    """
    Aggregates gravitational sag metrics, checks tolerance thresholds,
    and returns a structured JSON QC Report summary.
    """
    summary = sag_analysis_result.get("summary", {})
    metrics = sag_analysis_result.get("sag_metrics", [])

    failed_tracks = [m for m in metrics if m["status"] == "FAIL"]
    warned_tracks = [m for m in metrics if m["status"] == "WARN"]

    report = {
        "title": "Varian Halcyon MLC Gravitational Sag & Positional Stability QC Report",
        "target_machine": "Varian Halcyon (HAL7)",
        "mlc_architecture": "Dual-Layer Staggered (Proximal SX1 & Distal SX2)",
        "total_gantry_angles_analyzed": len(metadata_series) if metadata_series else 4,
        "summary": summary,
        "action_required": summary.get("fail_count", 0) > 0,
        "failed_track_list": [
            {
                "track_index": m["track_index"],
                "label": m["label"],
                "bank": m["bank"],
                "max_sag_mm": m["max_sag_mm"],
                "fitted_amplitude_mm": m["fitted_amplitude_mm"]
            }
            for m in failed_tracks
        ],
        "warned_track_list": [
            {
                "track_index": m["track_index"],
                "label": m["label"],
                "bank": m["bank"],
                "max_sag_mm": m["max_sag_mm"],
                "fitted_amplitude_mm": m["fitted_amplitude_mm"]
            }
            for m in warned_tracks
        ]
    }

    return report
