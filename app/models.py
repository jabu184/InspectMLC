from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class ImageMetadata(BaseModel):
    filename: str
    modality: str = "RTIMAGE"
    manufacturer: str = "Varian"
    model: str = "Halcyon"
    station_name: str = "HAL7"
    label: str = ""
    gantry_angle: float = 0.0
    collimator_angle: float = 0.0
    sad_mm: float = 1000.0
    columns: int = 1280
    rows: int = 1280
    pixel_spacing_x: float = 0.336  # mm/pixel
    pixel_spacing_y: float = 0.336  # mm/pixel
    min_val: float = 0.0
    max_val: float = 65535.0
    mean_val: float = 0.0

class SubpixelEdgeFit(BaseModel):
    track_index: int
    bank: str  # Proximal (SX1) or Distal (SX2)
    pair_number: int
    label: str
    y_center_px: float
    y_center_mm: float
    left_edge_px: Optional[float] = None
    left_edge_mm: Optional[float] = None
    right_edge_px: Optional[float] = None
    right_edge_mm: Optional[float] = None
    fit_quality_r2: Optional[float] = 1.0

class GantryAngleFrame(BaseModel):
    gantry_angle: float
    filename: str
    epid_flex_x_mm: float = 0.0
    epid_flex_y_mm: float = 0.0
    edges: List[SubpixelEdgeFit]

class LeafSagMetric(BaseModel):
    track_index: int
    bank: str
    pair_number: int
    label: str
    neutral_left_mm: Optional[float] = None
    neutral_right_mm: Optional[float] = None
    
    # Position deviations at 90° and 270°
    sag_90_left_mm: Optional[float] = None
    sag_90_right_mm: Optional[float] = None
    sag_270_left_mm: Optional[float] = None
    sag_270_right_mm: Optional[float] = None
    
    max_sag_mm: float = 0.0
    fitted_amplitude_mm: float = 0.0
    status: str = "PASS"  # PASS (>0.5mm WARN, >1.0mm FAIL)

class SagAnalysisSummary(BaseModel):
    total_tracks_analyzed: int = 56
    pass_count: int = 56
    warn_count: int = 0
    fail_count: int = 0
    pass_rate_pct: float = 100.0
    max_sag_amplitude_mm: float = 0.0
    mean_abs_sag_mm: float = 0.0
    rmse_sag_mm: float = 0.0
    epid_flex_correction_applied: bool = True
    warning_threshold_mm: float = 0.5
    failure_threshold_mm: float = 1.0

class FaultInjectionConfig(BaseModel):
    stuck_leaves: Dict[int, float] = Field(default_factory=dict)       # track_index -> fixed_position_mm
    calibration_offsets: Dict[int, float] = Field(default_factory=dict)# track_index -> shift_mm
    bank_calibration_offset_sx1: float = 0.0                            # SX1 bank shift in mm
    bank_calibration_offset_sx2: float = 0.0                            # SX2 bank shift in mm
    sag_amplitude_mm: float = 0.0                                       # S_i sag amplitude in mm (S_i * sin(gantry))
    gaussian_noise_std: float = 0.0                                     # Noise injection
    poisson_noise_scale: float = 0.0
