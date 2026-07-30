/**
 * InspectMLC Simulator UI Controller
 * Manages fault injection parameters (stuck leaves, calibration shifts, sag amplitude, noise)
 * and communicates with /api/simulate-faults endpoint.
 */
document.addEventListener('DOMContentLoaded', () => {
    const simGantryAngle = document.getElementById('sim-gantry-angle');
    const simSagAmp = document.getElementById('sim-sag-amp');
    const simStuckLeaf = document.getElementById('sim-stuck-leaf');
    const simStuckPos = document.getElementById('sim-stuck-pos');
    const simCalOffsetLeaf = document.getElementById('sim-cal-offset-leaf');
    const simCalOffsetMm = document.getElementById('sim-cal-offset-mm');
    const simNoiseStd = document.getElementById('sim-noise-std');

    const btnRunSim = document.getElementById('btn-run-simulation');
    const previewImg = document.getElementById('sim-preview-img');
    const previewPlaceholder = document.getElementById('sim-preview-placeholder');

    if (btnRunSim) {
        btnRunSim.addEventListener('click', runSimulation);
    }

    function runSimulation() {
        const gantryAngle = parseFloat(simGantryAngle ? simGantryAngle.value : 90.0);
        const sagAmp = parseFloat(simSagAmp ? simSagAmp.value : 1.2);
        const stuckLeaf = parseInt(simStuckLeaf ? simStuckLeaf.value : 10);
        const stuckPos = parseFloat(simStuckPos ? simStuckPos.value : 25.0);
        const calLeaf = parseInt(simCalOffsetLeaf ? simCalOffsetLeaf.value : 15);
        const calShift = parseFloat(simCalOffsetMm ? simCalOffsetMm.value : 0.8);
        const noiseStd = parseFloat(simNoiseStd ? simNoiseStd.value : 200.0);

        btnRunSim.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Generating...`;
        btnRunSim.disabled = true;

        const faults = {
            gantry_angle: gantryAngle,
            sag_amplitude_mm: sagAmp,
            stuck_leaves: { [stuckLeaf]: stuckPos },
            calibration_offsets: { [calLeaf]: calShift },
            gaussian_noise_std: noiseStd
        };

        fetch('/api/simulate-faults', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(faults)
        })
        .then(res => res.json())
        .then(data => {
            btnRunSim.innerHTML = `<span>⚡</span> Generate Synthetic Image & Test Faults`;
            btnRunSim.disabled = false;

            if (data.status === 'success' && data.preview_png_b64) {
                previewImg.src = data.preview_png_b64;
                previewImg.style.display = 'block';
                if (previewPlaceholder) previewPlaceholder.style.display = 'none';
            } else {
                alert("Simulation failed: " + (data.detail || "Unknown error"));
            }
        })
        .catch(err => {
            btnRunSim.innerHTML = `<span>⚡</span> Generate Synthetic Image & Test Faults`;
            btnRunSim.disabled = false;
            console.error("Simulation error:", err);
        });
    }
});
