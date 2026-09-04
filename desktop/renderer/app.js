/** Evidence Copilot 桌面 UI */

const EXCLUSION_PRESETS = [
  "Wrong population",
  "Wrong intervention",
  "Wrong comparator",
  "Wrong outcome",
  "Wrong study design",
  "Wrong publication type",
  "Animal study",
  "Not relevant",
  "Other",
];

const SCREENING_STATUSES = ["Unscreened", "Include", "Maybe", "Exclude"];

const state = {
  projectId: null,
  proposedQuery: "",
  streamText: "",
  records: [],
  stats: {},
  pendingUiRequestId: null,
};

const $ = (id) => document.getElementById(id);

function setStatus(text) {
  $("status").textContent = text;
}

function appendStream(line) {
  state.streamText += `${line}\n`;
  $("agentStream").textContent = state.streamText.trim();
}

function renderPico(blocks) {
  const container = $("picoBlocks");
  container.innerHTML = "";
  for (const block of blocks || []) {
    const div = document.createElement("div");
    div.className = "block";
    div.innerHTML = `<strong>${block.label}</strong>${block.text}`;
    container.appendChild(div);
  }
}

function renderUncertainties(items) {
  const list = $("uncertainties");
  list.innerHTML = "";
  for (const item of items || []) {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  }
}

function renderStats(stats) {
  if (!stats || !Object.keys(stats).length) {
    $("screeningStats").textContent = "";
    return;
  }
  $("screeningStats").textContent = SCREENING_STATUSES.map(
    (key) => `${key}：${stats[key] ?? 0}`,
  ).join(" · ");
}

function renderRecords(result) {
  if (result?.records) {
    state.records = result.records;
  }
  if (result?.stats) {
    state.stats = result.stats;
  }
  $("searchSummary").textContent = result
    ? `检索式：${result.query}\n命中：${result.total_hits}；已拉回：${result.retrieved}`
    : "";
  renderStats(state.stats);
  $("exportActions").hidden = !state.records.length;

  const container = $("records");
  container.innerHTML = "";
  for (const record of state.records) {
    const div = document.createElement("div");
    div.className = "record";
    div.dataset.pmid = record.pmid;

    const title = document.createElement("div");
    title.className = "record-title";
    title.innerHTML = `<strong>PMID ${record.pmid}</strong> · ${record.title || "（无标题）"}<br/><span>${record.journal || ""} ${record.publication_year || ""}</span>`;
    div.appendChild(title);

    const statusRow = document.createElement("div");
    statusRow.className = "record-status";
    for (const status of SCREENING_STATUSES) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `status-btn ${record.screening_status === status ? "active" : ""}`;
      btn.textContent = status;
      btn.addEventListener("click", () => updateScreening(record.pmid, status, div));
      statusRow.appendChild(btn);
    }
    div.appendChild(statusRow);

    const excludeRow = document.createElement("div");
    excludeRow.className = "record-exclude";
    excludeRow.hidden = record.screening_status !== "Exclude";
    const select = document.createElement("select");
    select.innerHTML = `<option value="">选择排除原因</option>${EXCLUSION_PRESETS.map(
      (item) => `<option value="${item}" ${record.exclusion_reason === item ? "selected" : ""}>${item}</option>`,
    ).join("")}`;
    select.addEventListener("change", () => {
      if (select.value) {
        updateScreening(record.pmid, "Exclude", div, select.value);
      }
    });
    excludeRow.appendChild(select);
    div.appendChild(excludeRow);

    container.appendChild(div);
  }
}

async function updateScreening(pmid, status, recordEl, exclusionReason = null) {
  if (!state.projectId) {
    return;
  }
  if (status === "Exclude" && !exclusionReason) {
    recordEl.querySelector(".record-exclude").hidden = false;
    setStatus("请选择排除原因");
    return;
  }
  try {
    const result = await window.evidenceCopilot.updateScreening({
      project_id: state.projectId,
      pmid,
      status,
      exclusion_reason: exclusionReason,
    });
    const index = state.records.findIndex((item) => item.pmid === pmid);
    if (index >= 0 && result.record) {
      state.records[index] = result.record;
    }
    state.stats = result.stats || state.stats;
    renderRecords({ records: state.records, stats: state.stats });
    setStatus(`已更新 PMID ${pmid} → ${status}`);
  } catch (err) {
    setStatus(`初筛失败：${err.message}`);
  }
}

async function loadSettingsIntoForm() {
  const settings = await window.evidenceCopilot.getSettings();
  $("settingsNcbiEmail").value = settings.ncbi_email || "";
  $("settingsNcbiKeyHint").textContent = settings.ncbi_api_key_set
    ? `已保存：${settings.ncbi_api_key_hint}`
    : "尚未设置";
  $("settingsDeepseekKeyHint").textContent = settings.deepseek_api_key_set
    ? `已保存：${settings.deepseek_api_key_hint}`
    : "尚未设置";
  return settings;
}

async function checkSettingsHint() {
  try {
    const settings = await window.evidenceCopilot.getSettings();
    if (!settings.has_ncbi_email) {
      setStatus("请先在设置中填写 NCBI 邮箱");
    }
  } catch (err) {
    setStatus(`侧车未就绪：${err.message}`);
  }
}

async function init() {
  try {
    await window.evidenceCopilot.pingSidecar();
    await checkSettingsHint();
  } catch (err) {
    setStatus(`侧车未就绪：${err.message}`);
  }

  window.evidenceCopilot.onPiEvent((event) => {
    if (event.type === "message_update") {
      const delta = event.assistantMessageEvent;
      if (delta?.type === "text_delta" && delta.delta) {
        appendStream(delta.delta);
      }
    }
    if (event.type === "extension_ui_request" && event.method === "confirm") {
      state.pendingUiRequestId = event.id;
      $("approvalTitle").textContent = event.title || "需要你的确认";
      $("approvalText").textContent = event.message || "";
      $("approvalDock").hidden = false;
      return;
    }
    if (event.type === "tool_execution_start") {
      appendStream(`[Pi] 工具开始：${event.toolName}`);
    }
    if (event.type === "tool_execution_end") {
      appendStream(`[Pi] 工具结束：${event.toolName}`);
    }
    if (event.type === "agent_end" || event.type === "agent_settled") {
      setStatus("Agent 就绪");
    }
  });
}

$("btnSettings").addEventListener("click", async () => {
  await loadSettingsIntoForm();
  $("settingsDialog").showModal();
});

$("btnSettingsCancel").addEventListener("click", () => {
  $("settingsDialog").close();
});

$("settingsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = {
      ncbi_email: $("settingsNcbiEmail").value.trim(),
    };
    const ncbiKey = $("settingsNcbiKey").value.trim();
    const deepseekKey = $("settingsDeepseekKey").value.trim();
    if (ncbiKey) {
      payload.ncbi_api_key = ncbiKey;
    }
    if (deepseekKey) {
      payload.deepseek_api_key = deepseekKey;
    }
    await window.evidenceCopilot.saveSettings(payload);
    $("settingsNcbiKey").value = "";
    $("settingsDeepseekKey").value = "";
    $("settingsDialog").close();
    setStatus("设置已保存");
  } catch (err) {
    setStatus(`保存失败：${err.message}`);
  }
});

$("btnPropose").addEventListener("click", async () => {
  const researchIdea = $("researchIdea").value.trim();
  if (!researchIdea) {
    setStatus("请先输入研究想法");
    return;
  }
  setStatus("正在生成检索提议…");
  try {
    const result = await window.evidenceCopilot.proposeSearch({
      research_idea: researchIdea,
      project_id: state.projectId,
    });
    state.projectId = result.project_id;
    state.proposedQuery = result.proposed_query || "";
    $("proposedQuery").value = state.proposedQuery;
    renderPico(result.pico_blocks);
    renderUncertainties(result.uncertainties);
    $("btnApprove").disabled = false;
    setStatus("已生成提议，请确认检索式");
    appendStream(`[系统] 已生成检索提议 project=${result.project_id}`);
  } catch (err) {
    setStatus(`提议失败：${err.message}`);
  }
});

$("btnApprove").addEventListener("click", async () => {
  if (!state.projectId) {
    setStatus("缺少 project_id");
    return;
  }
  const query = $("proposedQuery").value.trim();
  setStatus("正在执行 PubMed…");
  try {
    const result = await window.evidenceCopilot.runPubmedSearch({
      project_id: state.projectId,
      query,
      approved: true,
    });
    renderRecords(result);
    setStatus(`PubMed 完成：${result.retrieved} 篇`);
    appendStream(`[系统] PubMed 检索完成 search_id=${result.search_id}`);
  } catch (err) {
    setStatus(`检索失败：${err.message}`);
  }
});

async function exportFormat(format) {
  if (!state.projectId) {
    setStatus("尚无项目可导出");
    return;
  }
  try {
    const result = await window.evidenceCopilot.exportProject({
      project_id: state.projectId,
      format,
    });
    const saved = await window.evidenceCopilot.saveFile({
      filename: result.filename,
      content: result.content,
    });
    if (saved.cancelled) {
      setStatus("已取消导出");
      return;
    }
    setStatus(`已导出：${saved.path}`);
  } catch (err) {
    setStatus(`导出失败：${err.message}`);
  }
}

$("btnExportRis").addEventListener("click", () => exportFormat("ris"));
$("btnExportCsv").addEventListener("click", () => exportFormat("csv"));
$("btnExportSnapshot").addEventListener("click", () => exportFormat("snapshot"));

$("btnPiAgent").addEventListener("click", async () => {
  const researchIdea = $("researchIdea").value.trim();
  if (!researchIdea) {
    setStatus("请先输入研究想法");
    return;
  }
  setStatus("Pi Agent 思考中…");
  state.streamText = "";
  $("agentStream").textContent = "";
  const prompt = [
    "用户研究想法：",
    researchIdea,
    "",
    "请先调用 propose_pubmed_search 生成检索提议，不要直接 run_pubmed_search。",
    "等用户在界面确认后再执行检索。",
  ].join("\n");
  try {
    await window.evidenceCopilot.sendPiPrompt(prompt);
  } catch (err) {
    setStatus(`Pi 不可用：${err.message}（可先使用「开始评估」按钮）`);
  }
});

async function respondPiConfirm(confirmed) {
  if (!state.pendingUiRequestId) {
    $("approvalDock").hidden = true;
    return;
  }
  await window.evidenceCopilot.sendPiUiResponse({
    type: "extension_ui_response",
    id: state.pendingUiRequestId,
    confirmed,
  });
  state.pendingUiRequestId = null;
  $("approvalDock").hidden = true;
  appendStream(confirmed ? "[用户] 已批准" : "[用户] 已拒绝");
}

$("btnAllow").addEventListener("click", () => {
  respondPiConfirm(true).catch((err) => setStatus(`审批失败：${err.message}`));
});

$("btnReject").addEventListener("click", () => {
  respondPiConfirm(false).catch((err) => setStatus(`审批失败：${err.message}`));
});

init();
