/**
 * Image Processor — frontend logic.
 * Communicates with Flask API via fetch + SSE.
 */

(function () {
    "use strict";

    // ---- DOM refs ----
    const $  = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const dirInput      = $("#dir-input");
    const btnScan       = $("#btn-scan");
    const dropZone      = $("#drop-zone");
    const scanError     = $("#scan-error");
    const toast         = $("#toast");
    const sectionFiles  = $("#section-files");
    const foundTotal    = $("#found-total");
    const extSummary    = $("#ext-summary");
    const selectedCount = $("#selected-count");
    const fileList      = $("#file-list");
    const btnSelectAll  = $("#btn-select-all");
    const btnSelectNone = $("#btn-select-none");
    const btnInvert     = $("#btn-invert");
    const btnStart      = $("#btn-start");

    const sectionProgress = $("#section-progress");
    const progressBar     = $("#progress-bar");
    const infoTotal       = $("#info-total");
    const infoDone        = $("#info-done");
    const infoSkipped     = $("#info-skipped");
    const infoElapsed     = $("#info-elapsed");
    const infoEta         = $("#info-eta");
    const infoCurrent     = $("#info-current");
    const statusText      = $("#status-text");
    const btnStop         = $("#btn-stop");
    const btnViewData     = $("#btn-view-data");
    const sectionData     = $("#section-data");
    const dataTable       = $("#data-table tbody");
    const dataCount       = $("#data-count");

    let scannedDir = "";
    let scannedFiles = [];
    let serverMode = "local";   // "local" or "synology"
    let mediaRoot = "";
    let browserCurrentPath = "";

    // ---- Detect server mode on load ----
    (async () => {
        try {
            const res = await fetch("/api/server-mode");
            const data = await res.json();
            serverMode = data.mode;
            mediaRoot = data.media_root || "";
        } catch (_) {}
    })();

    // ---- Helpers ----
    function showError(el, msg) {
        el.textContent = msg;
        el.classList.remove("hidden");
    }
    function hideError(el) {
        el.classList.add("hidden");
        el.textContent = "";
    }
    function updateSelectedCount() {
        const count = fileList.querySelectorAll("input[type=checkbox]:checked").length;
        selectedCount.textContent = count;
        btnStart.disabled = count === 0;
    }
    function getSelectedFiles() {
        const checked = fileList.querySelectorAll("input[type=checkbox]:checked");
        return Array.from(checked).map((cb) => cb.dataset.file);
    }

    function showToast(msg, type = "success") {
        toast.textContent = msg;
        toast.className = "toast toast-" + type;
        // Force reflow for animation restart
        void toast.offsetWidth;
        toast.classList.add("toast-show");
        clearTimeout(toast._timer);
        toast._timer = setTimeout(() => {
            toast.classList.remove("toast-show");
            toast.classList.add("hidden");
        }, 3500);
    }

    // ---- STEP 1: Scan ----

    // -- Drag & Drop (single unified handler) --
    ["dragenter", "dragover"].forEach(evt => {
        dropZone.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("drag-over");
        });
    });
    dropZone.addEventListener("dragleave", (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove("drag-over");

        // 1) Text drop (e.g. path dragged from Explorer address bar)
        const text = e.dataTransfer.getData("text");
        if (text && text.trim()) {
            dirInput.value = text.trim();
            showToast(`✅ Папку імпортовано: ${text.trim()}`);
            btnScan.click();
            return;
        }

        // 2) Folder/file entries — extract name
        let folderName = "";
        const items = e.dataTransfer.items;
        if (items && items.length > 0) {
            try {
                const entry = items[0].webkitGetAsEntry && items[0].webkitGetAsEntry();
                if (entry) {
                    folderName = entry.name;
                }
            } catch (_) {}
        }
        if (!folderName && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            folderName = e.dataTransfer.files[0].name || "";
        }

        if (!folderName) return;

        // 3) Resolve full path via server
        console.log("[DnD] Resolving folder:", folderName);
        try {
            const res = await fetch("/api/resolve-folder", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: folderName }),
            });
            const data = await res.json();
            console.log("[DnD] Server response:", data);
            if (data.path) {
                dirInput.value = data.path;
                showToast(`✅ Папку імпортовано: ${data.path}`);
                btnScan.click();
                return;
            }
        } catch (err) {
            console.error("[DnD] Resolve error:", err);
        }

        // Fallback — just the name
        dirInput.value = folderName;
        showToast(`⚠️ Не вдалося знайти повний шлях до папки "${folderName}". Введіть його вручную.`, "warn");
    });

    // -- Click on drop zone — native picker (Windows) or folder browser (Synology) --
    dropZone.addEventListener("click", async () => {
        if (serverMode === "synology") {
            openFolderBrowser();
            return;
        }
        try {
            dropZone.classList.add("drag-over");
            const res = await fetch("/api/browse-folder", { method: "POST" });
            const data = await res.json();
            dropZone.classList.remove("drag-over");
            if (data.use_browser) {
                // tkinter not available — fall back to web browser
                openFolderBrowser();
                return;
            }
            if (data.path) {
                dirInput.value = data.path;
                showToast(`✅ Папку імпортовано: ${data.path}`);
                btnScan.click();
            }
        } catch (err) {
            dropZone.classList.remove("drag-over");
            showToast("⚠️ Не вдалося відкрити діалог вибору папки.", "warn");
        }
    });

    btnScan.addEventListener("click", async () => {
        hideError(scanError);
        const dir = dirInput.value.trim();
        if (!dir) { showError(scanError, "Введіть шлях до папки."); return; }

        btnScan.disabled = true;
        btnScan.textContent = "Сканування…";

        try {
            const res = await fetch("/api/scan", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ directory: dir }),
            });
            const data = await res.json();

            if (!res.ok || data.error) {
                showError(scanError, data.error || "Помилка сканування.");
                return;
            }

            scannedDir = data.directory;
            scannedFiles = data.files || [];

            foundTotal.textContent = data.total;
            const extParts = Object.entries(data.by_extension || {})
                .map(([ext, cnt]) => `${ext}: ${cnt}`);
            extSummary.textContent = extParts.join(" | ");

            // Build file list
            fileList.innerHTML = "";
            scannedFiles.forEach((f) => {
                const li = document.createElement("li");
                li.classList.add("selected");
                const cb = document.createElement("input");
                cb.type = "checkbox";
                cb.checked = true;
                cb.dataset.file = f;
                cb.addEventListener("change", updateSelectedCount);
                const label = document.createElement("span");
                label.textContent = f;
                li.addEventListener("click", (e) => {
                    if (e.target === cb) return;
                    cb.checked = !cb.checked;
                    li.classList.toggle("selected", cb.checked);
                    updateSelectedCount();
                });
                li.appendChild(cb);
                li.appendChild(label);
                fileList.appendChild(li);
            });

            updateSelectedCount();
            sectionFiles.classList.remove("hidden");
        } catch (err) {
            showError(scanError, `Мережева помилка: ${err.message}`);
        } finally {
            btnScan.disabled = false;
            btnScan.textContent = "Сканувати";
        }
    });

    // Allow Enter to scan
    dirInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") btnScan.click();
    });

    // ---- Selection controls ----
    btnSelectAll.addEventListener("click", () => {
        fileList.querySelectorAll("input[type=checkbox]").forEach((cb) => {
            cb.checked = true;
            cb.closest("li").classList.add("selected");
        });
        updateSelectedCount();
    });
    btnSelectNone.addEventListener("click", () => {
        fileList.querySelectorAll("input[type=checkbox]").forEach((cb) => {
            cb.checked = false;
            cb.closest("li").classList.remove("selected");
        });
        updateSelectedCount();
    });
    btnInvert.addEventListener("click", () => {
        fileList.querySelectorAll("input[type=checkbox]").forEach((cb) => {
            cb.checked = !cb.checked;
            cb.closest("li").classList.toggle("selected", cb.checked);
        });
        updateSelectedCount();
    });

    // ---- STEP 2: Start processing ----
    btnStart.addEventListener("click", async () => {
        const files = getSelectedFiles();
        if (!files.length) return;

        btnStart.disabled = true;
        btnScan.disabled = true;

        try {
            const res = await fetch("/api/process", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ directory: scannedDir, files }),
            });
            const data = await res.json();

            if (!res.ok || data.error) {
                showError(scanError, data.error || "Помилка запуску.");
                btnStart.disabled = false;
                btnScan.disabled = false;
                return;
            }

            // Show progress section & start SSE
            sectionProgress.classList.remove("hidden");
            btnViewData.classList.add("hidden");
            btnStop.disabled = false;
            statusText.textContent = "Підготовка…";

            listenToJob(data.job_id);
        } catch (err) {
            showError(scanError, `Мережева помилка: ${err.message}`);
            btnStart.disabled = false;
            btnScan.disabled = false;
        }
    });

    // ---- STEP 3: SSE progress ----
    let currentJobId = null;

    function listenToJob(jobId) {
        currentJobId = jobId;
        const source = new EventSource(`/api/jobs/${jobId}/stream`);

        source.onmessage = (event) => {
            const d = JSON.parse(event.data);

            if (d.error) {
                statusText.textContent = `Помилка: ${d.error}`;
                source.close();
                resetButtons();
                return;
            }

            // Update UI
            progressBar.style.width = d.percent + "%";
            progressBar.textContent = d.percent + "%";
            infoTotal.textContent = d.total;
            infoDone.textContent = d.done;
            infoSkipped.textContent = d.skipped;
            infoElapsed.textContent = d.elapsed;
            infoEta.textContent = d.eta;
            infoCurrent.textContent = d.current_file || "—";

            const statusMap = {
                pending:    "Очікування…",
                scanning:   "Сканування файлів…",
                processing: `Обробка ${d.done}/${d.total}: ${d.current_file}`,
                saving:     "Збереження Excel…",
                done:       "✅ Готово!",
                stopped:    "⛔ Зупинено користувачем.",
                error:      `❌ Помилка: ${d.error}`,
            };
            statusText.textContent = statusMap[d.status] || d.status;

            if (d.status === "done" || d.status === "stopped" || d.status === "error") {
                source.close();
                resetButtons();
                if (d.status === "done" || d.status === "stopped") {
                    btnViewData.classList.remove("hidden");
                    btnViewData.onclick = () => loadJobData(jobId);
                }
            }
        };

        source.onerror = () => {
            source.close();
            statusText.textContent = "З'єднання втрачено.";
            resetButtons();
        };

        // Stop button
        btnStop.onclick = async () => {
            btnStop.disabled = true;
            await fetch(`/api/jobs/${jobId}/stop`, { method: "POST" });
        };
    }

    function resetButtons() {
        btnStart.disabled = false;
        btnScan.disabled = false;
        btnStop.disabled = true;
    }

    // ---- STEP 4: Load data from DB ----
    async function loadJobData(jobId) {
        try {
            const res = await fetch(`/api/jobs/${jobId}/data`);
            const data = await res.json();

            if (data.error) {
                dataCount.textContent = `Помилка: ${data.error}`;
                sectionData.classList.remove("hidden");
                return;
            }

            dataTable.innerHTML = "";
            (data.records || []).forEach((r, idx) => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${idx + 1}</td>
                    <td title="${r.FullName || ''}">${r.FileName || ''}</td>
                    <td>${r.Size || ''}</td>
                    <td title="${(r.AIDescription || '').replace(/"/g, '&quot;')}">${(r.AIDescription || '').substring(0, 120)}${(r.AIDescription || '').length > 120 ? '…' : ''}</td>
                    <td>${r.UKR_Keywords || ''}</td>
                    <td>${r.EN_Keywords || ''}</td>
                    <td>${r.OriginalWidthPx || ''}×${r.OriginalHeightPx || ''}</td>
                    <td title="${r.OriginalMD5 || ''}">${(r.OriginalMD5 || '').substring(0, 12)}…</td>
                `;
                dataTable.appendChild(tr);
            });

            dataCount.textContent = `Записів у БД: ${data.count}`;
            sectionData.classList.remove("hidden");
        } catch (err) {
            dataCount.textContent = `Помилка завантаження: ${err.message}`;
            sectionData.classList.remove("hidden");
        }
    }

    // ---- Folder Browser Modal (Synology mode) ----
    const folderModal   = $("#folder-browser-modal");
    const modalDirList  = $("#modal-dir-list");
    const modalBreadcrumb = $("#modal-breadcrumb");
    const modalClose    = $("#modal-close");
    const modalCancel   = $("#modal-cancel");
    const modalSelect   = $("#modal-select");

    function openFolderBrowser() {
        browserCurrentPath = mediaRoot || "/media";
        folderModal.classList.remove("hidden");
        loadDirectoryList(browserCurrentPath);
    }

    function closeFolderBrowser() {
        folderModal.classList.add("hidden");
    }

    modalClose.addEventListener("click", closeFolderBrowser);
    modalCancel.addEventListener("click", closeFolderBrowser);
    folderModal.addEventListener("click", (e) => {
        if (e.target === folderModal) closeFolderBrowser();
    });

    modalSelect.addEventListener("click", () => {
        if (browserCurrentPath) {
            dirInput.value = browserCurrentPath;
            closeFolderBrowser();
            showToast(`✅ Папку обрано: ${browserCurrentPath}`);
            btnScan.click();
        }
    });

    async function loadDirectoryList(path) {
        browserCurrentPath = path;
        modalBreadcrumb.textContent = path;
        modalDirList.innerHTML = '<div class="modal-dir-empty">Завантаження…</div>';

        try {
            const res = await fetch("/api/list-directory", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path }),
            });
            const data = await res.json();
            if (data.error) {
                modalDirList.innerHTML = `<div class="modal-dir-empty">${data.error}</div>`;
                return;
            }

            browserCurrentPath = data.path;
            modalBreadcrumb.textContent = data.path;
            modalDirList.innerHTML = "";

            // "Go up" button
            if (data.parent) {
                const up = document.createElement("div");
                up.className = "modal-dir-item go-up";
                up.innerHTML = "⬆️ ..";
                up.addEventListener("click", () => loadDirectoryList(data.parent));
                modalDirList.appendChild(up);
            }

            if (data.dirs.length === 0 && !data.parent) {
                modalDirList.innerHTML = '<div class="modal-dir-empty">Папки не знайдено. Перевірте volume mounts.</div>';
                return;
            }

            if (data.dirs.length === 0) {
                const empty = document.createElement("div");
                empty.className = "modal-dir-empty";
                empty.textContent = "Підпапки відсутні — можете обрати цю папку.";
                modalDirList.appendChild(empty);
                return;
            }

            data.dirs.forEach((name) => {
                const item = document.createElement("div");
                item.className = "modal-dir-item";
                item.innerHTML = `📁 ${name}`;
                item.addEventListener("click", () => {
                    loadDirectoryList(data.path + "/" + name);
                });
                modalDirList.appendChild(item);
            });
        } catch (err) {
            modalDirList.innerHTML = `<div class="modal-dir-empty">Помилка: ${err.message}</div>`;
        }
    }
})();
