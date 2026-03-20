/* ══════════════════════════════════════════════════════════════════════════════
   BDDA Frontend — app.js
   Handles: form submission, upload progress, job polling, history
   ══════════════════════════════════════════════════════════════════════════════ */

const API = '';  // Same-origin; set to 'http://localhost:8000' for local dev

// API key injected server-side into window.BDDA_API_KEY by FastAPI before serving index.html
const API_KEY = window.BDDA_API_KEY || '';

function apiHeaders() {
  return { 'X-API-Key': API_KEY };
}

// ─── STATE ────────────────────────────────────────────────────────────────────

let currentJobId = null;
let pollInterval = null;

const STAGE_ORDER = ['ingesting', 'triaging', 'classifying', 'analyzing', 'generating_report', 'complete'];

// ─── DOM REFS ─────────────────────────────────────────────────────────────────

const uploadForm    = document.getElementById('uploadForm');
const submitBtn     = document.getElementById('submitBtn');
const dropZone      = document.getElementById('dropZone');
const fileInput     = document.getElementById('fileInput');
const filePreview   = document.getElementById('filePreview');
const jobPanel      = document.getElementById('jobPanel');
const jobCard       = document.getElementById('jobCard');
const jobTurbineId  = document.getElementById('jobTurbineId');
const jobIdEl       = document.getElementById('jobId');
const progressBar   = document.getElementById('progressBar');
const jobMessage    = document.getElementById('jobMessage');
const jobStats      = document.getElementById('jobStats');
const downloadBtn   = document.getElementById('downloadBtn');
const errorBlock    = document.getElementById('errorBlock');
const jobHistory    = document.getElementById('jobHistory');
const apiStatus     = document.getElementById('apiStatus');

// ─── API HEALTH CHECK ─────────────────────────────────────────────────────────

async function checkApiHealth() {
  try {
    const res = await fetch(`${API}/api/health`, { headers: apiHeaders() });
    if (!res.ok) throw new Error('API not reachable');
    const data = await res.json();

    const keys = data.api_keys || {};
    const configured = Object.values(keys).filter(Boolean).length;
    const total = Object.keys(keys).length;

    if (configured === total) {
      apiStatus.textContent = `All ${total} API keys configured ✓`;
      apiStatus.className = 'api-status ok';
    } else {
      const missing = Object.entries(keys).filter(([, v]) => !v).map(([k]) => k.replace('_API_KEY', ''));
      apiStatus.textContent = `Missing: ${missing.join(', ')}`;
      apiStatus.className = 'api-status warning';
    }
  } catch {
    apiStatus.textContent = 'API offline';
    apiStatus.className = 'api-status';
  }
}

// ─── FILE DROP ZONE ───────────────────────────────────────────────────────────

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));

dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) {
    fileInput.files = e.dataTransfer.files;
    showFilePreview(e.dataTransfer.files[0]);
  }
});

fileInput.addEventListener('change', () => {
  if (fileInput.files.length) showFilePreview(fileInput.files[0]);
});

function showFilePreview(file) {
  const sizeMB = (file.size / 1024 / 1024).toFixed(1);
  filePreview.textContent = `📎 ${file.name}  (${sizeMB} MB)`;
  filePreview.style.display = 'block';
}

// ─── FORM SUBMIT ──────────────────────────────────────────────────────────────

uploadForm.addEventListener('submit', async e => {
  e.preventDefault();

  if (!fileInput.files.length) {
    alert('Please select images or a ZIP file to upload.');
    return;
  }

  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="btn-icon">⏳</span> Uploading…';

  const formData = new FormData(uploadForm);
  // Ensure inspection_date defaults to today if not set
  if (!formData.get('inspection_date')) {
    formData.set('inspection_date', new Date().toISOString().split('T')[0]);
  }

  try {
    const res = await fetch(`${API}/api/upload`, {
      method: 'POST',
      headers: apiHeaders(),
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Upload failed');
    }

    const data = await res.json();
    currentJobId = data.job_id;

    const turbineId = formData.get('turbine_id');
    showJobPanel(currentJobId, turbineId, data.image_count);
    startPolling(currentJobId);

  } catch (err) {
    alert(`Error: ${err.message}`);
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<span class="btn-icon">▶</span> Generate Inspection Report';
  }
});

// ─── JOB PANEL ────────────────────────────────────────────────────────────────

function showJobPanel(jobId, turbineId, imageCount) {
  jobPanel.style.display = 'block';
  jobTurbineId.textContent = turbineId || jobId;
  jobIdEl.textContent = `Job #${jobId}`;
  progressBar.style.width = '0%';
  jobMessage.textContent = 'Starting pipeline…';
  jobStats.innerHTML = imageCount ? `<span>${imageCount} images</span>` : '';
  downloadBtn.style.display = 'none';
  errorBlock.style.display = 'none';

  // Reset stage dots
  document.querySelectorAll('.stage-item').forEach(el => {
    el.classList.remove('active', 'done', 'error');
  });

  // Scroll to job panel
  jobPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function updateJobPanel(status) {
  const { stage, message, progress, total_images, flagged_images, critical_findings } = status;

  // Progress bar
  if (progress >= 0) {
    progressBar.style.width = `${progress}%`;
    progressBar.style.background = '';
  }

  // Message
  jobMessage.textContent = message || stage;

  // Stats
  const statParts = [];
  if (total_images)       statParts.push(`${total_images} images`);
  if (flagged_images)     statParts.push(`${flagged_images} flagged`);
  if (critical_findings)  statParts.push(`${critical_findings} critical`);
  jobStats.innerHTML = statParts.map(s => `<span>${s}</span>`).join('');

  // Stage dots
  const stageIdx = STAGE_ORDER.indexOf(stage);
  STAGE_ORDER.forEach((s, i) => {
    const el = document.querySelector(`.stage-item[data-stage="${s}"]`);
    if (!el) return;
    el.classList.remove('active', 'done', 'error');
    if (stage === 'error') {
      if (i < stageIdx) el.classList.add('done');
      else if (i === stageIdx) el.classList.add('error');
    } else {
      if (i < stageIdx) el.classList.add('done');
      else if (i === stageIdx) el.classList.add('active');
    }
  });

  // Complete
  if (stage === 'complete') {
    downloadBtn.onclick = () => downloadReport(currentJobId);
    downloadBtn.removeAttribute('href');
    downloadBtn.style.display = 'flex';
    progressBar.style.background = 'var(--green)';
    stopPolling();
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<span class="btn-icon">▶</span> Generate Inspection Report';
    loadHistory();
  }

  // Error
  if (stage === 'error') {
    errorBlock.textContent = `Pipeline error: ${message}`;
    errorBlock.style.display = 'block';
    progressBar.style.background = 'var(--red)';
    stopPolling();
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<span class="btn-icon">▶</span> Generate Inspection Report';
  }
}

// ─── POLLING ─────────────────────────────────────────────────────────────────

function startPolling(jobId) {
  stopPolling();
  pollInterval = setInterval(() => pollStatus(jobId), 3000);
  pollStatus(jobId);  // immediate first check
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

async function pollStatus(jobId) {
  try {
    const res = await fetch(`${API}/api/status/${jobId}`, { headers: apiHeaders() });
    if (!res.ok) return;
    const status = await res.json();
    updateJobPanel(status);
    if (status.stage === 'complete' || status.stage === 'error') {
      stopPolling();
    }
  } catch {
    // Network error — keep polling
  }
}

// ─── HISTORY ─────────────────────────────────────────────────────────────────

async function loadHistory() {
  try {
    const res = await fetch(`${API}/api/jobs`, { headers: apiHeaders() });
    if (!res.ok) return;
    const jobs = await res.json();

    if (!jobs.length) {
      jobHistory.innerHTML = '<div class="history-empty">No reports generated yet.</div>';
      return;
    }

    jobHistory.innerHTML = jobs.map(j => {
      const stageClass = j.stage === 'complete' ? 'history-stage-complete'
                       : j.stage === 'error'    ? 'history-stage-error'
                       : 'history-stage-running';
      const stageLabel = j.stage === 'complete' ? 'Done'
                       : j.stage === 'error'    ? 'Error'
                       : 'Running';
      const date = j.created_at ? new Date(j.created_at).toLocaleDateString() : '';
      const dlLink = j.stage === 'complete'
        ? `<button class="history-download" onclick="downloadReport('${j.job_id}')">⬇ PDF</button>`
        : '';

      return `
        <div class="history-item">
          <div>
            <div class="history-turbine">${j.turbine_id || j.job_id}</div>
            <div class="history-date">${date}</div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="history-stage-badge ${stageClass}">${stageLabel}</span>
            ${dlLink}
          </div>
        </div>
      `;
    }).join('');
  } catch {
    // Silently fail
  }
}

// ─── DOWNLOAD ────────────────────────────────────────────────────────────────

async function downloadReport(jobId) {
  try {
    const res = await fetch(`${API}/api/download/${jobId}`, { headers: apiHeaders() });
    if (!res.ok) throw new Error('Download failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `inspection_report_${jobId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert(`Download error: ${err.message}`);
  }
}

// ─── INIT ─────────────────────────────────────────────────────────────────────

checkApiHealth();
loadHistory();

// Set today's date as default
const dateInput = uploadForm.querySelector('input[name="inspection_date"]');
if (dateInput && !dateInput.value) {
  dateInput.value = new Date().toISOString().split('T')[0];
}
