/**
 * InspectMLC Chart Renderer v5.0
 * Renders:
 * 1. Gravitational Sag Bar Chart (90° & 270°) with Percentage Tolerance Heatmap Colors (Green -> Yellow -> Orange -> Red)
 * 2. Dynamic Gantry Angle Vector Plot Δx_sag(θ) (0°, 90°, 180°, 270°, 360°)
 * 3. EPID Panel Center Variation Plot ΔX_panel(θ) & ΔY_panel(θ) vs. Gantry Angle θ
 */
class MLCChartsRenderer {
    constructor() {
        this.discrepancyCanvas = document.getElementById('canvas-discrepancy-chart');
        this.profileCanvas = document.getElementById('canvas-profile-chart');
        this.panelCanvas = document.getElementById('canvas-panel-center-chart');
        
        this.sagMetrics = [];
        this.panelOffsets = {};
        this.selectedTrackIndex = 1;
        this.warnThreshMm = 0.5;
        this.actionThreshMm = 1.0;

        this.onSelectTrackCallback = null;

        if (this.discrepancyCanvas) {
            this.discrepancyCanvas.addEventListener('click', (e) => this.handleDiscrepancyClick(e));
        }
    }

    setToleranceThresholds(warnMm, actionMm) {
        this.warnThreshMm = parseFloat(warnMm) || 0.5;
        this.actionThreshMm = parseFloat(actionMm) || 1.0;
        this.renderSagChart();
        this.renderSagAngleCurve();
    }

    getToleranceColor(sagMm) {
        if (sagMm === undefined || sagMm === null) return '#10b981';
        const absSag = Math.abs(sagMm);
        const tw = Math.max(0.01, this.warnThreshMm || 0.5);
        const ta = Math.max(tw, this.actionThreshMm || 1.0);

        if (absSag < 0.5 * tw) {
            return '#10b981'; // Green (<50% of Warning Tolerance)
        } else if (absSag < tw) {
            return '#eab308'; // Yellow (50% to 100% of Warning Tolerance)
        } else if (absSag < ta) {
            return '#f97316'; // Orange (100% of Warning to Action Tolerance)
        } else {
            return '#ef4444'; // Red (>= Action Level)
        }
    }

    setSagResults(sagMetrics, panelOffsets = {}, selectedTrackIndex = 1, callback = null) {
        this.sagMetrics = sagMetrics || [];
        this.panelOffsets = panelOffsets || {};
        this.selectedTrackIndex = parseInt(selectedTrackIndex, 10) || 1;
        if (callback) this.onSelectTrackCallback = callback;
        
        this.renderSagChart();
        this.renderSagAngleCurve();
        this.renderPanelCenterChart();
    }

    setSelectedTrackIndex(trackIdx) {
        this.selectedTrackIndex = parseInt(trackIdx, 10) || 1;
        this.renderSagChart();
        this.renderSagAngleCurve();
    }

    setPanelOffsets(panelOffsets) {
        this.panelOffsets = panelOffsets || {};
        this.renderPanelCenterChart();
    }

    handleDiscrepancyClick(e) {
        if (!this.sagMetrics || this.sagMetrics.length === 0) return;
        const targetCanvas = this.discrepancyCanvas;
        if (!targetCanvas) return;
        
        const rect = targetCanvas.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        
        const paddingLeft = 50;
        const paddingRight = 25;
        const chartW = rect.width - paddingLeft - paddingRight;
        
        const count = this.sagMetrics.length;
        const barStep = chartW / count;
        
        const idx = Math.floor((clickX - paddingLeft) / barStep);
        if (idx >= 0 && idx < count) {
            const trackObj = this.sagMetrics[idx];
            this.selectedTrackIndex = trackObj.track_index;

            const s90 = Math.abs(trackObj.sag_90_mm || 0);
            const s270 = Math.abs(trackObj.sag_270_mm || 0);
            let targetAngle = 90;
            if (s270 > s90) {
                targetAngle = 270;
            }

            this.renderSagChart();
            this.renderSagAngleCurve();
            if (this.onSelectTrackCallback) {
                this.onSelectTrackCallback(this.selectedTrackIndex, targetAngle);
            }
        }
    }

    renderSagChart() {
        if (!this.discrepancyCanvas || !this.sagMetrics || this.sagMetrics.length === 0) return;

        const canvas = this.discrepancyCanvas;
        const ctx = canvas.getContext('2d');
        const parent = canvas.parentElement;

        const width = Math.floor(parent ? parent.clientWidth : 600);
        const height = Math.floor(parent ? parent.clientHeight : 180);

        if (width <= 0 || height <= 0) return;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;

        ctx.save();
        ctx.scale(dpr, dpr);
        ctx.imageSmoothingEnabled = true;
        ctx.clearRect(0, 0, width, height);

        const paddingLeft = 50;
        const paddingRight = 25;
        const paddingTop = 20;
        const paddingBottom = 30;

        const chartW = width - paddingLeft - paddingRight;
        const chartH = height - paddingTop - paddingBottom;

        const warnVal = this.warnThreshMm || 0.5;
        const maxVal = Math.max(warnVal * 1.2, ...this.sagMetrics.map(m => Math.abs(m.max_leaf_sag_mm !== undefined ? m.max_leaf_sag_mm : (m.max_sag_mm || 0))));
        const yMin = -maxVal * 1.25;
        const yMax = maxVal * 1.25;

        function valToY(v) {
            const norm = (v - yMin) / (yMax - yMin + 1e-6);
            return paddingTop + (1.0 - norm) * chartH;
        }

        const zeroY = valToY(0);

        // Grid lines & Y-axis labels
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 1;

        const yTicks = [yMin, yMin / 2, 0, yMax / 2, yMax];
        ctx.fillStyle = '#94a3b8';
        ctx.font = '10px Inter, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';

        yTicks.forEach(t => {
            const py = valToY(t);
            ctx.beginPath();
            ctx.moveTo(paddingLeft, py);
            ctx.lineTo(paddingLeft + chartW, py);
            ctx.stroke();
            ctx.fillText(`${t >= 0 ? '+' : ''}${t.toFixed(2)} mm`, paddingLeft - 6, py);
        });

        // Tolerance Lines (+/- Warning Tolerance)
        const warnY_pos = valToY(warnVal);
        const warnY_neg = valToY(-warnVal);

        ctx.strokeStyle = 'rgba(245, 158, 11, 0.5)';
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(paddingLeft, warnY_pos); ctx.lineTo(paddingLeft + chartW, warnY_pos);
        ctx.moveTo(paddingLeft, warnY_neg); ctx.lineTo(paddingLeft + chartW, warnY_neg);
        ctx.stroke();
        ctx.setLineDash([]);

        // Draw Bars for each track using Percentage Tolerance Heatmap Colors
        const count = this.sagMetrics.length;
        const barStep = chartW / count;
        const barW = Math.max(2.5, barStep * 0.7);

        this.sagMetrics.forEach((m, i) => {
            const isSelected = (parseInt(m.track_index, 10) === parseInt(this.selectedTrackIndex, 10));
            const delta = m.max_leaf_sag_mm !== undefined ? m.max_leaf_sag_mm : (m.max_sag_mm || 0);
            
            const bx = paddingLeft + i * barStep + (barStep - barW) / 2;
            const by = valToY(delta);
            const bh = zeroY - by;

            const fillColor = this.getToleranceColor(delta);

            ctx.fillStyle = fillColor;
            ctx.fillRect(bx, Math.min(zeroY, by), barW, Math.max(2, Math.abs(bh)));

            if (isSelected) {
                ctx.strokeStyle = '#00f2fe';
                ctx.lineWidth = 2.0;
                ctx.strokeRect(bx - 2, Math.min(zeroY, by) - 2, barW + 4, Math.max(2, Math.abs(bh)) + 4);
            }

            if (i % 4 === 0 || count <= 30) {
                const labelStr = m.bank.includes("SX1") ? `P${m.pair_number}` : (m.bank.includes("SX2") ? `D${m.pair_number}` : `${m.pair_number}`);
                ctx.fillStyle = isSelected ? '#00f2fe' : '#94a3b8';
                ctx.font = isSelected ? '700 9px Inter, sans-serif' : '9px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(labelStr, bx + barW / 2, height - 8);
            }
        });

        ctx.restore();
    }

    renderSagAngleCurve() {
        if (!this.profileCanvas) return;

        const canvas = this.profileCanvas;
        const ctx = canvas.getContext('2d');
        const parent = canvas.parentElement;

        const width = Math.floor(parent ? parent.clientWidth : 600);
        const height = Math.floor(parent ? parent.clientHeight : 170);

        if (width <= 0 || height <= 0) return;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;

        ctx.save();
        ctx.scale(dpr, dpr);
        ctx.imageSmoothingEnabled = true;
        ctx.clearRect(0, 0, width, height);

        const currentTrack = (this.sagMetrics && this.sagMetrics.length > 0)
            ? (this.sagMetrics.find(m => parseInt(m.track_index, 10) === parseInt(this.selectedTrackIndex, 10)) || this.sagMetrics[0])
            : null;

        const paddingTop = 25;
        const paddingBottom = 25;
        const paddingLeft = 50;
        const paddingRight = 25;

        const chartW = width - paddingLeft - paddingRight;
        const chartH = height - paddingTop - paddingBottom;

        const s0 = 0.0;
        const s90 = (currentTrack && currentTrack.sag_90_mm !== undefined && currentTrack.sag_90_mm !== null) ? currentTrack.sag_90_mm : 0.0;
        const s180 = (currentTrack && currentTrack.sag_180_mm !== undefined && currentTrack.sag_180_mm !== null) ? currentTrack.sag_180_mm : 0.0;
        const s270 = (currentTrack && currentTrack.sag_270_mm !== undefined && currentTrack.sag_270_mm !== null) ? currentTrack.sag_270_mm : 0.0;

        const vals = [s0, s90, s180, s270];
        const absMax = Math.max(0.08, Math.abs(Math.min(...vals)), Math.abs(Math.max(...vals)), (currentTrack ? currentTrack.max_sag_mm : 0.08));
        const yMin = -absMax * 1.5;
        const yMax = absMax * 1.5;

        function valToY(v) {
            const norm = (v - yMin) / (yMax - yMin + 1e-6);
            return paddingTop + (1.0 - norm) * chartH;
        }

        function degToPx(deg) {
            return paddingLeft + (deg / 360.0) * chartW;
        }

        const zeroY = valToY(0);

        // Grid lines & Y-axis labels
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 1;

        [yMin, yMin / 2, 0, yMax / 2, yMax].forEach(v => {
            const py = valToY(v);
            ctx.beginPath();
            ctx.moveTo(paddingLeft, py);
            ctx.lineTo(paddingLeft + chartW, py);
            ctx.stroke();

            ctx.fillStyle = '#94a3b8';
            ctx.font = '10px Inter, sans-serif';
            ctx.textAlign = 'right';
            ctx.textBaseline = 'middle';
            ctx.fillText(`${v >= 0 ? '+' : ''}${v.toFixed(3)} mm`, paddingLeft - 6, py);
        });

        // Zero Baseline Line
        ctx.strokeStyle = 'rgba(0, 242, 254, 0.25)';
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(paddingLeft, zeroY);
        ctx.lineTo(paddingLeft + chartW, zeroY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Title Header
        const tIdx = currentTrack ? currentTrack.track_index : this.selectedTrackIndex;
        const bankStr = currentTrack ? (currentTrack.bank || '') : '';
        const pairNum = currentTrack ? currentTrack.pair_number : tIdx;
        const dlgStr = (currentTrack && currentTrack.baseline_0_dlg_mm !== undefined) ? ` | 0° DLG: ${currentTrack.baseline_0_dlg_mm >= 0 ? '+' : ''}${currentTrack.baseline_0_dlg_mm.toFixed(2)}mm` : '';
        
        ctx.font = '700 11px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillStyle = '#00f2fe';
        ctx.fillText(`Track ${tIdx} (${bankStr} Pair ${pairNum}) Gravitational Sag Vector vs Gantry Angle θ${dlgStr}`, paddingLeft, 12);

        // Draw Continuous Fitted Sine Wave S_i · sin(θ)
        ctx.strokeStyle = 'rgba(0, 242, 254, 0.7)';
        ctx.lineWidth = 2.0;
        ctx.beginPath();
        for (let deg = 0; deg <= 360; deg += 2) {
            const rad = (deg * Math.PI) / 180.0;
            const sag_val = absMax * Math.sin(rad);
            const px = degToPx(deg);
            const py = valToY(sag_val);
            if (deg === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        }
        ctx.stroke();

        // Connect Empirical Cardinal Measurements
        const keyPoints = [
            { deg: 0, val: s0 },
            { deg: 90, val: s90 },
            { deg: 180, val: s180 },
            { deg: 270, val: s270 },
            { deg: 360, val: s0 }
        ];

        ctx.strokeStyle = '#a855f7';
        ctx.lineWidth = 1.8;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        keyPoints.forEach((pt, idx) => {
            const px = degToPx(pt.deg);
            const py = valToY(pt.val);
            if (idx === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        });
        ctx.stroke();
        ctx.setLineDash([]);

        // Draw All 5 Cardinal Measurement Dots & Text Badges using Percentage Tolerance Colors
        keyPoints.forEach(pt => {
            const px = degToPx(pt.deg);
            const py = valToY(pt.val);
            const ptColor = this.getToleranceColor(pt.val);

            ctx.fillStyle = ptColor;
            ctx.beginPath();
            ctx.arc(px, py, 5.5, 0, 2 * Math.PI);
            ctx.fill();

            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            ctx.fillStyle = '#f8fafc';
            ctx.font = '700 9px Inter, sans-serif';
            ctx.textAlign = 'center';
            const signStr = pt.val >= 0 ? '+' : '';
            const yTextOffset = pt.val >= 0 ? -9 : 12;
            ctx.fillText(`${pt.deg}° (${signStr}${pt.val.toFixed(3)}mm)`, px, py + yTextOffset);
        });

        ctx.restore();
    }

    renderPanelCenterChart() {
        if (!this.panelCanvas) return;

        const canvas = this.panelCanvas;
        const ctx = canvas.getContext('2d');
        const parent = canvas.parentElement;

        const width = Math.floor(parent ? parent.clientWidth : 600);
        const height = Math.floor(parent ? parent.clientHeight : 170);

        if (width <= 0 || height <= 0) return;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;

        ctx.save();
        ctx.scale(dpr, dpr);
        ctx.imageSmoothingEnabled = true;
        ctx.clearRect(0, 0, width, height);

        const paddingTop = 25;
        const paddingBottom = 25;
        const paddingLeft = 50;
        const paddingRight = 25;

        const chartW = width - paddingLeft - paddingRight;
        const chartH = height - paddingTop - paddingBottom;

        const pOff = this.panelOffsets || {};
        
        function getDX(ang) {
            const p = pOff[ang] || pOff[String(ang)];
            return p ? (p.delta_x_panel_mm || 0.0) : 0.0;
        }

        function getDY(ang) {
            const p = pOff[ang] || pOff[String(ang)];
            return p ? (p.delta_y_panel_mm || 0.0) : 0.0;
        }

        const angles = [0, 90, 180, 270, 360];
        const dxVals = angles.map(a => getDX(a === 360 ? 0 : a));
        const dyVals = angles.map(a => getDY(a === 360 ? 0 : a));

        const allVals = [...dxVals, ...dyVals];
        const absMax = Math.max(0.5, Math.abs(Math.min(...allVals)), Math.abs(Math.max(...allVals)));
        const yMin = -absMax * 1.4;
        const yMax = absMax * 1.4;

        function valToY(v) {
            const norm = (v - yMin) / (yMax - yMin + 1e-6);
            return paddingTop + (1.0 - norm) * chartH;
        }

        function degToPx(deg) {
            return paddingLeft + (deg / 360.0) * chartW;
        }

        const zeroY = valToY(0);

        // Grid lines & Y-axis labels
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 1;

        [yMin, yMin / 2, 0, yMax / 2, yMax].forEach(v => {
            const py = valToY(v);
            ctx.beginPath();
            ctx.moveTo(paddingLeft, py);
            ctx.lineTo(paddingLeft + chartW, py);
            ctx.stroke();

            ctx.fillStyle = '#94a3b8';
            ctx.font = '10px Inter, sans-serif';
            ctx.textAlign = 'right';
            ctx.textBaseline = 'middle';
            ctx.fillText(`${v >= 0 ? '+' : ''}${v.toFixed(2)} mm`, paddingLeft - 6, py);
        });

        // Zero Baseline Line
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(paddingLeft, zeroY);
        ctx.lineTo(paddingLeft + chartW, zeroY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Legend & Title
        ctx.font = '700 11px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillStyle = '#00f2fe';
        ctx.fillText('EPID Panel Flex / CAX Center Shift vs. Gantry Angle θ', paddingLeft, 12);

        // Legend Pills (Cyan = ΔX, Amber = ΔY)
        ctx.fillStyle = '#00f2fe';
        ctx.fillRect(width - 120, 4, 10, 10);
        ctx.fillStyle = '#f8fafc';
        ctx.font = '600 9px Inter, sans-serif';
        ctx.fillText('ΔX_panel', width - 106, 12);

        ctx.fillStyle = '#f59e0b';
        ctx.fillRect(width - 60, 4, 10, 10);
        ctx.fillStyle = '#f8fafc';
        ctx.font = '600 9px Inter, sans-serif';
        ctx.fillText('ΔY_panel', width - 46, 12);

        // Draw ΔX_panel Line (Cyan `#00f2fe`)
        ctx.strokeStyle = '#00f2fe';
        ctx.lineWidth = 2.0;
        ctx.beginPath();
        angles.forEach((ang, i) => {
            const px = degToPx(ang);
            const py = valToY(dxVals[i]);
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        });
        ctx.stroke();

        // Draw ΔY_panel Line (Amber `#f59e0b`)
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 2.0;
        ctx.beginPath();
        angles.forEach((ang, i) => {
            const px = degToPx(ang);
            const py = valToY(dyVals[i]);
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        });
        ctx.stroke();

        // Draw Dots & Badges for ΔX_panel and ΔY_panel
        angles.forEach((ang, i) => {
            const px = degToPx(ang);
            const pyX = valToY(dxVals[i]);
            const pyY = valToY(dyVals[i]);

            // ΔX dot
            ctx.fillStyle = '#00f2fe';
            ctx.beginPath(); ctx.arc(px, pyX, 4.5, 0, 2 * Math.PI); ctx.fill();
            ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.0; ctx.stroke();

            // ΔY dot
            ctx.fillStyle = '#f59e0b';
            ctx.beginPath(); ctx.arc(px, pyY, 4.5, 0, 2 * Math.PI); ctx.fill();
            ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.0; ctx.stroke();

            // Text label
            ctx.fillStyle = '#94a3b8';
            ctx.font = '600 9px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(`${ang}°`, px, height - 6);
        });

        ctx.restore();
    }
}
