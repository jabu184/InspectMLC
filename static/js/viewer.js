/**
 * InspectMLC Canvas Viewer v6.0
 * Handles HiDPI synchronized image rendering, interactive mouse wheel zoom centered on cursor,
 * pan offsets, mouse click closest-track selection, All-Tracks sub-pixel edge display mode,
 * and User-Defined Percentage Tolerance Color Heatmaps (Green -> Yellow -> Orange -> Red).
 */
class ImageCanvasViewer {
    constructor(canvasId, overlayInfoId) {
        this.canvas = document.getElementById(canvasId);
        this.overlayInfo = document.getElementById(overlayInfoId);
        this.ctx = this.canvas ? this.canvas.getContext('2d') : null;

        this.imgObj = null;
        this.imgSrc = null;
        this.zoomScale = 1.0;
        this.panOffsetX = 0.0;
        this.panOffsetY = 0.0;
        
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;
        this.hasDragged = false;
        
        this.leafResults = [];
        this.selectedTrackIndex = 1;
        this.showAllTracks = false;
        this.activeGantryAngle = 0;
        this.activeImageType = 'MLC'; // 'MLC' or 'OPEN'

        this.warnThreshMm = 0.5;
        this.actionThreshMm = 1.0;

        this.onTrackClickCallback = null;

        if (this.canvas) {
            this.initEvents();
        }
    }

    setToleranceThresholds(warnMm, actionMm) {
        this.warnThreshMm = parseFloat(warnMm) || 0.5;
        this.actionThreshMm = parseFloat(actionMm) || 1.0;
        this.render();
    }

    setActiveGantryAngle(angle) {
        this.activeGantryAngle = parseFloat(angle) || 0;
        this.render();
    }

    setActiveImageType(type) {
        this.activeImageType = type || 'MLC';
        this.render();
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

    initEvents() {
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const rect = this.canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            
            const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
            const newScale = Math.max(0.5, Math.min(15.0, this.zoomScale * zoomFactor));
            
            if (newScale === 1.0) {
                this.panOffsetX = 0;
                this.panOffsetY = 0;
            } else {
                const centerX = rect.width / 2;
                const centerY = rect.height / 2;
                const scaleRatio = newScale / this.zoomScale;
                
                this.panOffsetX = (this.panOffsetX + centerX - mouseX) * scaleRatio + mouseX - centerX;
                this.panOffsetY = (this.panOffsetY + centerY - mouseY) * scaleRatio + mouseY - centerY;
            }
            
            this.zoomScale = newScale;
            this.render();
        }, { passive: false });

        this.canvas.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            this.isDragging = true;
            this.hasDragged = false;
            this.dragStartX = e.clientX - this.panOffsetX;
            this.dragStartY = e.clientY - this.panOffsetY;
        });

        window.addEventListener('mousemove', (e) => {
            if (!this.isDragging) return;
            this.hasDragged = true;
            this.panOffsetX = e.clientX - this.dragStartX;
            this.panOffsetY = e.clientY - this.dragStartY;
            this.render();
        });

        window.addEventListener('mouseup', () => {
            this.isDragging = false;
        });

        // Mouse click on canvas to select closest track
        this.canvas.addEventListener('click', (e) => {
            if (this.hasDragged || !this.imgObj) return;

            const rect = this.canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            const width = rect.width;
            const height = rect.height;
            const centerX = width / 2;
            const centerY = height / 2;

            const imgWidth = this.imgObj.width;
            const imgHeight = this.imgObj.height;

            const fitScale = Math.min(width / imgWidth, height / imgHeight) * 0.92;
            const scale = fitScale * this.zoomScale;

            const drawH = imgHeight * scale;
            const drawY = centerY - drawH / 2 + this.panOffsetY;

            // Convert click Y coordinate to image pixel Y
            const clickedImgY = (mouseY - drawY) / scale;

            if (this.leafResults && this.leafResults.length > 0) {
                let minDist = Infinity;
                let closestTrackIndex = this.selectedTrackIndex;

                this.leafResults.forEach(leaf => {
                    if (leaf.y_center_px !== undefined && leaf.y_center_px !== null) {
                        const dist = Math.abs(leaf.y_center_px - clickedImgY);
                        if (dist < minDist) {
                            minDist = dist;
                            closestTrackIndex = leaf.track_index;
                        }
                    }
                });

                this.selectedTrackIndex = parseInt(closestTrackIndex, 10);
                this.render();

                if (this.onTrackClickCallback) {
                    this.onTrackClickCallback(this.selectedTrackIndex);
                }
            }
        });

        this.canvas.addEventListener('mousemove', (e) => {
            if (!this.imgObj) return;
            const rect = this.canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            
            const imgX = Math.round((mouseX - centerX - this.panOffsetX) / this.zoomScale + this.imgObj.width / 2);
            const imgY = Math.round((mouseY - centerY - this.panOffsetY) / this.zoomScale + this.imgObj.height / 2);
            
            if (imgX >= 0 && imgX < this.imgObj.width && imgY >= 0 && imgY < this.imgObj.height) {
                if (this.overlayInfo) {
                    this.overlayInfo.textContent = `X: ${imgX} px | Y: ${imgY} px | Zoom: ${(this.zoomScale * 100).toFixed(0)}%`;
                }
            }
        });

        window.addEventListener('resize', () => this.render());
    }

    setImage(imgSrc, leafResults = [], selectedTrackIndex = 1) {
        if (!imgSrc) return;
        this.leafResults = leafResults || [];
        this.selectedTrackIndex = parseInt(selectedTrackIndex, 10) || 1;
        
        if (this.imgSrc === imgSrc && this.imgObj) {
            this.render();
            return;
        }

        this.imgSrc = imgSrc;
        const img = new Image();
        img.onload = () => {
            this.imgObj = img;
            this.render();
        };
        img.src = imgSrc;
    }

    setLeafResults(leafResults, selectedTrackIndex = 1) {
        this.leafResults = leafResults || [];
        this.selectedTrackIndex = parseInt(selectedTrackIndex, 10) || 1;
        this.render();
    }

    setSelectedTrackIndex(trackIdx) {
        this.selectedTrackIndex = parseInt(trackIdx, 10) || 1;
        this.render();
    }

    toggleShowAllTracks() {
        this.showAllTracks = !this.showAllTracks;
        this.render();
        return this.showAllTracks;
    }

    resetView() {
        this.zoomScale = 1.0;
        this.panOffsetX = 0.0;
        this.panOffsetY = 0.0;
        this.render();
    }

    getLeafSags(leaf) {
        if (!leaf) return { left: 0, right: 0 };
        const ang = Math.round(this.activeGantryAngle);
        let leftSag = 0;
        let rightSag = 0;

        if (ang === 90) {
            leftSag = leaf.sag_left_90_mm !== undefined ? leaf.sag_left_90_mm : (leaf.raw_left_shift_90_mm || 0);
            rightSag = leaf.sag_right_90_mm !== undefined ? leaf.sag_right_90_mm : (leaf.raw_right_shift_90_mm || 0);
        } else if (ang === 270) {
            leftSag = leaf.sag_left_270_mm !== undefined ? leaf.sag_left_270_mm : (leaf.raw_left_shift_270_mm || 0);
            rightSag = leaf.sag_right_270_mm !== undefined ? leaf.sag_right_270_mm : (leaf.raw_right_shift_270_mm || 0);
        } else {
            leftSag = leaf.max_leaf_sag_mm !== undefined ? leaf.max_leaf_sag_mm : (leaf.max_sag_mm || 0);
            rightSag = leaf.max_leaf_sag_mm !== undefined ? leaf.max_leaf_sag_mm : (leaf.max_sag_mm || 0);
        }

        return { left: leftSag, right: rightSag };
    }

    render() {
        if (!this.canvas || !this.ctx || !this.imgObj) return;

        const parent = this.canvas.parentElement;
        const width = Math.floor(parent ? parent.clientWidth : 600);
        const height = Math.floor(parent ? parent.clientHeight : 480);

        if (width <= 0 || height <= 0) return;

        const dpr = window.devicePixelRatio || 1;
        const targetW = Math.floor(width * dpr);
        const targetH = Math.floor(height * dpr);

        if (this.canvas.width !== targetW || this.canvas.height !== targetH) {
            this.canvas.width = targetW;
            this.canvas.height = targetH;
            this.canvas.style.width = `${width}px`;
            this.canvas.style.height = `${height}px`;
        }

        const ctx = this.ctx;
        ctx.save();
        ctx.scale(dpr, dpr);
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';

        ctx.fillStyle = '#050811';
        ctx.fillRect(0, 0, width, height);

        const centerX = width / 2;
        const centerY = height / 2;

        const imgWidth = this.imgObj.width;
        const imgHeight = this.imgObj.height;

        const fitScale = Math.min(width / imgWidth, height / imgHeight) * 0.92;
        const scale = fitScale * this.zoomScale;

        const drawW = imgWidth * scale;
        const drawH = imgHeight * scale;

        const drawX = centerX - drawW / 2 + this.panOffsetX;
        const drawY = centerY - drawH / 2 + this.panOffsetY;

        ctx.drawImage(this.imgObj, drawX, drawY, drawW, drawH);

        const currSelIdx = parseInt(this.selectedTrackIndex, 10) || 1;
        const isMlcImage = (this.activeImageType === 'MLC');
        const ang = Math.round(this.activeGantryAngle);
        const isSagAngle = (ang === 90 || ang === 270);
        const shouldOverlayLeafResults = isMlcImage && isSagAngle;

        if (!shouldOverlayLeafResults) {
            ctx.restore();
            return;
        }

        // 1. Draw background track guides / edge markers for all non-selected tracks
        if (this.leafResults && this.leafResults.length > 0) {
            this.leafResults.forEach((leaf) => {
                const isSelected = (parseInt(leaf.track_index, 10) === currSelIdx);
                if (isSelected) return;

                const leafY_img = leaf.y_center_px;
                if (leafY_img === undefined || leafY_img === null) return;
                const canvasY = drawY + (leafY_img / imgHeight) * drawH;

                ctx.shadowBlur = 0;
                ctx.lineWidth = this.showAllTracks ? 1.5 : 1.0;
                ctx.strokeStyle = leaf.status === 'FAIL' ? 'rgba(239, 68, 68, 0.4)' : (leaf.status === 'WARN' ? 'rgba(245, 158, 11, 0.3)' : 'rgba(255, 255, 255, 0.12)');

                ctx.beginPath();
                ctx.moveTo(drawX, canvasY);
                ctx.lineTo(drawX + drawW, canvasY);
                ctx.stroke();

                // If Show All Tracks is enabled, render dynamic percentage tolerance color dots for every track
                if (this.showAllTracks && leaf.x_left_px !== undefined && leaf.x_left_px !== null && leaf.x_right_px !== undefined && leaf.x_right_px !== null) {
                    const canvasX_left = drawX + (leaf.x_left_px / imgWidth) * drawW;
                    const canvasX_right = drawX + (leaf.x_right_px / imgWidth) * drawW;

                    const sags = this.getLeafSags(leaf);
                    const colorLeft = this.getToleranceColor(sags.left);
                    const colorRight = this.getToleranceColor(sags.right);

                    ctx.fillStyle = colorLeft;
                    ctx.beginPath();
                    ctx.arc(canvasX_left, canvasY, 3.5, 0, 2 * Math.PI);
                    ctx.fill();

                    ctx.fillStyle = colorRight;
                    ctx.beginPath();
                    ctx.arc(canvasX_right, canvasY, 3.5, 0, 2 * Math.PI);
                    ctx.fill();
                }
            });
        }

        // 2. PROMINENT SELECTED TRACK HIGHLIGHT LINE & GRADUATED LEAF EDGES
        let selectedTrackMatch = null;
        let selectedY_px = null;
        let selectedLabel = `Track ${currSelIdx}`;

        if (this.leafResults && this.leafResults.length > 0) {
            selectedTrackMatch = this.leafResults.find(t => parseInt(t.track_index, 10) === currSelIdx);
            if (selectedTrackMatch && selectedTrackMatch.y_center_px !== undefined && selectedTrackMatch.y_center_px !== null) {
                selectedY_px = selectedTrackMatch.y_center_px;
                selectedLabel = selectedTrackMatch.label || `Track ${currSelIdx}`;
            }
        }

        // Fallback geometry calculation if leafResults is empty
        if (selectedY_px === null) {
            const dy = 0.3733;
            const iso_y = imgHeight / 2.0;

            if (imgHeight === 768 || imgHeight === 1024) {
                const y_positions_mm = [];
                for (let i = 0; i < 10; i++) y_positions_mm.push(-195.0 + i * 10.0);
                for (let i = 0; i < 40; i++) y_positions_mm.push(-97.5 + i * 5.0);
                for (let i = 0; i < 10; i++) y_positions_mm.push(105.0 + i * 10.0);

                const tIdx = Math.max(1, Math.min(60, currSelIdx));
                const y_mm = y_positions_mm[tIdx - 1] || 0.0;
                selectedY_px = iso_y + (y_mm / dy);
                selectedLabel = `Leaf Pair ${tIdx}`;
            } else {
                const pitch_px = 5.0 / 0.336;
                const tIdx = Math.max(1, Math.min(57, currSelIdx));
                selectedY_px = iso_y + (tIdx - 28.5) * pitch_px;
                selectedLabel = `Track ${tIdx}`;
            }
        }

        if (selectedY_px !== null) {
            const canvasY = drawY + (selectedY_px / imgHeight) * drawH;

            // Calculate Graduated Colors for Left (Bank A) & Right (Bank B) Leaves
            const sags = this.getLeafSags(selectedTrackMatch);
            const colorLeft = this.getToleranceColor(sags.left);
            const colorRight = this.getToleranceColor(sags.right);
            const absMaxSag = Math.max(Math.abs(sags.left || 0), Math.abs(sags.right || 0));
            const colorWorst = this.getToleranceColor(absMaxSag);

            // Outer glow horizontal line across canvas
            ctx.shadowColor = colorWorst;
            ctx.shadowBlur = 12;
            ctx.lineWidth = 3.5;
            ctx.strokeStyle = colorWorst;

            ctx.beginPath();
            ctx.moveTo(drawX, canvasY);
            ctx.lineTo(drawX + drawW, canvasY);
            ctx.stroke();
            ctx.shadowBlur = 0;

            // Draw Track Badge at Left Edge
            ctx.fillStyle = colorWorst;
            ctx.fillRect(drawX + 8, canvasY - 11, 105, 22);
            ctx.fillStyle = '#0f172a';
            ctx.font = '700 11px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(selectedLabel, drawX + 60, canvasY);

            // 3. DRAW SUB-PIXEL MLC LEAF EDGES & MARKERS WITH GRADUATED COLORS
            if (selectedTrackMatch) {
                const xLeftPx = selectedTrackMatch.x_left_px;
                const xRightPx = selectedTrackMatch.x_right_px;
                const xRawPx = selectedTrackMatch.x_raw_px;
                const xLeftMm = selectedTrackMatch.x_left_mm;
                const xRightMm = selectedTrackMatch.x_right_mm;
                const gapMm = selectedTrackMatch.aperture_width_mm;

                if (xLeftPx !== undefined && xLeftPx !== null && xRightPx !== undefined && xRightPx !== null) {
                    const canvasX_left = drawX + (xLeftPx / imgWidth) * drawW;
                    const canvasX_right = drawX + (xRightPx / imgWidth) * drawW;
                    const canvasX_center = xRawPx ? (drawX + (xRawPx / imgWidth) * drawW) : (canvasX_left + canvasX_right) / 2.0;

                    const tickH = 16;

                    // Left MLC Leaf Bank Tip (Graduated Color Tick & Dot)
                    ctx.strokeStyle = colorLeft;
                    ctx.lineWidth = 4.0;
                    ctx.beginPath();
                    ctx.moveTo(canvasX_left, canvasY - tickH);
                    ctx.lineTo(canvasX_left, canvasY + tickH);
                    ctx.stroke();

                    ctx.fillStyle = colorLeft;
                    ctx.beginPath();
                    ctx.arc(canvasX_left, canvasY, 6.5, 0, 2 * Math.PI);
                    ctx.fill();

                    // Right MLC Leaf Bank Tip (Graduated Color Tick & Dot)
                    ctx.strokeStyle = colorRight;
                    ctx.lineWidth = 4.0;
                    ctx.beginPath();
                    ctx.moveTo(canvasX_right, canvasY - tickH);
                    ctx.lineTo(canvasX_right, canvasY + tickH);
                    ctx.stroke();

                    ctx.fillStyle = colorRight;
                    ctx.beginPath();
                    ctx.arc(canvasX_right, canvasY, 6.5, 0, 2 * Math.PI);
                    ctx.fill();

                    // Slit Center (Yellow Vertical Dashed Line)
                    ctx.strokeStyle = '#eab308';
                    ctx.lineWidth = 2.0;
                    ctx.setLineDash([4, 4]);
                    ctx.beginPath();
                    ctx.moveTo(canvasX_center, canvasY - tickH - 6);
                    ctx.lineTo(canvasX_center, canvasY + tickH + 6);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    // Floating Sub-Pixel Edge Metric Badge above aperture
                    const badgeText = `Left Sag: ${sags.left >= 0 ? '+' : ''}${sags.left.toFixed(2)}mm | Right Sag: ${sags.right >= 0 ? '+' : ''}${sags.right.toFixed(2)}mm | Gap: ${gapMm !== null ? gapMm.toFixed(2) : '--'}mm`;
                    ctx.font = '600 10px Inter, sans-serif';
                    const textW = ctx.measureText(badgeText).width + 16;
                    
                    const badgeX = canvasX_center - textW / 2;
                    const badgeY = canvasY - 24;

                    ctx.fillStyle = 'rgba(15, 23, 42, 0.94)';
                    ctx.strokeStyle = colorWorst;
                    ctx.lineWidth = 1.5;
                    ctx.fillRect(badgeX, badgeY - 10, textW, 20);
                    ctx.strokeRect(badgeX, badgeY - 10, textW, 20);

                    ctx.fillStyle = '#f8fafc';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(badgeText, canvasX_center, badgeY);
                }
            }
        }

        ctx.restore();
    }
}
