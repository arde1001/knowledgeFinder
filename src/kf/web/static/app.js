"use strict";

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};
const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* private window: the choice just is not remembered */ } },
};
const ROLE_LABEL = { "test.board": "Board", "test.leader": "Leader", "test.committee_member": "Committee member" };
const roleClass = (role) => role.replace(/^test\./, "");
const prettyName = (id) => id.split(".").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");

let user = null;
let session = (crypto.randomUUID && crypto.randomUUID()) || String(Math.random()).slice(2);
let busy = false;

function banner(text) {
  $("banner").hidden = !text;
  $("banner").textContent = text || "";
}

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function emptyState(questions) {
  const box = el("div", "empty");
  box.append(el("strong", "", "Ask about the association"));
  box.append(el("p", "", questions ? "Pick a test question on the left, or type your own. Then switch user and ask the same thing." : "Type a question below."));
  return box;
}

function clearChat() {
  const log = $("log");
  log.replaceChildren(emptyState(window.hasTests));
}

function addMessage(kind) {
  const log = $("log");
  if (log.querySelector(".empty")) log.replaceChildren();
  const msg = el("div", `msg ${kind}`);
  log.append(msg);
  log.scrollTop = log.scrollHeight;
  return msg;
}

function renderAnswer(msg, data) {
  msg.replaceChildren(el("div", "who", "Expert"));
  for (const part of data.answer.split(/\n+/).filter(Boolean)) msg.append(el("p", "", part));
  if (data.sources.length) {
    const box = el("div", "sources");
    box.append(el("h3", "", "Sources"));
    const list = el("ol");
    for (const s of data.sources) {
      const li = el("li");
      li.append(el("span", "n", `[${s.n}]`));
      const body = el("span");
      body.append(el("code", "", s.path));
      body.append(el("small", "", `${s.drive}, created ${s.created}`));
      li.append(body);
      list.append(li);
    }
    box.append(list);
    msg.append(box);
  }
  if (data.notice) {
    const box = el("div", "notice");
    box.append($("lock-icon").content.cloneNode(true));
    box.append(el("span", "", data.notice));
    msg.append(box);
  }
}

// The answer, shown as it is generated. The final event replaces the streamed text (the server may rewrite it: NOT_FOUND, citations).
// Falls back to /api/ask when the stream cannot be opened or breaks before the first word; an error event is reported as is.
async function fetchAnswer(msg, payload) {
  let started = false;
  try {
    const res = await fetch("/api/ask_stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", text = "", final = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      for (let end; (end = buffer.indexOf("\n\n")) >= 0;) {
        const block = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const name = /^event: (\w+)/m.exec(block)?.[1];
        const data = JSON.parse(/^data: (.*)$/m.exec(block)?.[1] || "{}");
        if (name === "delta") {
          started = true;
          text += data.text;
          renderAnswer(msg, { answer: text, sources: [], notice: null });
          $("log").scrollTop = $("log").scrollHeight;
        } else if (name === "final") final = data;
        else if (name === "error") throw Object.assign(new Error(data.error), { reported: true });
      }
    }
    if (!final) throw new Error("The answer stopped early.");
    return final;
  } catch (err) {
    if (started || err.reported) throw err;
    return api("/api/ask", payload);
  }
}

async function ask(question) {
  if (busy || !question.trim()) return;
  busy = true;
  $("send").disabled = true;
  banner("");
  addMessage("user").append(el("p", "", question));
  const msg = addMessage("bot");
  msg.setAttribute("aria-busy", "true");
  const dots = el("span", "thinking");
  dots.append(el("span"), el("span"), el("span"));
  msg.append(dots);
  try {
    renderAnswer(msg, await fetchAnswer(msg, { user, session, question }));
  } catch (err) {
    msg.remove();
    banner(err.message);
  } finally {
    msg.removeAttribute("aria-busy");
    busy = false;
    $("send").disabled = false;
    $("log").scrollTop = $("log").scrollHeight;
    $("question").focus();
  }
}

async function selectUser(id) {
  user = id;
  store.set("kf-user", id);
  session = (crypto.randomUUID && crypto.randomUUID()) || String(Math.random()).slice(2);
  const me = await api(`/api/me?user=${encodeURIComponent(id)}`);
  const roles = $("roles");
  roles.replaceChildren(...me.roles.map((r) => el("span", `chip ${roleClass(r)}`, ROLE_LABEL[r] || r)));
  if (!me.roles.length) roles.append(el("span", "chip", "No role"));
  $("drives").replaceChildren(...me.drives.map((d) => {
    const li = el("li", "", d.name);
    if (d.label) { li.append(el("small", "", d.label)); li.title = d.label; }
    return li;
  }));
  $("shared").replaceChildren(...me.shared.map((n) => el("li", "", n)));
  $("shared-wrap").hidden = !me.shared.length;
  $("chat-title").textContent = `Asking as ${prettyName(id)}`;
  clearChat();
}

async function init() {
  try {
    const data = await api("/api/users");
    const groups = new Map();
    for (const u of data.users) {
      const key = u.roles[0] || "";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(u);
    }
    const select = $("user");
    for (const [role, users] of groups) {
      const group = document.createElement("optgroup");
      group.label = ROLE_LABEL[role] || role || "No role";
      for (const u of users) {
        const o = el("option", "", prettyName(u.id));
        o.value = u.id;
        group.append(o);
      }
      select.append(group);
    }
    window.hasTests = data.questions.length > 0;
    $("tests-card").hidden = !window.hasTests;
    $("tests").replaceChildren(...data.questions.map((q) => {
      const li = el("li");
      const b = el("button", "");
      b.type = "button";
      b.append(el("small", "", q.drive), document.createTextNode(q.question));
      b.addEventListener("click", () => { $("question").value = q.question; $("question").focus(); });
      li.append(b);
      return li;
    }));
    const saved = store.get("kf-user");
    const first = data.users.find((u) => u.id === saved) || data.users.find((u) => u.roles[0] === "test.board") || data.users[0];
    select.value = first.id;
    await selectUser(first.id);
  } catch (err) {
    banner(err.message);
  }
}

$("user").addEventListener("change", (e) => selectUser(e.target.value).catch((err) => banner(err.message)));
$("new-chat").addEventListener("click", () => {
  api("/api/reset", { user, session }).catch(() => {});
  session = (crypto.randomUUID && crypto.randomUUID()) || String(Math.random()).slice(2);
  clearChat();
});
$("form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("question").value;
  $("question").value = "";
  ask(q);
});
$("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("form").requestSubmit();
  }
});
init();
