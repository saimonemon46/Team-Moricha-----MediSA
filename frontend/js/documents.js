// MediAI - Documents JS
const AI_BASE = 'http://localhost:8000';
const PHP_BASE = '../../backend_php';

let currentAnalysis = null;
let currentDocuments = [];

function getUser() { try { return JSON.parse(sessionStorage.getItem('mediai_user') || 'null'); } catch { return null; } }
function logout() { sessionStorage.removeItem('mediai_user'); window.location.href = 'login.html'; }
function escHtml(t) { return String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

function asArray(value) {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}

function normaliseAnalysis(data) {
  return {
    document_id: data.document_id || data.id || 0,
    document_type: data.document_type || 'Medical Document',
    document_summary: data.document_summary || '',
    medications: asArray(data.medications),
    diagnoses: asArray(data.diagnoses),
    lab_results: asArray(data.lab_results),
    abnormal_findings: asArray(data.abnormal_findings),
    red_flags: asArray(data.red_flags),
    follow_up: data.follow_up || '',
    recommended_specialist: data.recommended_specialist || '',
    notes: data.notes || '',
    raw_text: data.raw_text || '',
    extraction: data.extraction || {},
    needs_review: Boolean(data.needs_review),
  };
}

async function handleFileSelect(file) {
  if (!file) return;
  const status = document.getElementById('uploadStatus');
  const statusText = document.getElementById('uploadStatusText');
  status.style.display = 'block';
  statusText.textContent = 'Uploading ' + file.name + '...';

  try {
    const fd = new FormData();
    fd.append('document', file);
    fd.append('user_id', getUser()?.id || 1);
    const res = await fetch(PHP_BASE + '/api/upload.php', { method: 'POST', body: fd });
    const uploadData = await res.json();
    if (!res.ok || !uploadData.success) throw new Error(uploadData.message || 'Upload failed.');

    statusText.textContent = 'Analyzing document with AI...';
    const aiData = await analyzeDocument(uploadData.id, uploadData.path);
    await saveDocumentAnalysis(uploadData.id, aiData);

    status.style.display = 'none';
    showAnalysis(aiData);
    loadDocuments();
  } catch (err) {
    status.style.display = 'none';
    alert(err?.message || 'Could not upload this document.');
  } finally {
    document.getElementById('fileInput').value = '';
  }
}

async function analyzeDocument(documentId, filePath) {
  const aiRes = await fetch(AI_BASE + '/analyze-document', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_id: documentId, file_path: filePath })
  });
  const aiData = await aiRes.json();
  if (!aiRes.ok) throw new Error(aiData.detail || 'Document analysis failed.');
  return normaliseAnalysis(aiData);
}

async function saveDocumentAnalysis(documentId, analysis) {
  await fetch(PHP_BASE + '/api/upload.php', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: documentId,
      document_type: analysis.document_type || 'Unknown',
      ai_analysis: analysis
    })
  });
}

function renderList(title, items, className = 'text-muted') {
  if (!items.length) return '';
  return `
    <div class="report-section">
      <h4>${escHtml(title)}</h4>
      <ul class="symptoms-list">${items.map(item => `<li class="${className}">${escHtml(item)}</li>`).join('')}</ul>
    </div>`;
}

function showAnalysis(data) {
  const analysis = normaliseAnalysis(data);
  currentAnalysis = analysis;
  window._currentAnalysis = analysis;
  const el = document.getElementById('analysisResult');
  const content = document.getElementById('analysisContent');
  el.style.display = 'block';
  cacheDocumentAssessment(analysis);

  let html = `
    <div class="alert alert-info mb-16">
      <span><strong>${escHtml(analysis.document_type)}</strong>${analysis.document_summary ? ': ' + escHtml(analysis.document_summary) : ''}</span>
    </div>`;

  if (analysis.needs_review) {
    const reason = analysis.extraction?.error || 'Please review this upload manually.';
    html += `<div class="alert alert-warn mb-16"><span>${escHtml(reason)}</span></div>`;
  }

  if (analysis.medications.length) {
    html += '<div class="report-section"><h4>Extracted medications</h4>';
    html += '<table class="data-table"><thead><tr><th>Medication</th><th>Dosage</th><th>Frequency</th><th>Duration</th><th></th></tr></thead><tbody>';
    analysis.medications.forEach((m, index) => {
      html += `<tr>
        <td><strong>${escHtml(m.name)}</strong>${m.route ? `<div class="text-muted">${escHtml(m.route)}</div>` : ''}</td>
        <td>${escHtml(m.dosage || '-')}</td>
        <td>${escHtml(m.frequency || '-')}</td>
        <td>${escHtml(m.duration || '-')}</td>
        <td><button class="btn-book" style="width:auto;padding:4px 12px" data-add-med="${index}">Add</button></td>
      </tr>`;
    });
    html += '</tbody></table>';
    html += '<div class="mt-16"><button class="btn-primary" id="addAllMedsBtn" style="padding:10px 18px;border:none;cursor:pointer">Add all to reminders</button></div></div>';
  }

  if (analysis.lab_results.length) {
    html += '<div class="report-section"><h4>Lab results</h4>';
    html += '<table class="data-table"><thead><tr><th>Test</th><th>Value</th><th>Range</th><th>Flag</th></tr></thead><tbody>';
    analysis.lab_results.forEach(l => {
      const value = [l.value, l.unit].filter(Boolean).join(' ');
      html += `<tr><td>${escHtml(l.test)}</td><td>${escHtml(value || '-')}</td><td>${escHtml(l.reference_range || '-')}</td><td>${escHtml(l.flag || '-')}</td></tr>`;
    });
    html += '</tbody></table></div>';
  }

  html += renderList('Diagnoses', analysis.diagnoses);
  html += renderList('Abnormal findings', analysis.abnormal_findings);
  html += renderList('Red flags', analysis.red_flags, 'badge-high');

  if (analysis.follow_up) html += `<div class="report-section"><h4>Follow-up</h4><p>${escHtml(analysis.follow_up)}</p></div>`;
  if (analysis.notes) html += `<div class="report-section"><h4>Notes</h4><p>${escHtml(analysis.notes)}</p></div>`;

  html += `<div class="alert alert-info mt-16"><span><a href="${documentDoctorLink(analysis)}" class="text-teal" style="color:var(--teal)">Find a relevant doctor for this report -></a></span></div>`;
  content.innerHTML = html;

  content.querySelectorAll('[data-add-med]').forEach(btn => {
    btn.addEventListener('click', () => addMedicationsToReminders([analysis.medications[Number(btn.dataset.addMed)]]));
  });
  const addAll = document.getElementById('addAllMedsBtn');
  if (addAll) addAll.addEventListener('click', () => addMedicationsToReminders(analysis.medications));

  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function addMedicationsToReminders(medications) {
  const analysis = currentAnalysis || {};
  const usable = asArray(medications).filter(m => m?.name);
  if (!usable.length) return;
  const user = getUser();

  try {
    const res = await fetch(PHP_BASE + '/api/medications.php', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: user?.id || 1,
        document_id: analysis.document_id || 0,
        medications: usable.map(m => ({
          name: m.name,
          dosage: m.dosage || '',
          frequency: m.frequency || 'once_daily',
          duration: m.duration || '',
          route: m.route || '',
          instructions: m.instructions || ''
        }))
      })
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.message || 'Could not save medications.');
    alert(`${data.count || usable.length} medication reminder(s) added.`);
  } catch (err) {
    alert(err?.message || 'Could not add medication reminders.');
  }
}

function cacheDocumentAssessment(data) {
  sessionStorage.setItem('mediai_last_assessment', JSON.stringify({
    source: 'document',
    saved_at: new Date().toISOString(),
    document_analysis: data,
    report: {
      possible_condition: data.diagnoses[0] || data.abnormal_findings[0] || '',
      recommended_specialist: data.recommended_specialist || '',
      reasoning: [data.document_summary, data.notes, data.follow_up].filter(Boolean).join(' '),
      symptoms_listed: [...data.diagnoses, ...data.abnormal_findings],
    },
  }));
}

function documentDoctorLink(data) {
  const params = new URLSearchParams();
  if (data.recommended_specialist) params.set('specialization', data.recommended_specialist);
  if (data.diagnoses.length) {
    params.set('condition', data.diagnoses[0]);
    params.set('symptom', data.diagnoses.join(', '));
  } else if (data.abnormal_findings.length) {
    params.set('symptom', data.abnormal_findings.join(', '));
  }
  const reportText = [data.document_summary, data.notes, data.follow_up, data.raw_text].filter(Boolean).join(' ').slice(0, 900);
  if (reportText) params.set('report_text', reportText);
  return `doctors.html?${params.toString()}`;
}

function handleDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelect(file);
}

async function loadDocuments() {
  const u = getUser();
  try {
    const res = await fetch(PHP_BASE + '/api/upload.php?user_id=' + (u?.id || 1));
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.message || 'Failed to load documents.');
    currentDocuments = data.documents || [];
    window._documents = currentDocuments;
    renderDocuments(currentDocuments);
  } catch (err) {
    document.getElementById('docsList').innerHTML = `<p class="text-muted">${escHtml(err?.message || 'Could not load documents.')}</p>`;
  }
}

function renderDocuments(docs) {
  const el = document.getElementById('docsList');
  if (!docs.length) {
    el.innerHTML = `
      <div class="empty-state document-empty">
        <strong>No documents yet</strong>
        <span>Upload a prescription, report, or medical image to see its analysis here.</span>
      </div>`;
    return;
  }
  el.innerHTML =
    docs.map(d => {
      const hasAnalysis = Boolean(d.ai_analysis);
      const uploaded = d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString() : '-';
      const name = d.original_name || 'Untitled document';
      const extension = name.includes('.') ? name.split('.').pop().slice(0, 4).toUpperCase() : 'DOC';
      return `<article class="document-row">
        <div class="document-file-mark">${escHtml(extension)}</div>
        <div class="document-row-main">
          <div class="document-row-title">${escHtml(name)}</div>
          <div class="document-row-meta">
            <span>${escHtml(d.document_type || 'Document')}</span>
            <span>${escHtml(uploaded)}</span>
            <span class="${hasAnalysis ? 'state-ready' : 'state-pending'}">${hasAnalysis ? 'Analyzed' : 'Needs analysis'}</span>
          </div>
        </div>
        <div class="document-row-actions">
          <button class="btn-book" onclick="viewAnalysis(${d.id})">View</button>
          <button class="btn-book" onclick="reanalyse(${d.id})">Re-analyze</button>
          <button class="btn-ghost" onclick="deleteDocument(${d.id})">Delete</button>
        </div>
      </article>`;
    }).join('');
}

async function fetchDocument(id) {
  const user = getUser();
  const res = await fetch(`${PHP_BASE}/api/upload.php?user_id=${user?.id || 1}&id=${id}`);
  const data = await res.json();
  if (!res.ok || !data.success || !data.document) throw new Error(data.message || 'Document not found.');
  return data.document;
}

async function viewAnalysis(id) {
  try {
    const doc = currentDocuments.find(d => Number(d.id) === Number(id)) || await fetchDocument(id);
    if (doc.ai_analysis) {
      showAnalysis({ ...doc.ai_analysis, document_id: doc.id });
      return;
    }
    await reanalyse(id);
  } catch (err) {
    alert(err?.message || 'Could not open this document.');
  }
}

async function reanalyse(id) {
  const status = document.getElementById('uploadStatus');
  const statusText = document.getElementById('uploadStatusText');
  status.style.display = 'block';
  statusText.textContent = 'Re-analyzing document with AI...';

  try {
    const doc = await fetchDocument(id);
    const analysis = await analyzeDocument(doc.id, doc.file_path);
    await saveDocumentAnalysis(doc.id, analysis);
    status.style.display = 'none';
    showAnalysis(analysis);
    loadDocuments();
  } catch (err) {
    status.style.display = 'none';
    alert(err?.message || 'Could not re-analyze this document.');
  }
}

async function deleteDocument(id) {
  if (!confirm('Delete this document?')) return;
  const user = getUser();
  try {
    const res = await fetch(PHP_BASE + '/api/upload.php', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, user_id: user?.id || 1 })
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.message || 'Could not delete document.');
    if (currentAnalysis?.document_id === id) {
      document.getElementById('analysisResult').style.display = 'none';
      currentAnalysis = null;
    }
    loadDocuments();
  } catch (err) {
    alert(err?.message || 'Could not delete this document.');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const u = getUser();
  const el = document.getElementById('sidebarUserName');
  if (el) el.textContent = u ? u.first_name + ' ' + u.last_name : 'Guest';
  loadDocuments();
});
