// Alarm Investigation Copilot - front-end logic (plain JavaScript, no build step)

let currentThreadId = null;
let latestResult = null;

// ---------- small helpers ----------

function escapeHtml(value) {
    // Everything that comes from the API or documents is escaped before it is put in the page
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function inlineMarkdown(text) {
    // text is already escaped; only add simple formatting
    return text
        .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
        .replace(/\*(.+?)\*/g, "<i>$1</i>")
        .replace(/`(.+?)`/g, "<code>$1</code>");
}

function renderMarkdown(markdown) {
    // Tiny markdown renderer (headings, bold, italics, lists).
    // We escape FIRST, so text from the LLM or documents can never inject HTML or scripts.
    const lines = escapeHtml(markdown).split("\n");
    let html = "";
    let inList = false;
    for (const raw of lines) {
        const line = raw.trimEnd();
        const item = line.match(/^(\s*)[-*] (.*)$/) || line.match(/^(\s*)\d+\. (.*)$/);
        if (item) {
            if (!inList) { html += "<ul>"; inList = true; }
            const nested = item[1].length >= 2 ? ' class="nested"' : "";
            html += `<li${nested}>${inlineMarkdown(item[2])}</li>`;
            continue;
        }
        if (inList) { html += "</ul>"; inList = false; }
        const heading = line.match(/^#{1,6} (.*)$/);
        if (heading) html += `<h3>${inlineMarkdown(heading[1])}</h3>`;
        else if (line.trim()) html += `<p>${inlineMarkdown(line)}</p>`;
    }
    if (inList) html += "</ul>";
    return html;
}

function prettyJson(value) {
    return escapeHtml(JSON.stringify(value, null, 2));
}

function badge(text, kind) {
    return `<span class="tag tag-${escapeHtml(kind)}">${escapeHtml(text)}</span>`;
}

function setPrompt(text) {
    document.getElementById("userInput").value = text;
    document.getElementById("userInput").focus();
}

function setLoading(isLoading) {
    document.getElementById("sendBtn").disabled = isLoading;
    document.getElementById("btnText").classList.toggle("hidden", isLoading);
    document.getElementById("btnLoader").classList.toggle("hidden", !isLoading);
}

function showError(message) {
    const box = document.getElementById("errorBox");
    box.textContent = message;
    box.classList.remove("hidden");
}

function hideError() {
    document.getElementById("errorBox").classList.add("hidden");
}

// ---------- chat ----------

function addChatMessage(role, html) {
    const log = document.getElementById("chatLog");
    const empty = log.querySelector(".empty-state");
    if (empty) empty.remove();

    const div = document.createElement("div");
    div.className = `msg msg-${role}`;
    div.innerHTML = html;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
}

async function sendMessage() {
    hideError();
    const input = document.getElementById("userInput");
    const message = input.value.trim();

    if (!message) {
        showError("Please type a question first.");
        return;
    }

    addChatMessage("user", escapeHtml(message));
    input.value = "";
    setLoading(true);
    const thinking = addChatMessage("bot", '<span class="muted">Planning, calling MCP tools and searching documents...</span>');

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: message, thread_id: currentThreadId })
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            const detail = data.error || (data.detail && JSON.stringify(data.detail)) || "Something went wrong.";
            throw new Error(detail);
        }

        currentThreadId = data.thread_id;
        document.getElementById("threadInfo").textContent = `conversation ${data.thread_id}`;
        latestResult = data;

        const source = data.answer_source === "llm" ? "LLM answer" : "template answer";
        thinking.innerHTML = renderMarkdown(data.answer_markdown) +
            `<div class="msg-meta">${escapeHtml(source)} - intent: ${escapeHtml(data.intent)} - trace ${escapeHtml(data.trace_id || "-")}</div>`;
        renderEvidence(data);

    } catch (error) {
        thinking.innerHTML = '<span class="error-text">Could not get an answer.</span>';
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

function newConversation() {
    currentThreadId = null;
    latestResult = null;
    document.getElementById("threadInfo").textContent = "";
    document.getElementById("chatLog").innerHTML =
        '<div class="empty-state">New conversation started. Ask about an asset or site.</div>';
    document.getElementById("evidence").classList.add("hidden");
    document.getElementById("evidenceEmpty").classList.remove("hidden");
}

// ---------- evidence panels ----------

function renderEvidence(data) {
    document.getElementById("evidenceEmpty").classList.add("hidden");
    document.getElementById("evidence").classList.remove("hidden");

    renderSummary(data);
    renderWarnings(data.warnings || []);
    renderCauses(data.likely_causes || []);
    renderRecommendations(data.recommendations || []);
    renderRelated(data.related_assets || []);
    renderCitations(data.citations || [], data.retrieval || {});
    renderTrace(data.trace || []);
}

function renderSummary(data) {
    const s = data.alarm_summary || {};
    const kpis = [
        ["Alarms", s.total_alarms ?? "-"],
        ["Active now", s.active_count ?? 0],
        ["Window", `${s.days ?? "-"} days`],
        ["Trend", s.trend_direction || "-"],
    ];
    document.getElementById("kpis").innerHTML = kpis
        .map(([label, value]) => `<div class="kpi"><div class="kpi-value">${escapeHtml(value)}</div><div class="kpi-label">${escapeHtml(label)}</div></div>`)
        .join("");

    const f = data.focus_alarm;
    document.getElementById("focusAlarm").innerHTML = f
        ? `<div class="focus">Focus alarm: <b>${escapeHtml(f.alarm_name)}</b> on ${escapeHtml(f.asset_name)}
           ${badge(f.severity, f.severity)} ${badge(f.status, f.status)}
           ${f.priority_level ? badge(`${f.priority_level} ${f.priority_score}/100`, "priority") : ""}
           <div class="muted">${escapeHtml(f.priority_explanation || f.alarm_id)}</div></div>`
        : '<div class="muted">No alarm selected.</div>';

    const rows = data.alarms_table || [];
    const table = document.getElementById("alarmTable");
    if (!rows.length) {
        table.innerHTML = '<tr><td class="muted">No alarms in scope.</td></tr>';
        return;
    }
    table.innerHTML = "<tr><th>Alarm</th><th>Asset</th><th>Name</th><th>Severity</th><th>Status</th><th>Start (UTC)</th></tr>" +
        rows.map(a => `<tr><td>${escapeHtml(a.alarm_id)}</td><td>${escapeHtml(a.asset_name)}</td><td>${escapeHtml(a.alarm_name)}</td>
            <td>${badge(a.severity, a.severity)}</td><td>${badge(a.status, a.status)}</td><td>${escapeHtml(a.start_time)}</td></tr>`).join("");
}

function renderWarnings(warnings) {
    const card = document.getElementById("warningsCard");
    card.classList.toggle("hidden", warnings.length === 0);
    document.getElementById("warnings").innerHTML = warnings.map(w => `<li>${escapeHtml(w)}</li>`).join("");
}

function renderCauses(causes) {
    const list = document.getElementById("causes");
    if (!causes.length) {
        list.innerHTML = '<li class="muted">No cause evidence for this question.</li>';
        return;
    }
    list.innerHTML = causes.map(c =>
        `<li>${badge(c.kind, c.kind)} ${escapeHtml(c.cause)} <span class="ref">[${escapeHtml(c.ref || "-")}]</span></li>`).join("");
}

function renderRecommendations(recs) {
    const list = document.getElementById("recommendations");
    if (!recs.length) {
        list.innerHTML = '<li class="muted">No recommendations were requested or available.</li>';
        return;
    }
    const labels = { supported: "supported by docs", conflict: "conflicts with docs", not_covered: "not in docs - verify" };
    list.innerHTML = recs.map(r => `
        <li>
            ${badge(labels[r.doc_check], r.doc_check)} ${badge(r.urgency, "urgency")}
            ${escapeHtml(r.action)}
            <span class="ref">[${escapeHtml(r.api_ref || "API")}${r.doc_ref ? ", " + escapeHtml(r.doc_ref) : ""}]</span>
            ${r.doc_sentence ? `<div class="doc-quote">Document: "${escapeHtml(r.doc_sentence)}"</div>` : ""}
        </li>`).join("");
}

function renderRelated(assets) {
    const list = document.getElementById("relatedAssets");
    list.innerHTML = assets.length
        ? assets.map(a => `<li><b>${escapeHtml(a.asset_name)}</b> <span class="muted">(${escapeHtml(a.relationship)})</span> - ${escapeHtml(a.reasons.join(", "))}</li>`).join("")
        : '<li class="muted">No related assets.</li>';
}

function renderCitations(citations, retrieval) {
    document.getElementById("retrievalInfo").textContent =
        retrieval.status ? `(retrieval: ${retrieval.status})` : "";
    const box = document.getElementById("citations");
    if (!citations.length) {
        box.innerHTML = '<div class="muted">No documents were used.</div>';
        return;
    }
    box.innerHTML = citations.map(c => `
        <details class="item">
            <summary>
                <b>[${escapeHtml(c.ref)}]</b> ${escapeHtml(c.doc_id)} - ${escapeHtml(c.title)}
                <span class="muted">section "${escapeHtml(c.section)}" - score ${escapeHtml(c.score)}</span>
                ${c.injection_removed ? badge("injection removed", "conflict") : ""}
                ${c.trust_level === "external" ? badge("external source", "not_covered") : ""}
            </summary>
            <div class="muted">${escapeHtml(c.doc_type)} - ${escapeHtml(c.source_file)} - chunk ${escapeHtml(c.chunk_id)}</div>
            <pre class="doc-text">${escapeHtml(c.text)}</pre>
        </details>`).join("");
}

function renderTrace(trace) {
    const retries = trace.reduce((sum, s) => sum + Math.max(0, (s.attempts || 1) - 1), 0);
    const failed = trace.filter(s => s.status !== "success").length;
    document.getElementById("traceInfo").textContent =
        `(${trace.length} steps, ${failed} failed, ${retries} retries)`;

    document.getElementById("trace").innerHTML = trace.map(s => `
        <details class="item">
            <summary>
                <b>T${escapeHtml(s.step)}</b> ${escapeHtml(s.tool)}
                ${badge(s.status, s.status)}
                <span class="muted">${escapeHtml(s.duration_ms)} ms - attempts ${escapeHtml(s.attempts ?? "-")}
                ${s.api_status ? " - API " + escapeHtml(s.api_status) : ""}</span>
                <div class="muted small">${escapeHtml(s.purpose || "")}</div>
            </summary>
            <div class="muted small">server: ${escapeHtml(s.server)} - trace_id: ${escapeHtml(s.trace_id)}</div>
            ${s.error ? `<div class="error-text">${escapeHtml(s.error)}</div>` : ""}
            <div class="label">Request</div><pre>${prettyJson(s.request)}</pre>
            ${s.response ? `<div class="label">Response</div><pre>${prettyJson(s.response)}</pre>` : ""}
        </details>`).join("");
}

// ---------- tool discovery ----------

async function toggleTools() {
    const panel = document.getElementById("toolsPanel");
    panel.classList.toggle("hidden");
    if (panel.classList.contains("hidden")) return;

    const list = document.getElementById("toolsList");
    list.textContent = "Loading tools...";
    try {
        const response = await fetch("/api/tools");
        const data = await response.json();
        if (!data.success) throw new Error(data.error);
        list.innerHTML = data.tools.map(t => `
            <details class="item">
                <summary><b>${escapeHtml(t.name)}</b> <span class="muted">${escapeHtml(t.description)}</span></summary>
                <div class="label">Input schema</div><pre>${prettyJson(t.input_schema)}</pre>
                <div class="label">Output schema</div><pre>${prettyJson(t.output_schema)}</pre>
            </details>`).join("");
    } catch (error) {
        list.innerHTML = `<div class="error-text">${escapeHtml(error.message)}</div>`;
    }
}

// ---------- export ----------

function download(filename, text, type) {
    const blob = new Blob([text], { type: type });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
}

function exportJson() {
    if (latestResult) download("alarm-investigation.json", JSON.stringify(latestResult, null, 2), "application/json");
}

function exportMarkdown() {
    if (!latestResult) return;
    const sources = (latestResult.citations || []).map(c => `- [${c.ref}] ${c.doc_id} - ${c.title}, section "${c.section}"`).join("\n");
    const tools = (latestResult.trace || []).map(s => `- T${s.step} ${s.tool}: ${s.status}`).join("\n");
    download("alarm-investigation.md",
        `${latestResult.answer_markdown}\n\n## Sources\n${sources}\n\n## MCP trace (${latestResult.trace_id})\n${tools}\n`,
        "text/markdown");
}

// ---------- startup ----------

async function checkHealth() {
    const pill = document.getElementById("statusPill");
    try {
        const response = await fetch("/health");
        pill.innerHTML = response.ok ? '<span class="status-dot"></span>Online' : '<span class="status-dot off"></span>Degraded';
    } catch {
        pill.innerHTML = '<span class="status-dot off"></span>Offline';
    }
}

document.addEventListener("keydown", event => {
    if (event.ctrlKey && event.key === "Enter") sendMessage();
});

checkHealth();
