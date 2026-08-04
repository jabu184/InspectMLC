/**
 * Anti-Gravity QC Main Controller v12.0
 * Multi-Platform MLC Gravitational QC & DLG Engine
 * Supports Varian TrueBeam Millennium 120 (60 Leaf Pairs / 120 Leaves) & Halcyon Dual-Layer SX2/SX1 (114 Leaves).
 * Features Native Windows Directory Selection Dialog, Completeness-Gated 'Run Analysis' Action Button,
 * QATrack+ Settings & REST API Integration Engine with Automatic Payload Generation and Push Logging,
 * EPID Leaf Overlay Suppression for Open Fields / 0° / 180°, User-Defined Tolerance Inputs & 4-Color Heatmaps.
 */
document.addEventListener('DOMContentLoaded', () => {
    const viewer = new ImageCanvasViewer('canvas-viewer', 'viewer-overlay-info');
    const charts = new MLCChartsRenderer();

    let currentSagAnalysisData = null;
    let selectedTrackIndex = 1;
    let activeGantryAngleIndex = 0; // 0: 0°, 1: 90°, 2: 180°, 3: 270°
    let activeImageType = 'MLC'; // 'MLC' or 'OPEN'
    let activeTableViewMode = 'LEAF'; // 'CENTER' or 'LEAF'
    let activeBankFilter = 'DISTAL'; // 'DISTAL', 'PROXIMAL', or 'ALL'

    // Directory Watcher & Browse Elements
    const inputWatchFolder = document.getElementById('input-watch-folder');
    const btnBrowseFolderTrigger = document.getElementById('btn-browse-folder-trigger');

    const chkLiveWatch = document.getElementById('chk-live-watch');
    
    const lblChecklistTitle = document.getElementById('lbl-checklist-title');
    const lblWatchedCount = document.getElementById('lbl-watched-count');
    const expectedFieldsGrid = document.getElementById('expected-fields-checklist-grid');
    const unmappedContainer = document.getElementById('unmapped-files-warning-container');
    const unmappedList = document.getElementById('unmapped-files-list');

    let watchTimer = null;
    let lastWatchedFolderData = null;

    // Manual Tolerance Inputs
    const inputWarnSag = document.getElementById('input-warn-sag');
    const inputActionSag = document.getElementById('input-action-sag');

    function getWarnTolerance() {
        return inputWarnSag ? (parseFloat(inputWarnSag.value) || 0.5) : 0.5;
    }

    function getActionTolerance() {
        return inputActionSag ? (parseFloat(inputActionSag.value) || 1.0) : 1.0;
    }

    function getToleranceColor(sagMm) {
        if (sagMm === undefined || sagMm === null) return '#10b981';
        const absSag = Math.abs(sagMm);
        const tw = Math.max(0.01, getWarnTolerance());
        const ta = Math.max(tw, getActionTolerance());

        if (absSag < 0.5 * tw) {
            return '#10b981'; // Green (<50% of Warning Tolerance)
        } else if (absSag < tw) {
            return '#eab308'; // Yellow (50% to 100% of Warning Tolerance)
        } else if (absSag < ta) {
            return '#f97316'; // Orange (100% to Action Tolerance)
        } else {
            return '#ef4444'; // Red (>= Action Level)
        }
    }

    function updateToleranceColorsAndLegend() {
        const warnMm = getWarnTolerance();
        const actionMm = getActionTolerance();

        const halfWarn = (warnMm / 2.0).toFixed(2);
        const warnStr = warnMm.toFixed(2);
        const actionStr = actionMm.toFixed(2);

        const legPass = document.getElementById('leg-pass');
        const legCaution = document.getElementById('leg-caution');
        const legWarn = document.getElementById('leg-warn');
        const legFail = document.getElementById('leg-fail');

        if (legPass) legPass.textContent = `🟢 <50% Warn (<${halfWarn}mm)`;
        if (legCaution) legCaution.textContent = `🟡 50–100% Warn (${halfWarn}–${warnStr}mm)`;
        if (legWarn) legWarn.textContent = `🟠 100–200% Warn (${warnStr}–${actionStr}mm)`;
        if (legFail) legFail.textContent = `🔴 ≥Action Level (≥${actionStr}mm)`;

        viewer.setToleranceThresholds(warnMm, actionMm);
        charts.setToleranceThresholds(warnMm, actionMm);

        if (currentSagAnalysisData) {
            const filteredMetrics = filterByActiveBank(currentSagAnalysisData.combined_metrics);
            renderAntiGravityTable(filteredMetrics);
        }
    }

    if (inputWarnSag) inputWarnSag.addEventListener('input', updateToleranceColorsAndLegend);
    if (inputActionSag) inputActionSag.addEventListener('input', updateToleranceColorsAndLegend);

    // Interactive Canvas Mouse Click Handler
    viewer.onTrackClickCallback = (trackIdx) => {
        selectTrack(trackIdx);
    };

    // Navigation Tabs
    const navAnalysis = document.getElementById('nav-tab-analysis');
    const navSimulator = document.getElementById('nav-tab-simulator');
    const navFluence = document.getElementById('nav-tab-fluence');
    const navSettings = document.getElementById('nav-tab-settings');

    const sectionAnalysis = document.getElementById('section-analysis');
    const sectionSimulator = document.getElementById('section-simulator');
    const sectionFluence = document.getElementById('section-fluence');
    const sectionSettings = document.getElementById('section-settings');

    // Quick Load Ethos Button & Action Buttons
    const btnQuickEthos = document.getElementById('btn-quick-ethos');
    const btnRunSagAnalysis = document.getElementById('btn-run-sag-analysis');
    const btnPushQATrack = document.getElementById('btn-push-qatrack');
    const btnPushQATrackNow = document.getElementById('btn-push-qatrack-now');

    // Machine Architecture Selector & Containers
    const selectMachineType = document.getElementById('select-machine-type');
    const machineDescBox = document.getElementById('machine-desc-box');

    // Options
    const chkOpenRatio = document.getElementById('chk-open-ratio');
    const chkMagCorr = document.getElementById('chk-mag-corr');
    const chkAutoFlex = document.getElementById('chk-auto-flex');

    // Buttons
    const btnResetView = document.getElementById('btn-reset-view');
    const btnToggleAllTracks = document.getElementById('btn-toggle-all-tracks');

    // Halcyon Leaf Bank Filter Tabs
    const btnBankDistal = document.getElementById('btn-bank-distal');
    const btnBankProximal = document.getElementById('btn-bank-proximal');
    const btnBankAll = document.getElementById('btn-bank-all');

    // Table View Tabs
    const tabTableCenter = document.getElementById('tab-table-center');
    const tabTableLeaf = document.getElementById('tab-table-leaf');

    // Per-Leaf Modal Elements
    const perLeafModal = document.getElementById('per-leaf-modal');
    const modalTrackTitle = document.getElementById('modal-track-title');
    const modalTrackContent = document.getElementById('modal-track-content');
    const btnCloseModal = document.getElementById('btn-close-modal');

    // KPI Elements
    const kpiPassRate = document.getElementById('kpi-pass-rate');
    const kpiDlgVal = document.getElementById('kpi-dlg-val');
    const kpiDlgSub = document.getElementById('kpi-dlg-sub');
    const kpiMaxSag = document.getElementById('kpi-max-sag');
    const kpiMaxLeafSag = document.getElementById('kpi-max-leaf-sag');
    const kpiMaxLeafSub = document.getElementById('kpi-max-leaf-sub');
    const kpiMaxFluence = document.getElementById('kpi-max-fluence');
    const kpiFlexStatus = document.getElementById('kpi-flex-status');
    const kpiLinacSub = document.getElementById('kpi-linac-sub');

    // Viewer Mode Sub-Tabs (MLC Slit vs Open Field)
    const tabImgMlc = document.getElementById('tab-img-mlc');
    const tabImgOpen = document.getElementById('tab-img-open');

    // Gantry View Tabs
    const tabGantry0 = document.getElementById('tab-gantry-0');
    const tabGantry90 = document.getElementById('tab-gantry-90');
    const tabGantry180 = document.getElementById('tab-gantry-180');
    const tabGantry270 = document.getElementById('tab-gantry-270');

    // Table Tbody & Head
    const tableHead = document.getElementById('table-head');
    const tableBody = document.querySelector('#table-leaf-results tbody');

    // Settings Elements
    const settingQATrackUrl = document.getElementById('setting-qatrack-url');
    const settingQATrackToken = document.getElementById('setting-qatrack-token');
    const settingQATrackUnit = document.getElementById('setting-qatrack-unit');
    const settingQATrackTestList = document.getElementById('setting-qatrack-testlist');
    const settingQATrackUTC = document.getElementById('setting-qatrack-utc');

    const settingTempVal = document.getElementById('setting-temp-val');
    const settingPressVal = document.getElementById('setting-press-val');

    const settingMacroMaxSag = document.getElementById('setting-macro-max-sag');
    const settingMacroMaxLeafSag = document.getElementById('setting-macro-max-leaf-sag');
    const settingMacroPassRate = document.getElementById('setting-macro-pass-rate');
    const settingMacroDlgBaseline = document.getElementById('setting-macro-dlg-baseline');
    const settingMacroMaxFluence = document.getElementById('setting-macro-max-fluence');
    const settingMacroQCStatus = document.getElementById('setting-macro-qc-status');

    const btnTestQATrackConn = document.getElementById('btn-test-qatrack-conn');
    const btnSaveQATrackSettings = document.getElementById('btn-save-qatrack-settings');
    const qatrackLogOutput = document.getElementById('qatrack-log-output');

    // ----------------------------------------------------
    // NATIVE WINDOWS FOLDER SELECTION BOX HANDLER
    // ----------------------------------------------------
    if (btnBrowseFolderTrigger) {
        btnBrowseFolderTrigger.addEventListener('click', () => {
            btnBrowseFolderTrigger.innerHTML = `⏳ Opening...`;
            btnBrowseFolderTrigger.disabled = true;

            fetch('/api/open-folder-dialog', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    btnBrowseFolderTrigger.innerHTML = `📁 Browse Windows...`;
                    btnBrowseFolderTrigger.disabled = false;

                    if (data.status === 'success' && !data.canceled && data.folder_path) {
                        if (inputWatchFolder) inputWatchFolder.value = data.folder_path;
                        pollWatchedFolder(false);
                    }
                })
                .catch(err => {
                    btnBrowseFolderTrigger.innerHTML = `📁 Browse Windows...`;
                    btnBrowseFolderTrigger.disabled = false;
                    console.error("Native folder dialog error:", err);
                });
        });
    }

    // ----------------------------------------------------
    // REAL-TIME EXPECTED FIELDS CHECKLIST WATCHER LOGIC
    // ----------------------------------------------------
    const slotDefinitions = {
        'HALCYON': [
            { key: 'dist_0', title: '0° Distal MLC (SX2)' },
            { key: 'prox_0', title: '0° Proximal MLC (SX1)' },
            { key: 'open_0', title: '0° Open Field' },

            { key: 'dist_90', title: '90° Distal MLC (SX2)' },
            { key: 'prox_90', title: '90° Proximal MLC (SX1)' },
            { key: 'open_90', title: '90° Open Field' },

            { key: 'dist_180', title: '180° Distal MLC (SX2)' },
            { key: 'prox_180', title: '180° Proximal MLC (SX1)' },
            { key: 'open_180', title: '180° Open Field' },

            { key: 'dist_270', title: '270° Distal MLC (SX2)' },
            { key: 'prox_270', title: '270° Proximal MLC (SX1)' },
            { key: 'open_270', title: '270° Open Field' }
        ],
        'TRUEBEAM': [
            { key: 'dist_0', title: '0° Dynamic MLC Slit' },
            { key: 'open_0', title: '0° Open Field' },

            { key: 'dist_90', title: '90° Dynamic MLC Slit' },
            { key: 'open_90', title: '90° Open Field' },

            { key: 'dist_180', title: '180° Dynamic MLC Slit' },
            { key: 'open_180', title: '180° Open Field' },

            { key: 'dist_270', title: '270° Dynamic MLC Slit' },
            { key: 'open_270', title: '270° Open Field' }
        ]
    };

    let manualUploadedSlots = {};

    function clearAnalysisResults() {
        currentSagAnalysisData = null;
        if (kpiPassRate) {
            kpiPassRate.textContent = '--';
            kpiPassRate.className = 'kpi-value';
        }
        if (kpiDlgVal) kpiDlgVal.textContent = '--';
        if (kpiDlgSub) kpiDlgSub.textContent = '--';
        if (kpiMaxSag) kpiMaxSag.textContent = '--';
        if (kpiMaxLeafSag) kpiMaxLeafSag.textContent = '--';
        if (kpiMaxLeafSub) kpiMaxLeafSub.textContent = '--';
        if (kpiMaxFluence) kpiMaxFluence.textContent = '--';

        if (tableBody) tableBody.innerHTML = '';
        if (tableHead) tableHead.innerHTML = '';

        if (typeof charts !== 'undefined' && charts && charts.setSagResults) {
            charts.setSagResults([], {}, null, null);
        }
        if (typeof viewer !== 'undefined' && viewer && viewer.setLeafResults) {
            viewer.setLeafResults([], null);
        }
        updateViewerImage();
    }

    function pollWatchedFolder(autoRunAnalysis = false) {
        const folderPath = inputWatchFolder ? inputWatchFolder.value.trim() : '';
        const machineType = selectMachineType ? selectMachineType.value : 'HALCYON';
        const expectedList = slotDefinitions[machineType] || slotDefinitions['HALCYON'];

        const processFolderData = (data) => {
            lastWatchedFolderData = data || { status: 'success', mapped_slots: {}, is_complete: false };

            let mappedCount = 0;
            expectedList.forEach(slotDef => {
                if (manualUploadedSlots[slotDef.key] || (lastWatchedFolderData.mapped_slots && lastWatchedFolderData.mapped_slots[slotDef.key])) {
                    mappedCount++;
                }
            });

            const isAllComplete = (mappedCount >= expectedList.length);

            if (lblWatchedCount) {
                if (isAllComplete) {
                    lblWatchedCount.className = 'badge-pill PASS';
                    lblWatchedCount.style.background = 'rgba(16,185,129,0.2)';
                    lblWatchedCount.style.color = '#10b981';
                    lblWatchedCount.textContent = `🟢 All ${expectedList.length} Fields Ready`;
                } else if (mappedCount > 0) {
                    lblWatchedCount.className = 'badge-pill WARN';
                    lblWatchedCount.style.background = 'rgba(245,158,11,0.2)';
                    lblWatchedCount.style.color = '#f59e0b';
                    lblWatchedCount.textContent = `🟡 ${mappedCount} of ${expectedList.length} Mapped`;
                } else {
                    lblWatchedCount.className = 'badge-pill WARN';
                    lblWatchedCount.style.background = 'rgba(148,163,184,0.2)';
                    lblWatchedCount.style.color = '#94a3b8';
                    lblWatchedCount.textContent = `⚪ ${mappedCount} of ${expectedList.length} Mapped`;
                }
            }

            if (btnRunSagAnalysis) {
                btnRunSagAnalysis.disabled = false;
                btnRunSagAnalysis.style.opacity = '1';
                btnRunSagAnalysis.style.cursor = 'pointer';
            }

            // Render Live Expected Field Checklist Grid Cards with Manual Upload option per slot
            if (expectedFieldsGrid) {
                expectedFieldsGrid.innerHTML = '';
                expectedList.forEach(slotDef => {
                    const manualMatch = manualUploadedSlots[slotDef.key];
                    const folderMatch = lastWatchedFolderData.mapped_slots ? lastWatchedFolderData.mapped_slots[slotDef.key] : null;
                    const fileMatch = manualMatch || folderMatch;
                    const isManual = !!manualMatch;

                    const card = document.createElement('div');

                    if (fileMatch) {
                        const displayFileName = fileMatch.filename || (typeof fileMatch === 'string' ? fileMatch.split('/').pop().split('\\').pop() : 'DICOM Image');
                        card.style.cssText = isManual
                            ? 'background: rgba(168, 85, 247, 0.15); border: 1px solid #a855f7; padding: 0.45rem 0.65rem; border-radius: 6px; font-size: 0.76rem; color: #f8fafc;'
                            : 'background: rgba(16, 185, 129, 0.12); border: 1px solid #10b981; padding: 0.45rem 0.65rem; border-radius: 6px; font-size: 0.76rem; color: #f8fafc;';
                        card.innerHTML = `
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.3rem;">
                                <span style="font-weight: 700; color: ${isManual ? '#c084fc' : '#10b981'};">
                                    ${isManual ? '📌' : '✅'} ${slotDef.title}
                                </span>
                                <div style="display: flex; align-items: center; gap: 0.25rem;">
                                    ${isManual ? `<span style="font-size: 0.62rem; background: rgba(168,85,247,0.3); color: #c084fc; font-weight: 700; padding: 0.08rem 0.3rem; border-radius: 3px;">MANUAL UPLOAD</span>` : `<span style="font-size: 0.62rem; color: #34d399; font-weight: 700;">FOLDER</span>`}
                                    <button type="button" class="btn-slot-upload" data-slot="${slotDef.key}" style="background: rgba(0, 242, 254, 0.15); border: 1px solid #00f2fe; color: #00f2fe; font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 3px; cursor: pointer;" title="Upload custom DICOM file for ${slotDef.title}">
                                        📤 Upload
                                    </button>
                                    ${isManual ? `<button type="button" class="btn-slot-clear" data-slot="${slotDef.key}" style="background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 3px; cursor: pointer;" title="Clear manual upload override">✕</button>` : ''}
                                </div>
                            </div>
                            <div style="font-size: 0.71rem; color: ${isManual ? '#e9d5ff' : '#94a3b8'}; margin-top: 0.2rem; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
                                📄 ${displayFileName}
                            </div>
                            <input type="file" id="file-input-slot-${slotDef.key}" accept=".dcm,.dicom,image/*" style="display: none;">
                        `;
                    } else {
                        card.style.cssText = 'background: #0f172a; border: 1px dashed #334155; padding: 0.45rem 0.65rem; border-radius: 6px; font-size: 0.76rem; color: #64748b;';
                        card.innerHTML = `
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.3rem;">
                                <span style="font-weight: 600; color: #94a3b8;">⏳ ${slotDef.title}</span>
                                <div style="display: flex; align-items: center; gap: 0.25rem;">
                                    <span style="font-size: 0.65rem; color: #f59e0b;">AWAITING</span>
                                    <button type="button" class="btn-slot-upload" data-slot="${slotDef.key}" style="background: rgba(0, 242, 254, 0.15); border: 1px solid #00f2fe; color: #00f2fe; font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 3px; cursor: pointer;" title="Upload custom DICOM file for ${slotDef.title}">
                                        📤 Upload
                                    </button>
                                </div>
                            </div>
                            <div style="font-size: 0.71rem; color: #475569; margin-top: 0.2rem;">
                                Waiting for DICOM image...
                            </div>
                            <input type="file" id="file-input-slot-${slotDef.key}" accept=".dcm,.dicom,image/*" style="display: none;">
                        `;
                    }

                    expectedFieldsGrid.appendChild(card);

                    const uploadBtn = card.querySelector(`.btn-slot-upload[data-slot="${slotDef.key}"]`);
                    const fileInput = card.querySelector(`#file-input-slot-${slotDef.key}`);
                    const clearBtn = card.querySelector(`.btn-slot-clear[data-slot="${slotDef.key}"]`);

                    if (uploadBtn) {
                        uploadBtn.addEventListener('click', (e) => {
                            e.stopPropagation();
                            e.preventDefault();

                            fetch('/api/open-file-dialog', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ target_slot: slotDef.key })
                            })
                            .then(res => res.json())
                            .then(uploadData => {
                                if (uploadData.status === 'success') {
                                    if (uploadData.canceled) return;
                                    if (uploadData.saved_path) {
                                        manualUploadedSlots[slotDef.key] = {
                                            filename: uploadData.original_filename || uploadData.saved_path.split('\\').pop(),
                                            saved_path: uploadData.saved_path,
                                            is_manual: true
                                        };
                                        clearAnalysisResults();
                                        pollWatchedFolder(false);
                                        return;
                                    }
                                }
                                if (fileInput) fileInput.click();
                            })
                            .catch(() => {
                                if (fileInput) fileInput.click();
                            });
                        });
                    }

                    if (fileInput) {
                        fileInput.addEventListener('change', (e) => {
                            if (!e.target.files || e.target.files.length === 0) return;
                            const file = e.target.files[0];
                            const formData = new FormData();
                            formData.append('file', file);
                            formData.append('target_slot', slotDef.key);

                            fetch('/api/upload-field-image', {
                                method: 'POST',
                                body: formData
                            })
                            .then(res => res.json())
                            .then(uploadData => {
                                if (uploadData.status === 'success' || uploadData.saved_path) {
                                    manualUploadedSlots[slotDef.key] = {
                                        filename: uploadData.original_filename || file.name,
                                        saved_path: uploadData.saved_path,
                                        is_manual: true
                                    };
                                    clearAnalysisResults();
                                    pollWatchedFolder(false);
                                } else {
                                    alert("Upload failed: " + (uploadData.detail || "Error"));
                                }
                            })
                            .catch(err => alert("Upload error: " + err));
                        });
                    }

                    if (clearBtn) {
                        clearBtn.addEventListener('click', (e) => {
                            e.stopPropagation();
                            delete manualUploadedSlots[slotDef.key];
                            clearAnalysisResults();
                            pollWatchedFolder(false);
                        });
                    }
                });
            }

            // Render Unmapped / Ambiguous DICOM Warning Alert (Exclamation Alert ⚠️)
            if (unmappedContainer && unmappedList) {
                const unmapped = data.unmapped_files || [];
                if (unmapped.length > 0) {
                    unmappedContainer.style.display = 'block';
                    unmappedList.innerHTML = '';
                    unmapped.forEach(uf => {
                        const badge = document.createElement('span');
                        badge.style.cssText = 'background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; font-weight: 700; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.72rem; display: inline-flex; align-items: center; gap: 0.3rem;';
                        badge.innerHTML = `⚠️ <strong>${uf.filename}</strong> (${uf.raw_label || 'Unmapped / Ambiguous'})`;
                        unmappedList.appendChild(badge);
                    });
                } else {
                    unmappedContainer.style.display = 'none';
                }
            }

            updateViewerImage();

            if (autoRunAnalysis && isAllComplete) {
                runAntiGravityAnalysis();
            }
        };

        if (!folderPath) {
            if (lblWatchedCount && Object.keys(manualUploadedSlots).length === 0) {
                lblWatchedCount.textContent = '⚪ No Folder Selected';
            }
            processFolderData({ status: 'success', mapped_slots: {}, is_complete: false });
            return;
        }

        fetch('/api/watch-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                folder_path: folderPath,
                machine_type: machineType
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                processFolderData(data);
            } else {
                if (lblWatchedCount) {
                    lblWatchedCount.textContent = `🔴 Directory Error: ${data.detail || 'Error'}`;
                }
            }
        })
        .catch(err => console.error("Folder watcher error:", err));
    }

    function setupDirectoryWatcherTimer() {
        if (watchTimer) clearInterval(watchTimer);
        if (chkLiveWatch && chkLiveWatch.checked) {
            watchTimer = setInterval(() => {
                pollWatchedFolder(false);
            }, 3000);
        }
    }

    if (chkLiveWatch) {
        chkLiveWatch.addEventListener('change', setupDirectoryWatcherTimer);
    }

    if (inputWatchFolder) {
        inputWatchFolder.addEventListener('change', () => {
            pollWatchedFolder(false);
        });
    }

    // Initial Watcher Start
    pollWatchedFolder(false);
    setupDirectoryWatcherTimer();

    function switchTab(targetTab) {
        if (navAnalysis) navAnalysis.className = targetTab === 'analysis' ? 'btn active' : 'btn btn-secondary';
        if (navSimulator) navSimulator.className = targetTab === 'simulator' ? 'btn active' : 'btn btn-secondary';
        if (navFluence) navFluence.className = targetTab === 'fluence' ? 'btn active' : 'btn btn-secondary';
        if (navSettings) navSettings.className = targetTab === 'settings' ? 'btn active' : 'btn btn-secondary';

        if (sectionAnalysis) sectionAnalysis.style.display = targetTab === 'analysis' ? 'block' : 'none';
        if (sectionSimulator) sectionSimulator.style.display = targetTab === 'simulator' ? 'block' : 'none';
        if (sectionFluence) sectionFluence.style.display = targetTab === 'fluence' ? 'block' : 'none';
        if (sectionSettings) sectionSettings.style.display = targetTab === 'settings' ? 'block' : 'none';
    }

    if (navAnalysis) navAnalysis.onclick = () => switchTab('analysis');
    if (navSimulator) navSimulator.onclick = () => switchTab('simulator');
    if (navFluence) navFluence.onclick = () => switchTab('fluence');
    if (navSettings) navSettings.onclick = () => switchTab('settings');

    // ----------------------------------------------------
    // QATRACK+ SETTINGS & REST API HANDLERS
    // ----------------------------------------------------
    function loadQATrackSettings() {
        fetch('/api/settings')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success' && data.settings) {
                    const s = data.settings;
                    if (settingQATrackUrl) settingQATrackUrl.value = s.qatrack_url || 'http://localhost:8000';
                    if (settingQATrackToken) settingQATrackToken.value = s.qatrack_token || '';
                    if (settingQATrackUnit) settingQATrackUnit.value = s.unit_name || 'Halcyon_1';
                    if (settingQATrackTestList) settingQATrackTestList.value = s.test_list_slug || 'anti_gravity_mlc_qc';
                    if (settingQATrackUTC) settingQATrackUTC.value = s.unit_test_collection || '';

                    if (settingTempVal) settingTempVal.value = s.temperature_val !== undefined ? s.temperature_val : 22.0;
                    if (settingPressVal) settingPressVal.value = s.pressure_val !== undefined ? s.pressure_val : 101.3;

                    if (settingMacroMaxSag) settingMacroMaxSag.value = s.macro_max_sag || 'sag_max_mm';
                    if (settingMacroMaxLeafSag) settingMacroMaxLeafSag.value = s.macro_max_leaf_sag || 'sag_max_leaf_mm';
                    if (settingMacroPassRate) settingMacroPassRate.value = s.macro_pass_rate || 'pass_rate_pct';
                    if (settingMacroDlgBaseline) settingMacroDlgBaseline.value = s.macro_dlg_baseline || 'dlg_0deg_mm';
                    if (settingMacroMaxFluence) settingMacroMaxFluence.value = s.macro_max_fluence || 'max_fluence_delta_pct';
                    if (settingMacroQCStatus) settingMacroQCStatus.value = s.macro_qc_status || 'qc_status';
                }
            });
    }

    function saveQATrackSettings() {
        const payload = {
            qatrack_url: settingQATrackUrl ? settingQATrackUrl.value.trim() : '',
            qatrack_token: settingQATrackToken ? settingQATrackToken.value.trim() : '',
            unit_name: settingQATrackUnit ? settingQATrackUnit.value.trim() : '',
            test_list_slug: settingQATrackTestList ? settingQATrackTestList.value.trim() : '',
            unit_test_collection: settingQATrackUTC ? settingQATrackUTC.value.trim() : '',
            temperature_val: settingTempVal ? parseFloat(settingTempVal.value) || 22.0 : 22.0,
            pressure_val: settingPressVal ? parseFloat(settingPressVal.value) || 101.3 : 101.3,
            macro_temperature: 'temperature',
            macro_pressure: 'pressure',
            macro_max_sag: settingMacroMaxSag ? settingMacroMaxSag.value.trim() : 'sag_max_mm',
            macro_max_leaf_sag: settingMacroMaxLeafSag ? settingMacroMaxLeafSag.value.trim() : 'sag_max_leaf_mm',
            macro_pass_rate: settingMacroPassRate ? settingMacroPassRate.value.trim() : 'pass_rate_pct',
            macro_dlg_baseline: settingMacroDlgBaseline ? settingMacroDlgBaseline.value.trim() : 'dlg_0deg_mm',
            macro_max_fluence: settingMacroMaxFluence ? settingMacroMaxFluence.value.trim() : 'max_fluence_delta_pct',
            macro_qc_status: settingMacroQCStatus ? settingMacroQCStatus.value.trim() : 'qc_status'
        };

        fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                alert("QATrack+ settings saved successfully!");
            }
        });
    }

    function testQATrackConnection() {
        const payload = {
            qatrack_url: settingQATrackUrl ? settingQATrackUrl.value.trim() : '',
            qatrack_token: settingQATrackToken ? settingQATrackToken.value.trim() : '',
            unit_name: settingQATrackUnit ? settingQATrackUnit.value.trim() : '',
            test_list_slug: settingQATrackTestList ? settingQATrackTestList.value.trim() : '',
            unit_test_collection: settingQATrackUTC ? settingQATrackUTC.value.trim() : ''
        };

        if (qatrackLogOutput) qatrackLogOutput.textContent = "Testing connection to QATrack+ REST API...";

        fetch('/api/test-qatrack-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            if (qatrackLogOutput) {
                qatrackLogOutput.textContent = JSON.stringify(data, null, 2);
            }
        });
    }

    function pushQATrackResults() {
        if (!currentSagAnalysisData || !currentSagAnalysisData.summary) {
            alert("No Anti-Gravity QC analysis results available. Run Analysis first!");
            return;
        }

        if (qatrackLogOutput) qatrackLogOutput.textContent = "Pushing Anti-Gravity QC results to QATrack+ API...";

        fetch('/api/push-qatrack-results', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                summary: currentSagAnalysisData.summary
            })
        })
        .then(res => res.json())
        .then(data => {
            if (qatrackLogOutput) {
                qatrackLogOutput.textContent = JSON.stringify(data, null, 2);
            }
            if (data.status === 'success') {
                alert(`✅ QATrack+ Push Successful: ${data.message}`);
            } else {
                alert(`⚠️ QATrack+ Push Error: ${data.message}\nCheck Settings & QATrack+ log output for details.`);
            }
        })
        .catch(err => {
            console.error("QATrack+ push error:", err);
            if (qatrackLogOutput) qatrackLogOutput.textContent = "Push failed: " + err;
            alert("QATrack+ push request failed. Check server logs.");
        });
    }

    if (btnSaveQATrackSettings) btnSaveQATrackSettings.addEventListener('click', saveQATrackSettings);
    if (btnTestQATrackConn) btnTestQATrackConn.addEventListener('click', testQATrackConnection);
    if (btnPushQATrack) btnPushQATrack.addEventListener('click', pushQATrackResults);
    if (btnPushQATrackNow) btnPushQATrackNow.addEventListener('click', pushQATrackResults);

    loadQATrackSettings();

    // Fetch and bind App Version info
    function loadAppVersion() {
        fetch('/api/version')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success' && data.version) {
                    const badge = document.getElementById('app-version-badge');
                    const modalVer = document.getElementById('splash-modal-version');
                    const buildStr = document.getElementById('splash-build-string');
                    if (badge) badge.textContent = data.version;
                    if (modalVer) modalVer.textContent = data.version;
                    if (buildStr) buildStr.textContent = data.version;
                }
            })
            .catch(err => console.warn("Failed to load version:", err));
    }
    loadAppVersion();

    // Splash / About Modal Controls
    const splashModal = document.getElementById('splash-about-modal');
    const btnOpenSplash = document.getElementById('btn-open-splash-about');
    const brandSplashTrigger = document.getElementById('brand-splash-trigger');
    const btnCloseSplash = document.getElementById('btn-close-splash-about');
    const btnCloseSplashBottom = document.getElementById('btn-close-splash-modal-bottom');

    function openSplashModal() {
        if (splashModal) splashModal.style.display = 'block';
    }

    function closeSplashModal() {
        if (splashModal) splashModal.style.display = 'none';
    }

    if (btnOpenSplash) btnOpenSplash.addEventListener('click', openSplashModal);
    if (brandSplashTrigger) brandSplashTrigger.addEventListener('click', openSplashModal);
    if (btnCloseSplash) btnCloseSplash.addEventListener('click', closeSplashModal);
    if (btnCloseSplashBottom) btnCloseSplashBottom.addEventListener('click', closeSplashModal);

    if (splashModal) {
        splashModal.addEventListener('click', (e) => {
            if (e.target === splashModal) closeSplashModal();
        });
    }

    function filterByActiveBank(list) {
        if (!list) return [];
        if (activeBankFilter === 'DISTAL') {
            return list.filter(item => {
                const b = (item.bank || '').toLowerCase();
                return b.includes('distal') || b.includes('sx2');
            });
        } else if (activeBankFilter === 'PROXIMAL') {
            return list.filter(item => {
                const b = (item.bank || '').toLowerCase();
                return b.includes('proximal') || b.includes('sx1');
            });
        }
        return list;
    }

    function setBankFilter(mode) {
        activeBankFilter = mode;

        if (btnBankDistal) btnBankDistal.className = mode === 'DISTAL' ? 'tab-btn active' : 'tab-btn';
        if (btnBankProximal) btnBankProximal.className = mode === 'PROXIMAL' ? 'tab-btn active' : 'tab-btn';
        if (btnBankAll) btnBankAll.className = mode === 'ALL' ? 'tab-btn active' : 'tab-btn';

        if (currentSagAnalysisData) {
            const filteredMetrics = filterByActiveBank(currentSagAnalysisData.combined_metrics);
            renderAntiGravityTable(filteredMetrics);

            const pOffsets = (currentSagAnalysisData.summary && currentSagAnalysisData.summary.panel_offsets) ? currentSagAnalysisData.summary.panel_offsets : {};
            charts.setSagResults(filteredMetrics, pOffsets, selectedTrackIndex, (trackIdx, targetAngle) => {
                selectTrack(trackIdx, targetAngle);
            });

            const activeTracks = (currentSagAnalysisData.analyzed_angles && currentSagAnalysisData.analyzed_angles[activeGantryAngleIndex])
                ? currentSagAnalysisData.analyzed_angles[activeGantryAngleIndex].tracks
                : [];
            viewer.setLeafResults(filterByActiveBank(activeTracks), selectedTrackIndex);
        }
    }

    if (btnBankDistal) btnBankDistal.addEventListener('click', () => setBankFilter('DISTAL'));
    if (btnBankProximal) btnBankProximal.addEventListener('click', () => setBankFilter('PROXIMAL'));
    if (btnBankAll) btnBankAll.addEventListener('click', () => setBankFilter('ALL'));

    function updateMachineLayout() {
        const m = selectMachineType ? selectMachineType.value : 'HALCYON';
        if (m === 'HALCYON') {
            if (machineDescBox) machineDescBox.textContent = 'Halcyon Triad Workflow: 1 Distal Slit (SX2) + 1 Proximal Slit (SX1) + 1 Open Field per cardinal angle.';
            if (kpiFlexStatus) kpiFlexStatus.textContent = 'Halcyon (114 Leaves)';
            if (kpiLinacSub) kpiLinacSub.textContent = '57 Staggered Tracks (29 Distal / 28 Proximal)';

            if (btnBankDistal) { btnBankDistal.style.display = 'inline-block'; btnBankDistal.textContent = '🔹 Distal Bank (SX2 - 29 Pairs)'; }
            if (btnBankProximal) { btnBankProximal.style.display = 'inline-block'; btnBankProximal.textContent = '🔸 Proximal Bank (SX1 - 28 Pairs)'; }
            if (btnBankAll) { btnBankAll.textContent = '🌐 All Combined Tracks (57 Pairs)'; }

            setBankFilter('DISTAL');
        } else {
            if (machineDescBox) machineDescBox.textContent = 'TrueBeam Pair Workflow: 1 Combined MLC Slit (Millennium 120) + 1 Open Field per cardinal angle.';
            if (kpiFlexStatus) kpiFlexStatus.textContent = 'TrueBeam (120 Leaves)';
            if (kpiLinacSub) kpiLinacSub.textContent = '60 Millennium Leaf Pairs';

            if (btnBankDistal) btnBankDistal.style.display = 'none';
            if (btnBankProximal) btnBankProximal.style.display = 'none';
            if (btnBankAll) btnBankAll.textContent = 'Millennium 120 (60 Leaf Pairs)';

            setBankFilter('ALL');
        }

        pollWatchedFolder(false);
    }

    if (selectMachineType) {
        selectMachineType.addEventListener('change', updateMachineLayout);
        updateMachineLayout();
    }

    // Toggle All Tracks Display Button
    if (btnToggleAllTracks) {
        btnToggleAllTracks.addEventListener('click', () => {
            const isAllVisible = viewer.toggleShowAllTracks();
            btnToggleAllTracks.className = isAllVisible ? 'tab-btn active' : 'tab-btn';
        });
    }

    // Auto-Load Gravity ETHOS Dataset Button Handler
    if (btnQuickEthos) {
        btnQuickEthos.addEventListener('click', () => {
            if (inputWatchFolder) inputWatchFolder.value = 'Test Images/Gravity ETHOS/Normal';
            if (selectMachineType) selectMachineType.value = 'HALCYON';
            pollWatchedFolder(true);
        });
    }

    if (btnRunSagAnalysis) {
        btnRunSagAnalysis.addEventListener('click', runAntiGravityAnalysis);
    }

    function runAntiGravityAnalysis() {
        const machineType = selectMachineType ? selectMachineType.value : 'HALCYON';
        const expectedList = slotDefinitions[machineType] || slotDefinitions['HALCYON'];
        const slots = (lastWatchedFolderData && lastWatchedFolderData.mapped_slots) ? lastWatchedFolderData.mapped_slots : {};

        const missingSlots = [];
        expectedList.forEach(slotDef => {
            if (!manualUploadedSlots[slotDef.key] && !slots[slotDef.key]) {
                missingSlots.push(slotDef.title);
            }
        });

        if (missingSlots.length > 0) {
            alert(`Cannot run analysis yet. The following required DICOM input slots are missing:\n\n• ${missingSlots.join('\n• ')}\n\nPlease upload or select a folder containing these files.`);
            return;
        }

        const angles = [0, 90, 180, 270];

        const getSlotPath = (key) => {
            if (manualUploadedSlots[key]) {
                return manualUploadedSlots[key].saved_path;
            }
            const match = slots[key];
            if (!match) return '';
            return typeof match === 'string' ? match : (match.saved_path || '');
        };

        const applyMag = chkMagCorr ? chkMagCorr.checked : true;

        const warnMm = getWarnTolerance();
        const actionMm = getActionTolerance();

        viewer.setToleranceThresholds(warnMm, actionMm);
        charts.setToleranceThresholds(warnMm, actionMm);

        const cardinalDatasets = angles.map((ang) => {
            const openPath = getSlotPath(`open_${ang}`);
            const distPath = getSlotPath(`dist_${ang}`);
            const proxPath = getSlotPath(`prox_${ang}`) || distPath;

            return {
                gantry_angle: ang,
                open_field: openPath,
                picket_field: distPath,
                distal_field: distPath,
                proximal_field: proxPath,
                mlc_field: distPath
            };
        });

        btnRunSagAnalysis.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Analyzing Anti-Gravity QC & DLG...`;
        btnRunSagAnalysis.disabled = true;

        fetch('/api/analyze-anti-gravity-qc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                machine_type: machineType,
                cardinal_datasets: cardinalDatasets,
                warn_sag_mm: warnMm,
                action_sag_mm: actionMm,
                warn_fluence_pct: 5.0,
                apply_magnification_correction: applyMag
            })
        })
        .then(res => res.json())
        .then(data => {
            btnRunSagAnalysis.innerHTML = `<span>▶</span> Run Analysis`;
            btnRunSagAnalysis.disabled = false;

            if (data.status === 'success') {
                currentSagAnalysisData = data;
                updateAntiGravityKPIs(data.summary);

                // User directive: Default view once analysed should be 90° image, all tracks, and all available leaf banks/pairs
                activeGantryAngleIndex = 1; // 90° index in [0, 90, 180, 270]
                selectedTrackIndex = null;  // All tracks
                activeBankFilter = 'ALL';   // All available leaf banks/pairs

                // Update UI active states for Gantry Angle buttons
                const btnGantryAngles = document.querySelectorAll('#gantry-angle-tabs .tab-btn');
                btnGantryAngles.forEach((btn, idx) => {
                    if (idx === 1) btn.classList.add('active');
                    else btn.classList.remove('active');
                });

                // Update UI active states for Bank Filter buttons
                if (btnBankDistal) btnBankDistal.classList.remove('active');
                if (btnBankProximal) btnBankProximal.classList.remove('active');
                if (btnBankAll) btnBankAll.classList.add('active');

                const filteredMetrics = filterByActiveBank(data.combined_metrics);
                renderAntiGravityTable(filteredMetrics);

                const pOffsets = (data.summary && data.summary.panel_offsets) ? data.summary.panel_offsets : {};
                charts.setSagResults(filteredMetrics, pOffsets, selectedTrackIndex, (trackIdx, targetAngle) => {
                    selectTrack(trackIdx, targetAngle);
                });

                updateViewerImage();
                updateToleranceColorsAndLegend();
            } else {
                alert("Anti-Gravity QC failed: " + (data.detail || "Error"));
            }
        })
        .catch(err => {
            btnRunSagAnalysis.innerHTML = `<span>▶</span> Run Analysis`;
            btnRunSagAnalysis.disabled = false;
            console.error("Anti-Gravity QC error:", err);
        });
    }

    function updateAntiGravityKPIs(summary) {
        if (!summary) return;
        if (kpiPassRate) {
            kpiPassRate.textContent = `${summary.pass_rate_pct.toFixed(1)}%`;
            kpiPassRate.className = summary.pass_rate_pct >= 95 ? 'kpi-value badge-pass' : (summary.pass_rate_pct >= 85 ? 'kpi-value badge-warn' : 'kpi-value badge-fail');
        }

        const dlg = summary.baseline_g0_dlg || {};
        if (kpiDlgVal) kpiDlgVal.textContent = `${dlg.dlg_system_mm !== undefined ? dlg.dlg_system_mm.toFixed(3) : '0.000'} mm`;
        if (kpiDlgSub) kpiDlgSub.textContent = summary.machine_type === 'TRUEBEAM' ? 'Millennium 120 System DLG' : `Prox: ${dlg.dlg_proximal_mm || 0}mm | Dist: ${dlg.dlg_distal_mm || 0}mm`;

        if (kpiMaxSag) kpiMaxSag.textContent = `${summary.max_sag_amplitude_mm.toFixed(3)} mm`;

        if (kpiMaxLeafSag) kpiMaxLeafSag.textContent = `${(summary.max_individual_leaf_sag_mm || summary.max_sag_amplitude_mm).toFixed(3)} mm`;
        if (kpiMaxLeafSub) kpiMaxLeafSub.textContent = `${summary.worst_leaf_label || 'Worst Leaf'}`;

        if (kpiMaxFluence) kpiMaxFluence.textContent = `${summary.max_dosimetric_delta_pct.toFixed(2)} %`;
        if (kpiFlexStatus) kpiFlexStatus.textContent = summary.machine_type === 'HALCYON' ? 'Halcyon (114 Leaves)' : 'TrueBeam (120 Leaves)';
        if (kpiLinacSub) kpiLinacSub.textContent = summary.machine_type === 'HALCYON' ? '57 Staggered Tracks (29 Distal / 28 Proximal)' : '60 Millennium Leaf Pairs';
    }

    function updateViewerImage() {
        const angles = [0, 90, 180, 270];
        const gAng = angles[activeGantryAngleIndex] !== undefined ? angles[activeGantryAngleIndex] : 0;
        const slots = (lastWatchedFolderData && lastWatchedFolderData.mapped_slots) ? lastWatchedFolderData.mapped_slots : {};

        const slotKey = (activeImageType === 'OPEN') ? `open_${gAng}` : `dist_${gAng}`;
        let selectedPath = '';

        if (manualUploadedSlots[slotKey]) {
            selectedPath = manualUploadedSlots[slotKey].saved_path;
        } else if (slots[slotKey]) {
            const match = slots[slotKey];
            selectedPath = typeof match === 'string' ? match : (match.saved_path || '');
        }

        if (selectedPath) {
            const formData = new FormData();
            formData.append('file_path', selectedPath);
            formData.append('slot', 'a');

            fetch('/api/load-image', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(imgData => {
                if (imgData.preview_b64) {
                    const activeTracks = (currentSagAnalysisData && currentSagAnalysisData.analyzed_angles)
                        ? (currentSagAnalysisData.analyzed_angles[activeGantryAngleIndex] ? currentSagAnalysisData.analyzed_angles[activeGantryAngleIndex].tracks : [])
                        : [];
                    viewer.setLeafResults(filterByActiveBank(activeTracks), selectedTrackIndex);
                    viewer.setImage(imgData.preview_b64, filterByActiveBank(activeTracks), selectedTrackIndex);
                }
            });
        }
    }

    function renderAntiGravityTable(combinedMetrics) {
        if (!tableBody || !tableHead || !combinedMetrics) return;
        tableBody.innerHTML = '';
        tableHead.innerHTML = '';

        if (activeTableViewMode === 'LEAF') {
            tableHead.innerHTML = `
                <tr>
                    <th>Track #</th>
                    <th>MLC Bank</th>
                    <th>Left 0° (mm)</th>
                    <th>Right 0° (mm)</th>
                    <th style="color: #38bdf8;">90° Left Sag</th>
                    <th style="color: #38bdf8;">90° Right Sag</th>
                    <th style="color: #38bdf8;">270° Left Sag</th>
                    <th style="color: #38bdf8;">270° Right Sag</th>
                    <th>Max Leaf Sag</th>
                    <th>Uncertainty σ</th>
                    <th>Status</th>
                </tr>
            `;

            combinedMetrics.forEach(m => {
                const tr = document.createElement('tr');
                if (parseInt(m.track_index, 10) === parseInt(selectedTrackIndex, 10)) tr.className = 'selected';

                const left0 = m.neutral_0_x_left_mm !== null ? `${m.neutral_0_x_left_mm.toFixed(2)} mm` : '--';
                const right0 = m.neutral_0_x_right_mm !== null ? `${m.neutral_0_x_right_mm.toFixed(2)} mm` : '--';

                const sagL90 = m.sag_left_90_mm !== undefined && m.sag_left_90_mm !== null ? `${m.sag_left_90_mm >= 0 ? '+' : ''}${m.sag_left_90_mm.toFixed(2)} mm` : '--';
                const sagR90 = m.sag_right_90_mm !== undefined && m.sag_right_90_mm !== null ? `${m.sag_right_90_mm >= 0 ? '+' : ''}${m.sag_right_90_mm.toFixed(2)} mm` : '--';

                const sagL270 = m.sag_left_270_mm !== undefined && m.sag_left_270_mm !== null ? `${m.sag_left_270_mm >= 0 ? '+' : ''}${m.sag_left_270_mm.toFixed(2)} mm` : '--';
                const sagR270 = m.sag_right_270_mm !== undefined && m.sag_right_270_mm !== null ? `${m.sag_right_270_mm >= 0 ? '+' : ''}${m.sag_right_270_mm.toFixed(2)} mm` : '--';

                const colorL90 = getToleranceColor(m.sag_left_90_mm);
                const colorR90 = getToleranceColor(m.sag_right_90_mm);
                const colorL270 = getToleranceColor(m.sag_left_270_mm);
                const colorR270 = getToleranceColor(m.sag_right_270_mm);
                const colorMaxLeaf = getToleranceColor(m.max_leaf_sag_mm);

                const maxLeafSag = m.max_leaf_sag_mm !== undefined ? `${m.max_leaf_sag_mm.toFixed(2)} mm` : `${m.max_sag_mm.toFixed(2)} mm`;
                const sigmaLeaf = m.leaf_positional_uncertainty_mm !== undefined ? `±${(m.leaf_positional_uncertainty_mm / 2.0).toFixed(2)} mm` : '--';

                tr.innerHTML = `
                    <td><strong>Track ${m.track_index}</strong></td>
                    <td><small style="color: #00f2fe;">${m.bank}</small> Pair ${m.pair_number}</td>
                    <td>${left0}</td>
                    <td>${right0}</td>
                    <td><strong style="color: ${colorL90};">${sagL90}</strong></td>
                    <td><strong style="color: ${colorR90};">${sagR90}</strong></td>
                    <td><strong style="color: ${colorL270};">${sagL270}</strong></td>
                    <td><strong style="color: ${colorR270};">${sagR270}</strong></td>
                    <td><strong style="color: ${colorMaxLeaf}; font-size: 0.85rem;">${maxLeafSag}</strong></td>
                    <td><span style="color: #a855f7; font-weight: 600;">${sigmaLeaf}</span></td>
                    <td><span class="badge-pill ${m.status}">${m.status}</span></td>
                `;

                tr.addEventListener('click', () => {
                    selectTrack(m.track_index);
                });

                tableBody.appendChild(tr);
            });

        } else {
            tableHead.innerHTML = `
                <tr>
                    <th>Track #</th>
                    <th>MLC Bank</th>
                    <th>Neutral 0° (mm)</th>
                    <th>0° DLG (mm)</th>
                    <th>90° Slit Sag (mm)</th>
                    <th>270° Slit Sag (mm)</th>
                    <th>90° Fluence ΔD (%)</th>
                    <th>270° Fluence ΔD (%)</th>
                    <th>Max Slit Sag (mm)</th>
                    <th>Status</th>
                </tr>
            `;

            combinedMetrics.forEach(m => {
                const tr = document.createElement('tr');
                if (parseInt(m.track_index, 10) === parseInt(selectedTrackIndex, 10)) tr.className = 'selected';

                const neutStr = m.neutral_0_x_true_mm !== null ? `${m.neutral_0_x_true_mm.toFixed(2)} mm` : '--';
                const dlgStr = m.baseline_0_dlg_mm !== undefined ? `${m.baseline_0_dlg_mm >= 0 ? '+' : ''}${m.baseline_0_dlg_mm.toFixed(2)} mm` : '--';
                const s90 = m.sag_90_mm !== null ? `${m.sag_90_mm >= 0 ? '+' : ''}${m.sag_90_mm.toFixed(2)} mm` : '--';
                const s270 = m.sag_270_mm !== null ? `${m.sag_270_mm >= 0 ? '+' : ''}${m.sag_270_mm.toFixed(2)} mm` : '--';
                const d90 = m.delta_d_90_pct !== null ? `${m.delta_d_90_pct >= 0 ? '+' : ''}${m.delta_d_90_pct.toFixed(1)}%` : '--';
                const d270 = m.delta_d_270_pct !== null ? `${m.delta_d_270_pct >= 0 ? '+' : ''}${m.delta_d_270_pct.toFixed(1)}%` : '--';

                const colorS90 = getToleranceColor(m.sag_90_mm);
                const colorS270 = getToleranceColor(m.sag_270_mm);
                const colorMaxSlit = getToleranceColor(m.max_sag_mm);

                tr.innerHTML = `
                    <td><strong>Track ${m.track_index}</strong></td>
                    <td><small style="color: #00f2fe;">${m.bank}</small> Pair ${m.pair_number}</td>
                    <td>${neutStr}</td>
                    <td><strong style="color: #a855f7;">${dlgStr}</strong></td>
                    <td><strong style="color: ${colorS90};">${s90}</strong></td>
                    <td><strong style="color: ${colorS270};">${s270}</strong></td>
                    <td><span style="color: #38bdf8;">${d90}</span></td>
                    <td><span style="color: #38bdf8;">${d270}</span></td>
                    <td><strong style="color: ${colorMaxSlit}; font-size: 0.85rem;">${m.max_sag_mm.toFixed(2)} mm</strong></td>
                    <td><span class="badge-pill ${m.status}">${m.status}</span></td>
                `;

                tr.addEventListener('click', () => {
                    selectTrack(m.track_index);
                });

                tableBody.appendChild(tr);
            });
        }
    }

    function showPerLeafInspectionModal(trackIdx) {
        if (!currentSagAnalysisData || !currentSagAnalysisData.combined_metrics || !perLeafModal) return;

        const m = currentSagAnalysisData.combined_metrics.find(t => parseInt(t.track_index, 10) === parseInt(trackIdx, 10));
        if (!m) return;

        const pOff = currentSagAnalysisData.summary.panel_offsets || {};

        if (modalTrackTitle) modalTrackTitle.textContent = `🔍 Per-Leaf Inspection Details - Track #${m.track_index} (${m.bank} Pair ${m.pair_number})`;

        const sagL90 = m.sag_left_90_mm !== undefined && m.sag_left_90_mm !== null ? `${m.sag_left_90_mm >= 0 ? '+' : ''}${m.sag_left_90_mm.toFixed(3)} mm` : '--';
        const sagR90 = m.sag_right_90_mm !== undefined && m.sag_right_90_mm !== null ? `${m.sag_right_90_mm >= 0 ? '+' : ''}${m.sag_right_90_mm.toFixed(3)} mm` : '--';

        const sagL270 = m.sag_left_270_mm !== undefined && m.sag_left_270_mm !== null ? `${m.sag_left_270_mm >= 0 ? '+' : ''}${m.sag_left_270_mm.toFixed(3)} mm` : '--';
        const sagR270 = m.sag_right_270_mm !== undefined && m.sag_right_270_mm !== null ? `${m.sag_right_270_mm >= 0 ? '+' : ''}${m.sag_right_270_mm.toFixed(3)} mm` : '--';

        const l0 = m.neutral_0_x_left_mm !== null ? `${m.neutral_0_x_left_mm.toFixed(3)} mm` : '--';
        const r0 = m.neutral_0_x_right_mm !== null ? `${m.neutral_0_x_right_mm.toFixed(3)} mm` : '--';

        const pFlex90 = pOff[90] ? `${pOff[90].delta_x_panel_mm} mm` : '--';
        const pFlex270 = pOff[270] ? `${pOff[270].delta_x_panel_mm} mm` : '--';

        const kmag90 = pOff[90] ? pOff[90].k_mag : '--';
        const kmag270 = pOff[270] ? pOff[270].k_mag : '--';

        const colorL90 = getToleranceColor(m.sag_left_90_mm);
        const colorR90 = getToleranceColor(m.sag_right_90_mm);

        if (modalTrackContent) {
            modalTrackContent.innerHTML = `
                <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid ${colorL90}; border-radius: 6px; padding: 0.75rem;">
                    <div style="font-weight: 700; color: ${colorL90}; margin-bottom: 0.4rem;">🍃 Bank A (Left Leaf #${m.pair_number})</div>
                    <div>• 0° Baseline Position: <strong>${l0}</strong></div>
                    <div>• 90° Gravitational Sag: <strong style="color: ${colorL90};">${sagL90}</strong></div>
                    <div>• 270° Counter Sag: <strong>${sagL270}</strong></div>
                </div>

                <div style="background: rgba(0, 242, 254, 0.08); border: 1px solid ${colorR90}; border-radius: 6px; padding: 0.75rem;">
                    <div style="font-weight: 700; color: ${colorR90}; margin-bottom: 0.4rem;">🍃 Bank B (Right Leaf #${m.pair_number})</div>
                    <div>• 0° Baseline Position: <strong>${r0}</strong></div>
                    <div>• 90° Gravitational Sag: <strong style="color: ${colorR90};">${sagR90}</strong></div>
                    <div>• 270° Counter Sag: <strong>${sagR270}</strong></div>
                </div>

                <div style="background: rgba(168, 85, 247, 0.08); border: 1px solid #a855f7; border-radius: 6px; padding: 0.75rem;">
                    <div style="font-weight: 700; color: #a855f7; margin-bottom: 0.4rem;">📐 Pair Slit & Detector Panel Parameters</div>
                    <div>• Slit Center Sag @ 90°: <strong>${m.sag_90_mm !== null ? `${m.sag_90_mm >= 0 ? '+' : ''}${m.sag_90_mm.toFixed(3)} mm` : '--'}</strong></div>
                    <div>• EPID Panel Flex (90° / 270°): <strong>${pFlex90} / ${pFlex270}</strong></div>
                    <div>• Magnification Factor k_mag: <strong>${kmag90} / ${kmag270}</strong></div>
                    <div>• Positional Uncertainty Range σ: <strong style="color: #f59e0b;">±${((m.leaf_positional_uncertainty_mm || 0) / 2.0).toFixed(3)} mm</strong></div>
                </div>
            `;
        }

        perLeafModal.style.display = 'block';
    }

    if (btnCloseModal && perLeafModal) {
        btnCloseModal.addEventListener('click', () => {
            perLeafModal.style.display = 'none';
        });
    }

    if (tabTableCenter && tabTableLeaf) {
        tabTableCenter.addEventListener('click', () => {
            activeTableViewMode = 'CENTER';
            tabTableCenter.className = 'tab-btn active';
            tabTableLeaf.className = 'tab-btn';
            if (currentSagAnalysisData) renderAntiGravityTable(filterByActiveBank(currentSagAnalysisData.combined_metrics));
        });

        tabTableLeaf.addEventListener('click', () => {
            activeTableViewMode = 'LEAF';
            tabTableLeaf.className = 'tab-btn active';
            tabTableCenter.className = 'tab-btn';
            if (currentSagAnalysisData) renderAntiGravityTable(filterByActiveBank(currentSagAnalysisData.combined_metrics));
        });
    }

    function selectTrack(trackIdx, targetAngle = null) {
        selectedTrackIndex = parseInt(trackIdx, 10) || 1;

        if (targetAngle === 90) {
            setGantryViewTab(1); // 90° Tab
        } else if (targetAngle === 270) {
            setGantryViewTab(3); // 270° Tab
        }

        if (currentSagAnalysisData) {
            const filteredMetrics = filterByActiveBank(currentSagAnalysisData.combined_metrics);
            renderAntiGravityTable(filteredMetrics);
            charts.setSelectedTrackIndex(selectedTrackIndex);

            const activeTracks = (currentSagAnalysisData.analyzed_angles && currentSagAnalysisData.analyzed_angles[activeGantryAngleIndex])
                ? currentSagAnalysisData.analyzed_angles[activeGantryAngleIndex].tracks
                : [];
            viewer.setLeafResults(filterByActiveBank(activeTracks), selectedTrackIndex);

            showPerLeafInspectionModal(selectedTrackIndex);
        } else {
            viewer.setSelectedTrackIndex(selectedTrackIndex);
        }
    }

    function setImageModeTab(mode) {
        activeImageType = mode;
        if (tabImgMlc) tabImgMlc.className = mode === 'MLC' ? 'tab-btn active' : 'tab-btn';
        if (tabImgOpen) tabImgOpen.className = mode === 'OPEN' ? 'tab-btn active' : 'tab-btn';
        
        viewer.setActiveImageType(mode);
        updateViewerImage();
    }

    function setGantryViewTab(index) {
        activeGantryAngleIndex = index;
        const gantryAngles = [0, 90, 180, 270];
        [tabGantry0, tabGantry90, tabGantry180, tabGantry270].forEach((btn, idx) => {
            if (btn) btn.className = idx === index ? 'tab-btn active' : 'tab-btn';
        });

        viewer.setActiveGantryAngle(gantryAngles[index]);

        if (currentSagAnalysisData && currentSagAnalysisData.analyzed_angles && currentSagAnalysisData.analyzed_angles[index]) {
            const activeTracks = currentSagAnalysisData.analyzed_angles[index].tracks || [];
            viewer.setLeafResults(filterByActiveBank(activeTracks), selectedTrackIndex);
        }

        updateViewerImage();
    }

    if (tabImgMlc) tabImgMlc.addEventListener('click', () => setImageModeTab('MLC'));
    if (tabImgOpen) tabImgOpen.addEventListener('click', () => setImageModeTab('OPEN'));

    if (tabGantry0) tabGantry0.addEventListener('click', () => setGantryViewTab(0));
    if (tabGantry90) tabGantry90.addEventListener('click', () => setGantryViewTab(1));
    if (tabGantry180) tabGantry180.addEventListener('click', () => setGantryViewTab(2));
    if (tabGantry270) tabGantry270.addEventListener('click', () => setGantryViewTab(3));

    if (btnResetView) btnResetView.addEventListener('click', () => viewer.resetView());
});
