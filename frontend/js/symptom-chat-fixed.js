// ============================================================
// MediAI - Symptom Chat JS
// Manages LangGraph multi-step AI conversation
// ============================================================

const AI_BASE = "http://localhost:8000";
const PHP_BASE = "../../backend_php";

let sessionId = null;
let stage = "initial"; // initial | followup | analysis | done
let followupAnswers = [];
let primarySymptom = "";
let currentReport = null;
let selectedImageFile = null;
let selectedImageUrl = "";
let symptomImageAnalyses = [];

function getUser() {
  try {
    return JSON.parse(sessionStorage.getItem("mediai_user") || "null");
  } catch {
    return null;
  }
}
function logout() {
  sessionStorage.removeItem("mediai_user");
  window.location.href = "login.html";
}

function autoResize(ta) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
}

function setStage(s) {
  stage = s;
  const labels = {
    initial: "Describe your symptoms",
    followup: "Answering questions",
    analysis: "Analysing...",
    done: "Report ready",
  };
  document.getElementById("stageLabel").textContent = labels[s] || s;
  ["dot1", "dot2", "dot3", "dot4"].forEach((id, i) => {
    const el = document.getElementById(id);
    el.className = "stage-dot";
    if (i < ["initial", "followup", "analysis", "done"].indexOf(s))
      el.classList.add("done");
    else if (i === ["initial", "followup", "analysis", "done"].indexOf(s))
      el.classList.add("active");
  });
}

function addMessage(text, sender) {
  const box = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = sender === "ai" ? "msg msg-ai" : "msg msg-user";
  if (sender === "ai") {
    div.innerHTML =
      '<div class="msg-label">MediAI</div>' +
      escHtml(text).replace(/\n/g, "<br>");
  } else {
    div.textContent = text;
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

function addTyping() {
  const box = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = "msg-typing";
  div.id = "typingIndicator";
  div.innerHTML =
    '<div class="typing-dots"><span></span><span></span><span></span></div>';
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

function escHtml(t) {
  return String(t)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function handleImageSelection(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!/^image\/(png|jpe?g|webp)$/i.test(file.type)) {
    addMessage("Please attach a JPG, PNG, or WEBP image.", "ai");
    event.target.value = "";
    return;
  }
  if (file.size > 8 * 1024 * 1024) {
    addMessage(
      "That image is larger than 8MB. Please attach a smaller photo.",
      "ai",
    );
    event.target.value = "";
    return;
  }
  if (selectedImageUrl) URL.revokeObjectURL(selectedImageUrl);
  selectedImageFile = file;
  selectedImageUrl = URL.createObjectURL(file);
  document.getElementById("imagePreview").src = selectedImageUrl;
  document.getElementById("imageFileName").textContent = file.name;
  const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
  const meta = document.getElementById("imageFileMeta");
  if (meta) meta.textContent = `${sizeMb}MB image ready to send`;
  document.getElementById("imageChip").classList.add("visible");
}

function clearSelectedImage() {
  selectedImageFile = null;
  if (selectedImageUrl) URL.revokeObjectURL(selectedImageUrl);
  selectedImageUrl = "";
  document.getElementById("symptomImageInput").value = "";
  document.getElementById("imageChip").classList.remove("visible");
  document.getElementById("imagePreview").removeAttribute("src");
  const meta = document.getElementById("imageFileMeta");
  if (meta) meta.textContent = "Ready to send with your message";
}

function addImageMessage(file, sender) {
  const box = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = sender === "ai" ? "msg msg-ai" : "msg msg-user";
  const url = URL.createObjectURL(file);
  div.innerHTML = `
    ${sender === "ai" ? '<div class="msg-label">MediAI</div>' : ""}
    <div style="font-size:12px;margin-bottom:8px">${sender === "ai" ? "Image received" : "Attached image"}</div>
    <img src="${url}" alt="Uploaded symptom image" style="max-width:220px;max-height:180px;border-radius:8px;display:block;object-fit:cover">
  `;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function formatImageAnalysisForAnswer(analysis) {
  const observations = Array.isArray(analysis?.visible_observations)
    ? analysis.visible_observations.join("; ")
    : "";
  const redFlags = Array.isArray(analysis?.red_flags)
    ? analysis.red_flags.join("; ")
    : "";
  return [
    `Uploaded image observations: type=${analysis?.image_type || "unclear"}`,
    observations ? `visible observations=${observations}` : "",
    analysis?.possible_relevance
      ? `possible relevance=${analysis.possible_relevance}`
      : "",
    redFlags ? `visual red flags=${redFlags}` : "",
    analysis?.confidence ? `image confidence=${analysis.confidence}` : "",
    "The image should be used as supportive context only, not as a definitive diagnosis.",
  ]
    .filter(Boolean)
    .join(". ");
}

function imageAnalysisSummary(analysis) {
  const observations =
    Array.isArray(analysis?.visible_observations) &&
    analysis.visible_observations.length
      ? analysis.visible_observations.join("\n- ")
      : "No detailed visual observations were available.";
  const redFlags =
    Array.isArray(analysis?.red_flags) && analysis.red_flags.length
      ? "\n\nVisual red flags noted:\n- " + analysis.red_flags.join("\n- ")
      : "";
  return `I reviewed the uploaded image as supportive triage context only.\n\nImage type: ${analysis?.image_type || "unclear"}\nVisible observations:\n- ${observations}${redFlags}\n\nA clinician should review the area directly if symptoms are worsening, spreading, painful, draining pus, or accompanied by fever.`;
}

async function analyzeSelectedImage() {
  if (!selectedImageFile) return null;
  const file = selectedImageFile;
  addImageMessage(file, "user");
  clearSelectedImage();
  addTyping();
  try {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(AI_BASE + "/analyze-symptom-image-for-triage", {
      method: "POST",
      body: fd,
    });
    const data = await res.json();

    // Also upload to PHP for permanent storage
    try {
      const phpFd = new FormData();
      phpFd.append("document", file);
      phpFd.append("user_id", getUser()?.id || 1);
      const phpRes = await fetch(PHP_BASE + "/api/upload.php", {
        method: "POST",
        body: phpFd,
      });
      const phpData = await phpRes.json();
      if (phpRes.ok && phpData.success) {
        data.image_path = phpData.path;
      }
    } catch (phpErr) {
      console.warn("Failed to persist image to backend:", phpErr);
    }

    removeTyping();
    if (!res.ok) throw new Error(data.detail || "Could not analyze the image.");
    symptomImageAnalyses.push(data);
    addMessage(imageAnalysisSummary(data), "ai");
    return data;
  } catch (err) {
    removeTyping();
    const fallback = {
      image_type: "unclear",
      visible_observations: [
        "Image was attached, but automatic image analysis was unavailable.",
      ],
      possible_relevance:
        "The image should still be mentioned to a clinician during assessment.",
      red_flags: [],
      confidence: "low",
      needs_clinician_review: true,
    };
    symptomImageAnalyses.push(fallback);
    addMessage(
      err?.message ||
        "I could not analyze the image automatically, but I will include that an image was uploaded.",
      "ai",
    );
    return fallback;
  }
}

function setSendDisabled(v) {
  document.getElementById("sendBtn").disabled = v;
  document.getElementById("chatInput").disabled = v;
}

async function sendMessage() {
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  if (!text && !selectedImageFile) return;
  input.value = "";
  input.style.height = "auto";
  if (text) addMessage(text, "user");
  setSendDisabled(true);

  const imageAnalysis = await analyzeSelectedImage();
  const imageAnswer = imageAnalysis
    ? formatImageAnalysisForAnswer(imageAnalysis)
    : "";

  if (stage === "initial") {
    primarySymptom =
      [text, imageAnswer].filter(Boolean).join("\n\n") ||
      "Uploaded symptom image for assessment";
    await startSession(primarySymptom);
  } else if (stage === "followup") {
    const answer = [text, imageAnswer].filter(Boolean).join("\n\n");
    followupAnswers.push(answer);
    await submitAnswer(answer);
  }
}

async function startSession(symptomText) {
  setStage("followup");
  addTyping();
  try {
    const res = await fetch(AI_BASE + "/generate-questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symptom: symptomText,
        user_id: getUser()?.id || 1,
      }),
    });
    const data = await res.json();
    if (!res.ok)
      throw new Error(data.detail || "Failed to start the symptom session.");

    removeTyping();
    
    if (data.is_medical === false) {
      addMessage(data.intent_message || "I'm here to help with health concerns. Please describe any symptoms you're experiencing.", "ai");
      setStage("initial");
      setSendDisabled(false);
      return;
    }

    sessionId = data.session_id;
    document.getElementById("sessionId").textContent = "#" + sessionId;

    if (data.questions && data.questions.length > 0) {
      const intro = (data.intent_message || "Thank you. To give you a better assessment, I have a few questions:") + 
        "\n\n" + data.questions[0];
      addMessage(intro, "ai");
      window._questions = data.questions;
      window._qIdx = 0;
    } else {
      // If medical intent was detected but no questions were generated, ask for more detail
      // instead of jumping straight to a report which might be empty/undetermined.
      const msg = data.intent_message || "I need a bit more detail about your symptoms to provide a helpful assessment. Could you describe what you're feeling in more detail?";
      addMessage(msg, "ai");
      setStage("initial"); // Allow them to keep typing in initial stage
      setSendDisabled(false);
    }
  } catch (err) {
    removeTyping();
    addMessage(
      err?.message ||
        "I could not start the symptom session. Please try again.",
      "ai",
    );
  }
  setSendDisabled(false);
}

async function submitAnswer(answer) {
  window._qIdx = (window._qIdx || 0) + 1;
  const questions = window._questions || [];

  if (window._qIdx < questions.length) {
    addMessage(questions[window._qIdx], "ai");
    setSendDisabled(false);
  } else {
    setStage("analysis");
    addMessage(
      "Thank you for your answers. Analysing your symptoms now...",
      "ai",
    );
    await generateReport();
  }
}

async function generateReport() {
  setSendDisabled(true);
  addTyping();

  try {
    const res = await fetch(AI_BASE + "/generate-report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        symptom: primarySymptom,
        answers: followupAnswers,
        user_id: getUser()?.id || 1,
        image_analysis: symptomImageAnalyses.length
          ? symptomImageAnalyses[0]
          : null,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to generate report.");

    const saved = await persistReport(data.report);

    removeTyping();
    currentReport = { ...data.report, report_id: saved.report_id };
    cacheAssessment(currentReport);
    displayReportReady(data.report);
  } catch (err) {
    removeTyping();
    addMessage(
      err?.message ||
        "I could not generate or save the report just now. Please try again.",
      "ai",
    );
    setStage("followup");
    setSendDisabled(false);
  }
}

async function persistReport(report) {
  const payload = {
    user_id: getUser()?.id || 1,
    session_id: sessionId,
    possible_condition: report?.possible_condition || "",
    urgency: report?.urgency || "medium",
    recommended_specialist: report?.recommended_specialist || "",
    reasoning: report?.reasoning || "",
    guidance: report?.guidance || "",
    explanation: report?.explanation || "",
    symptoms_listed: Array.isArray(report?.symptoms_listed)
      ? report.symptoms_listed
      : [primarySymptom, ...followupAnswers].filter(Boolean),
    image_path: symptomImageAnalyses.length
      ? symptomImageAnalyses[0].image_path || null
      : null,
    image_analysis: symptomImageAnalyses.length
      ? symptomImageAnalyses[0]
      : null,
  };

  const saveRes = await fetch(PHP_BASE + "/api/reports.php", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!saveRes.ok) {
    throw new Error(
      `Failed to save report: ${saveRes.status} ${saveRes.statusText}`,
    );
  }
  const saveData = await saveRes.json();
  if (!saveData.success) {
    throw new Error(saveData.message || "Failed to save report.");
  }
  return saveData;
}

function cacheAssessment(report) {
  const payload = {
    source: "symptom-chat",
    saved_at: new Date().toISOString(),
    session_id: sessionId,
    primary_symptom: primarySymptom,
    answers: followupAnswers,
    symptom_image_analyses: symptomImageAnalyses,
    report,
  };
  sessionStorage.setItem("mediai_last_assessment", JSON.stringify(payload));
}

function reportContextText(report) {
  return [
    report?.reasoning || "",
    report?.guidance || "",
    report?.explanation || "",
    Array.isArray(report?.symptoms_listed)
      ? report.symptoms_listed.join(", ")
      : "",
    followupAnswers.join(", "),
    symptomImageAnalyses.map(formatImageAnalysisForAnswer).join(" "),
  ]
    .filter(Boolean)
    .join(" ");
}

function doctorLinkForReport(report) {
  const params = new URLSearchParams();
  if (report?.recommended_specialist)
    params.set("specialization", report.recommended_specialist);
  if (primarySymptom) params.set("symptom", primarySymptom);
  if (report?.possible_condition)
    params.set("condition", report.possible_condition);
  if (report?.urgency) params.set("urgency", report.urgency);
  const context = reportContextText(report).slice(0, 700);
  if (context) params.set("report_text", context);
  return `doctors.html?${params.toString()}`;
}

function displayReportReady(report) {
  setStage("done");
  const msg = `Your triage report is ready.\n\nPossible condition: ${report.possible_condition}\nUrgency: ${report.urgency?.toUpperCase()}\nRecommended specialist: ${report.recommended_specialist}\n\nClick "View Report" for the full analysis.`;
  addMessage(msg, "ai");
  document.getElementById("viewReportBtn").style.display = "inline-block";
  setSendDisabled(false);
  renderReportPanel(report);
  loadDoctorSuggestions(report);
}

function renderReportPanel(r) {
  const urgencyClass =
    { high: "badge-high", medium: "badge-medium", low: "badge-low" }[
      r.urgency
    ] || "badge-medium";
  const symptoms = Array.isArray(r.symptoms_listed)
    ? r.symptoms_listed.map((s) => `<li>${escHtml(s)}</li>`).join("")
    : `<li>${escHtml(primarySymptom)}</li>`;
  const imgAnalysis =
    r.image_analysis ||
    (symptomImageAnalyses.length ? symptomImageAnalyses[0] : null);
  const imageSection = imgAnalysis
    ? `
    <div class="report-section">
      <h4>Uploaded image review</h4>
      <div style="padding:10px 0;border-bottom:1px solid var(--border)">
        ${
          imgAnalysis.image_path
            ? `
          <img src="${PHP_BASE}/${imgAnalysis.image_path}" alt="Symptom Image" style="max-width:100%;max-height:250px;border-radius:8px;margin-bottom:12px;display:block;border:1px solid var(--border)">
        `
            : ""
        }
        <div style="font-weight:500">${escHtml(imgAnalysis.image_type || "Symptom image")}</div>
        <p>${escHtml((imgAnalysis.visible_observations || []).join(" ") || imgAnalysis.possible_relevance || "Image was included as supportive context.")}</p>
        ${(imgAnalysis.red_flags || []).length ? `<p style="color:var(--red-danger);font-weight:500">Red flags: ${escHtml(imgAnalysis.red_flags.join(", "))}</p>` : ""}
        <p class="text-muted">Confidence: ${escHtml(imgAnalysis.confidence || "low")}. Clinician review recommended.</p>
      </div>
    </div>
  `
    : "";

  document.getElementById("reportContent").innerHTML = `
    <div class="report-header" style="margin:-28px -28px 24px;padding:24px 28px;background:var(--teal);color:#fff;border-radius:var(--radius-lg) var(--radius-lg) 0 0">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;opacity:0.7;margin-bottom:8px">Triage Report</div>
      <div class="condition-name" style="color:#fff">${escHtml(r.possible_condition || "-")}</div>
      <div style="margin-top:8px"><span class="badge ${urgencyClass}" style="background:rgba(255,255,255,0.2);color:#fff">${(r.urgency || "medium").toUpperCase()} URGENCY</span></div>
    </div>

    <div class="report-section">
      <h4>Symptoms reported</h4>
      <ul class="symptoms-list">${symptoms}</ul>
    </div>

    ${imageSection}

    <div class="report-section">
      <h4>AI reasoning</h4>
      <p>${escHtml(r.reasoning || "-")}</p>
    </div>

    <div class="report-section">
      <h4>Recommended specialist</h4>
      <p style="font-weight:500">${escHtml(r.recommended_specialist || "-")}</p>
    </div>

    <div class="report-section" id="doctorSuggestions">
      <h4>Relevant doctors</h4>
      <p class="text-muted">Loading matched doctors...</p>
    </div>

    <div class="report-section">
      <h4>Guidance</h4>
      <p>${escHtml(r.guidance || "-")}</p>
    </div>

    <div style="font-size:11px;color:var(--ink-muted);margin-top:16px">
      Generated: ${new Date(r.generated_at || Date.now()).toLocaleString()}<br>
      <em>This is AI-assisted triage only. Always consult a qualified medical professional.</em>
    </div>

    <div style="margin-top:20px">
      <a href="${doctorLinkForReport(r)}" class="btn-primary" style="display:block;text-align:center;font-size:14px;padding:12px">Find a ${escHtml(r.recommended_specialist || "Doctor")} -></a>
    </div>
  `;
}

async function loadDoctorSuggestions(report) {
  const el = document.getElementById("doctorSuggestions");
  if (!el) return;
  const params = new URLSearchParams();
  if (report?.recommended_specialist)
    params.set("specialization", report.recommended_specialist);
  if (primarySymptom) params.set("symptom", primarySymptom);
  if (report?.possible_condition)
    params.set("possible_condition", report.possible_condition);
  if (report?.urgency) params.set("urgency", report.urgency);
  params.set("report_text", reportContextText(report).slice(0, 700));
  params.set("limit", "3");

  try {
    const res = await fetch(
      `${AI_BASE}/doctor-recommendation?${params.toString()}`,
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not load doctors.");
    const doctors = data.doctors || [];
    if (!doctors.length) {
      el.innerHTML =
        '<h4>Relevant doctors</h4><p class="text-muted">No doctor matches found yet.</p>';
      return;
    }
    el.innerHTML =
      "<h4>Relevant doctors</h4>" +
      doctors
        .map(
          (d) => `
      <div style="padding:10px 0;border-bottom:1px solid var(--border)">
        <div style="font-weight:500">${escHtml(d.doctor_name)}</div>
        <div class="text-muted">${escHtml(d.specialization)} | ${escHtml(d.location || "Location not listed")}</div>
        ${d.match_reason ? `<div class="text-muted">${escHtml(d.match_reason)}</div>` : ""}
      </div>
    `,
        )
        .join("") +
      `<a href="${doctorLinkForReport(report)}" class="btn-book" style="margin-top:14px">View and book matched doctors</a>`;
  } catch {
    el.innerHTML = `<h4>Relevant doctors</h4><a href="${doctorLinkForReport(report)}" class="btn-book">View matched doctors</a>`;
  }
}

function openReport() {
  document.getElementById("reportPanel").classList.add("open");
}
function closeReport() {
  document.getElementById("reportPanel").classList.remove("open");
}

document.addEventListener("DOMContentLoaded", () => {
  const u = getUser();
  const el = document.getElementById("sidebarUserName");
  if (el) el.textContent = u ? u.first_name + " " + u.last_name : "Guest";
  setSendDisabled(false);
});
