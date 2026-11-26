// The Halcyon page. Draws the events of ui/session.py and calls the Python bridge in ui/app.py.
// Opened in a plain browser (no pywebview), or with ?demo=1, it plays sample events and keeps
// sample chats in memory instead, so the design can be worked on without a model.
(function () {
  "use strict";

  // ---------------------------------------------------------------- words
  const TEXT = {
    en: {
      "status.loading": "Loading", "status.ready": "Ready", "status.listening": "Listening",
      "status.transcribing": "Hearing you", "status.thinking": "Thinking", "status.speaking": "Speaking",
      "status.error": "Something went wrong",
      "mode.general": "general mode", "mode.deep": "deep mode", "mode.research": "research mode",
      "welcome.title": "Your assistant, on your own computer.",
      "welcome.hint": "Type below, or turn on the microphone and talk.",
      "input.placeholder": "Message Halcyon", "input.voice": "The microphone is on: talk to Halcyon",
      "mic.on": "Turn the microphone on", "mic.off": "Turn the microphone off", "send": "Send",
      "via.voice": "spoken", "interrupted": "interrupted",
      "busy": "Not sent: Halcyon is still busy. Your message is kept.",
      "busy.switch": "Halcyon is still busy: wait for the reply, or turn the microphone off first.",
      "chat.new": "New chat", "chats.label": "Chats", "chats.toggle": "Show or hide the chats",
      "chats.empty": "No chats yet. What you write is kept here.",
      "group.pinned": "Pinned", "group.today": "Today", "group.yesterday": "Yesterday",
      "group.week": "This week", "group.older": "Older",
      "action.pin": "Pin", "action.unpin": "Unpin", "action.rename": "Rename", "action.delete": "Delete",
      "confirm.delete": "Delete?", "confirm.yes": "Delete", "confirm.no": "Keep",
      "history.local": "Chats are kept only on this computer.",
      "history.off": "Chats are not being saved.",
      "copy": "Copy", "copied": "Copied", "copy.failed": "Could not copy",
    },
    tr: {
      "status.loading": "Yükleniyor", "status.ready": "Hazır", "status.listening": "Dinliyor",
      "status.transcribing": "Seni anlıyor", "status.thinking": "Düşünüyor", "status.speaking": "Konuşuyor",
      "status.error": "Bir sorun oluştu",
      "mode.general": "genel mod", "mode.deep": "derin mod", "mode.research": "araştırma modu",
      "welcome.title": "Asistanın, kendi bilgisayarında.",
      "welcome.hint": "Aşağıya yaz ya da mikrofonu açıp konuş.",
      "input.placeholder": "Halcyon'a yaz", "input.voice": "Mikrofon açık: Halcyon'la konuş",
      "mic.on": "Mikrofonu aç", "mic.off": "Mikrofonu kapat", "send": "Gönder",
      "via.voice": "sesli", "interrupted": "kesildi",
      "busy": "Gönderilmedi: Halcyon hâlâ meşgul. Mesajın duruyor.",
      "busy.switch": "Halcyon hâlâ meşgul: cevabı bekle ya da önce mikrofonu kapat.",
      "chat.new": "Yeni sohbet", "chats.label": "Sohbetler", "chats.toggle": "Sohbetleri göster ya da gizle",
      "chats.empty": "Henüz sohbet yok. Yazdıkların burada saklanır.",
      "group.pinned": "Sabitlenenler", "group.today": "Bugün", "group.yesterday": "Dün",
      "group.week": "Bu hafta", "group.older": "Daha eski",
      "action.pin": "Sabitle", "action.unpin": "Sabitlemeyi kaldır", "action.rename": "Yeniden adlandır",
      "action.delete": "Sil",
      "confirm.delete": "Silinsin mi?", "confirm.yes": "Sil", "confirm.no": "Vazgeç",
      "history.local": "Sohbetler yalnızca bu bilgisayarda saklanır.",
      "history.off": "Sohbetler kaydedilmiyor.",
      "copy": "Kopyala", "copied": "Kopyalandı", "copy.failed": "Kopyalanamadı",
    },
  };

  const params = new URLSearchParams(location.search);
  let demoMode = params.has("demo");     // or the window's --demo, which the bridge reports

  function storedGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function storedSet(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private window */ } }

  // The language the user picked here, else the one Windows lists first (sent by ui/app.py), else
  // the web view's own, which follows the display language and was English for a Turkish user.
  function initialLanguage() {
    const picked = storedGet("halcyon.lang");
    if (picked === "tr" || picked === "en") return picked;
    const given = params.get("lang");
    if (given === "tr" || given === "en") return given;
    return (navigator.language || "en").toLowerCase().startsWith("tr") ? "tr" : "en";
  }
  let lang = initialLanguage();
  const t = (key) => (TEXT[lang] && TEXT[lang][key]) || TEXT.en[key] || key;

  // ---------------------------------------------------------------- elements
  const $ = (id) => document.getElementById(id);
  const conversation = $("conversation");
  const welcome = $("welcome");
  const input = $("input");
  const send = $("send");
  const mic = $("mic");
  const status = $("status");
  const statusLabel = $("status-label");
  const mode = $("mode");
  const meta = $("meta");
  const chatList = $("chat-list");

  let current = null;       // the assistant bubble being written
  let currentText = "";
  let state = "loading";
  let stateDetail = "";
  let modeKey = "general";
  let micOn = false;        // what the session says, not what was last clicked
  let micPending = false;   // a microphone request is on its way
  let sending = false;      // a message is on its way
  let frame = 0;            // a render scheduled for the next frame
  let chats = [];           // [{id, title, pinned, updated}]
  let activeId = null;      // the saved chat on screen
  let editing = null;       // the chat being renamed
  let confirming = null;    // the chat asking "delete?"
  let historyOn = true;

  // ------------------------------------------------------------- language
  function applyLanguage() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
    document.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
    document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === lang ? "true" : "false"));
    $("privacy").textContent = historyOn ? t("history.local") : t("history.off");
    mode.textContent = t(`mode.${modeKey}`);
    setState(state, stateDetail);
    renderChats();
  }

  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => {
    lang = b.dataset.lang;
    storedSet("halcyon.lang", lang);
    applyLanguage();
  }));

  // ------------------------------------------------- text: safe, lightly formatted
  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // Code fences, inline code, bold, simple lists and paragraphs. Everything is escaped first:
  // replies are text from a model, and a model can be made to write HTML.
  function render(text) {
    const parts = escapeHtml(text).split(/```/);
    return parts.map((part, i) => {
      if (i % 2 === 1) {
        const code = part.replace(/^[\w+-]*\n/, "");
        return `<div class="code"><pre><code>${code.replace(/\n$/, "")}</code></pre></div>`;
      }
      return part.split(/\n{2,}/).filter((p) => p.trim()).map((p) => {
        const inline = p
          .replace(/`([^`\n]+)`/g, "<code>$1</code>")
          .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
          .replace(/\n/g, "<br>");
        return `<p>${inline}</p>`;
      }).join("");
    }).join("");
  }

  // ------------------------------------------------------------------- copy
  const COPY_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3h11a2 2 0 0 1 2 2v11h-2V5H8V3Zm-3 4h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Zm0 2v10h10V9H5Z"/></svg>';

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      // Older web views refuse the clipboard API on a file:// page; the old way still works.
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      area.remove();
      return ok;
    }
  }

  function flashCopied(button, ok) {
    const label = button.querySelector("span");
    if (!label) return;
    label.textContent = ok ? t("copied") : t("copy.failed");
    clearTimeout(button._timer);
    button._timer = setTimeout(() => { label.textContent = t("copy"); }, 1400);
  }

  // A copy button on every code block of a bubble (drawn again whenever the bubble is).
  function decorate(bubble) {
    bubble.querySelectorAll(".code").forEach((block) => {
      if (block.querySelector(".copy-code")) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "copy-code";
      button.innerHTML = `${COPY_ICON}<span>${escapeHtml(t("copy"))}</span>`;
      button.addEventListener("click", async () => {
        flashCopied(button, await copyText(block.querySelector("code").textContent));
      });
      block.appendChild(button);
    });
  }

  // ---------------------------------------------------------------- drawing
  function scrollDown() { conversation.scrollTop = conversation.scrollHeight; }

  function showWelcome(show) { welcome.hidden = !show; }

  function addMessage(role, text, via) {
    showWelcome(false);
    const wrap = document.createElement("div");
    wrap.className = `message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = render(text);
    bubble._raw = text;
    decorate(bubble);
    wrap.appendChild(bubble);

    const tools = document.createElement("div");
    tools.className = "message-tools";
    if (via) {
      const small = document.createElement("span");
      small.className = "via";
      small.textContent = via;
      tools.appendChild(small);
      tools.classList.add("has-via");
    }
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "icon-sm copy";
    copy.title = t("copy");
    copy.setAttribute("aria-label", t("copy"));
    copy.innerHTML = COPY_ICON;
    copy.addEventListener("click", async () => {
      const ok = await copyText(bubble._raw || bubble.innerText);
      let note = tools.querySelector(".copied");
      if (!note) { note = document.createElement("span"); note.className = "copied"; tools.appendChild(note); }
      note.textContent = ok ? t("copied") : t("copy.failed");
      clearTimeout(copy._timer);
      copy._timer = setTimeout(() => note.remove(), 1400);
    });
    if (role === "user") tools.prepend(copy); else tools.appendChild(copy);
    wrap.appendChild(tools);

    conversation.appendChild(wrap);
    scrollDown();
    return bubble;
  }

  function setState(next, detail) {
    state = next;
    stateDetail = detail || "";
    status.dataset.state = next;
    statusLabel.textContent = detail && next === "loading" ? `${t("status.loading")}…` : t(`status.${next}`);
    status.title = detail || "";
    updateControls();
  }

  function updateControls() {
    const ready = state !== "loading" && state !== "error";
    const busy = ["thinking", "transcribing", "speaking"].includes(state) && !micOn;
    input.disabled = !ready || micOn || busy;
    send.disabled = input.disabled || sending || !input.value.trim();
    // Off while a typed reply is written: the voice loop would use the same model (review).
    mic.disabled = micPending || (!micOn && (!ready || busy));
    mic.setAttribute("aria-pressed", micOn ? "true" : "false");
    mic.title = micOn ? t("mic.off") : t("mic.on");
    input.placeholder = micOn ? t("input.voice") : t("input.placeholder");
  }

  function addNote(text) {
    const note = document.createElement("div");
    note.className = "note";
    note.textContent = text;
    conversation.appendChild(note);
    scrollDown();
  }

  function flush() {
    frame = 0;
    if (current) {
      current.innerHTML = render(currentText);
      current._raw = currentText;
      decorate(current);
    }
    scrollDown();
  }

  // A saved conversation, drawn from scratch.
  function showConversation(messages) {
    if (frame) { cancelAnimationFrame(frame); frame = 0; }
    current = null;
    currentText = "";
    conversation.querySelectorAll(".message, .note").forEach((el) => el.remove());
    messages.forEach((m) => {
      addMessage(m.role, m.text, m.via === "voice" ? t("via.voice") : "");
      if (m.status === "interrupted") addNote(t("interrupted"));
    });
    showWelcome(messages.length === 0);
    conversation.scrollTop = conversation.scrollHeight;
  }

  // ------------------------------------------------------------------ chats
  const ICONS = {
    pin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3l6 6-2 1-3 3 1 5-2 2-4-4-5 5-1-1 5-5-4-4 2-2 5 1 3-3 1-2Z"/></svg>',
    rename: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 17.2V20h2.8l8.3-8.3-2.8-2.8L4 17.2Zm13.7-7.6a1 1 0 0 0 0-1.4l-1.9-1.9a1 1 0 0 0-1.4 0l-1.4 1.4 2.8 2.8 1.9-1.9Z"/></svg>',
    delete: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm-3 6h12l-1 12H7L6 9Zm4 2v8h2v-8h-2Zm4 0v8h2v-8h-2Z"/></svg>',
  };

  function groupOf(chat) {
    if (chat.pinned) return "pinned";
    const day = new Date(); day.setHours(0, 0, 0, 0);
    const when = chat.updated * 1000;
    if (when >= day.getTime()) return "today";
    if (when >= day.getTime() - 86400000) return "yesterday";
    if (when >= day.getTime() - 6 * 86400000) return "week";
    return "older";
  }

  function iconButton(kind, title, onClick, extra) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `icon-sm ${extra || ""}`;
    button.title = title;
    button.setAttribute("aria-label", title);
    button.innerHTML = ICONS[kind];
    button.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
    return button;
  }

  function renderChats() {
    chatList.innerHTML = "";
    if (!chats.length) {
      const empty = document.createElement("p");
      empty.className = "empty-list";
      empty.textContent = historyOn ? t("chats.empty") : t("history.off");
      chatList.appendChild(empty);
      return;
    }
    let group = null;
    chats.forEach((chat) => {
      const g = groupOf(chat);
      if (g !== group) {
        group = g;
        const label = document.createElement("p");
        label.className = "group-label";
        label.textContent = t(`group.${g}`);
        chatList.appendChild(label);
      }
      chatList.appendChild(chatItem(chat));
    });
  }

  function chatItem(chat) {
    const item = document.createElement("div");
    item.className = "chat-item";
    item.tabIndex = 0;
    item.setAttribute("role", "button");
    item.dataset.id = chat.id;
    if (chat.id === activeId) item.setAttribute("aria-current", "true");

    if (editing === chat.id) {
      const field = document.createElement("input");
      field.className = "chat-rename";
      field.value = chat.title;
      field.maxLength = 120;
      let done = false;
      const finish = (save) => {
        if (done) return;
        done = true;
        editing = null;
        const title = field.value.trim();
        if (save && title && title !== chat.title) call("rename_chat", chat.id, title);
        renderChats();
      };
      field.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); finish(true); }
        if (e.key === "Escape") { e.preventDefault(); finish(false); }
        e.stopPropagation();
      });
      field.addEventListener("blur", () => finish(true));
      field.addEventListener("click", (e) => e.stopPropagation());
      item.appendChild(field);
      setTimeout(() => { field.focus(); field.select(); }, 0);
      return item;
    }

    const title = document.createElement("span");
    title.className = "chat-title";
    title.textContent = chat.title;
    title.title = chat.title;
    item.appendChild(title);

    if (confirming === chat.id) {
      item.classList.add("confirming");
      const box = document.createElement("span");
      box.className = "confirm";
      const ask = document.createElement("span");
      ask.textContent = t("confirm.delete");
      const yes = document.createElement("button");
      yes.type = "button"; yes.className = "yes"; yes.textContent = t("confirm.yes");
      const no = document.createElement("button");
      no.type = "button"; no.textContent = t("confirm.no");
      yes.addEventListener("click", async (e) => {
        e.stopPropagation();
        confirming = null;
        if (!(await call("delete_chat", chat.id))) addNote(t("busy.switch"));
        renderChats();
      });
      no.addEventListener("click", (e) => { e.stopPropagation(); confirming = null; renderChats(); });
      box.append(ask, yes, no);
      item.appendChild(box);
      return item;
    }

    if (chat.pinned) {
      const mark = document.createElement("span");
      mark.innerHTML = ICONS.pin;
      mark.firstChild.classList.add("pin-mark");
      item.appendChild(mark.firstChild);
    }
    const actions = document.createElement("span");
    actions.className = "chat-actions";
    actions.append(
      iconButton("pin", chat.pinned ? t("action.unpin") : t("action.pin"), () => call("pin_chat", chat.id, !chat.pinned)),
      iconButton("rename", t("action.rename"), () => { editing = chat.id; confirming = null; renderChats(); }),
      iconButton("delete", t("action.delete"), () => { confirming = chat.id; editing = null; renderChats(); }, "danger"),
    );
    item.appendChild(actions);

    const open = async () => {
      if (chat.id === activeId) { closeSideOnNarrow(); return; }
      if (await call("open_chat", chat.id)) closeSideOnNarrow();
      else addNote(t("busy.switch"));
    };
    item.addEventListener("click", open);
    item.addEventListener("keydown", (e) => {
      if (e.target !== item) return;
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      if (e.key === "F2") { e.preventDefault(); editing = chat.id; renderChats(); }
      if (e.key === "Delete") { e.preventDefault(); confirming = chat.id; renderChats(); }
    });
    return item;
  }

  $("new-chat").addEventListener("click", async () => {
    if (activeId === null && !conversation.querySelector(".message")) { closeSideOnNarrow(); input.focus(); return; }
    if (await call("new_chat")) { closeSideOnNarrow(); input.focus(); }
    else addNote(t("busy.switch"));
  });

  // ---------------------------------------------------------------- sidebar
  const narrow = () => window.matchMedia("(max-width: 760px)").matches;

  function closeSideOnNarrow() { if (narrow()) document.body.classList.remove("side-open"); }

  $("toggle-side").addEventListener("click", () => {
    if (narrow()) {
      document.body.classList.toggle("side-open");
    } else {
      const hidden = document.body.classList.toggle("side-hidden");
      storedSet("halcyon.side", hidden ? "hidden" : "shown");
    }
  });
  $("scrim").addEventListener("click", () => document.body.classList.remove("side-open"));
  if (storedGet("halcyon.side") === "hidden") document.body.classList.add("side-hidden");

  // ------------------------------------------------------------- events in
  function receive(event) {
    switch (event.type) {
      case "state":
        setState(event.state, event.detail);
        break;
      case "info":
        if (event.mode) { modeKey = event.mode; mode.textContent = t(`mode.${modeKey}`); }
        meta.textContent = [event.model, event.hardware].filter(Boolean).join(" · ");
        if ("history" in event) { historyOn = !!event.history; applyLanguage(); }
        break;
      case "chats":
        chats = event.chats || [];
        renderChats();
        break;
      case "chat":
        activeId = event.id;
        renderChats();
        break;
      case "conversation":
        activeId = event.id;
        showConversation(event.messages || []);
        renderChats();
        break;
      case "user":
        addMessage("user", event.text, event.via === "voice" ? t("via.voice") : "");
        break;
      case "assistant_start":
        currentText = "";
        current = addMessage("assistant", "");
        current.classList.add("typing");
        break;
      case "delta":
        if (!current) { currentText = ""; current = addMessage("assistant", ""); }
        currentText += event.text;
        current.classList.add("typing");
        // Drawn once a frame, not once a fragment: rebuilding a long answer on every fragment
        // made the work grow with the square of its length (found in review).
        if (!frame) frame = requestAnimationFrame(flush);
        break;
      case "mic":
        micOn = !!event.on;
        micPending = false;
        updateControls();
        break;
      case "assistant_done":
        if (frame) { cancelAnimationFrame(frame); flush(); }
        if (current) {
          current.classList.remove("typing");
          if (!currentText.trim()) current.parentElement.remove();
        }
        current = null;
        if (event.status === "interrupted") addNote(t("interrupted"));
        else if (event.status) {
          const match = /mode: (\w+)/.exec(event.status);
          if (match) { modeKey = match[1]; mode.textContent = t(`mode.${modeKey}`); }
        }
        break;
      case "error": {
        const bubble = addMessage("assistant", event.message);
        bubble.parentElement.classList.add("error");
        break;
      }
    }
  }

  // ------------------------------------------------------------ actions out
  const api = () => (window.pywebview && window.pywebview.api) || null;
  const live = () => !demoMode && !!api();

  // A call to the bridge; false when it refuses or fails. In the demo, the in-memory one.
  async function call(name, ...args) {
    const target = live() ? api() : demoApi;
    try {
      return await target[name](...args);
    } catch (e) {
      return false;
    }
  }

  async function submit() {
    const text = input.value.trim();
    if (!text || input.disabled || sending) return;
    if (!live()) {
      input.value = "";
      autosize();
      demoReply(text);
      return;
    }
    sending = true;
    updateControls();
    const accepted = await call("send", text);
    sending = false;
    // Cleared only once the session has taken it; a rejected message stays in the box (review).
    if (accepted) {
      if (input.value.trim() === text) input.value = "";
    } else {
      addNote(t("busy"));
    }
    autosize();
  }

  function autosize() {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
    input.style.overflowY = input.scrollHeight > 180 ? "auto" : "hidden";
    updateControls();
  }

  send.addEventListener("click", submit);
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });
  mic.addEventListener("click", async () => {
    const want = !micOn;
    if (!live()) {
      receive({ type: "mic", on: want });
      receive({ type: "state", state: want ? "listening" : "ready" });
      return;
    }
    micPending = true;
    updateControls();
    const ok = await call("mic", want);
    // The session's "mic" event is what turns the button on or off; a refused request only
    // releases it (found in review: the page stayed "on" after a refused or failed start).
    if (!ok) micPending = false;
    updateControls();
  });

  window.halcyon = { receive };

  // ------------------------------------------------------------------ demo
  // Sample chats in memory, answering like the bridge does, so every control can be tried.
  const demoStore = { next: 4, chats: [], messages: {} };
  const demoApi = {
    chats: () => demoStore.chats,
    new_chat: () => { receive({ type: "conversation", id: null, messages: [] }); return true; },
    open_chat: (id) => {
      if (!demoStore.messages[id]) return false;
      receive({ type: "conversation", id, messages: demoStore.messages[id] });
      return true;
    },
    rename_chat: (id, title) => demoEdit(id, (c) => { c.title = title; }),
    pin_chat: (id, pinned) => demoEdit(id, (c) => { c.pinned = pinned; }),
    delete_chat: (id) => {
      demoStore.chats = demoStore.chats.filter((c) => c.id !== id);
      delete demoStore.messages[id];
      if (id === activeId) receive({ type: "conversation", id: null, messages: [] });
      demoChats();
      return true;
    },
  };

  function demoEdit(id, change) {
    const chat = demoStore.chats.find((c) => c.id === id);
    if (!chat) return false;
    change(chat);
    demoChats();
    return true;
  }

  function demoChats() {
    const sorted = demoStore.chats.slice().sort((a, b) => (b.pinned - a.pinned) || (b.updated - a.updated));
    receive({ type: "chats", chats: sorted });
  }

  function demoReply(text) {
    let id = activeId;
    if (id === null) {
      id = demoStore.next++;
      demoStore.chats.push({ id, title: text.slice(0, 48), pinned: false, updated: Date.now() / 1000 });
      demoStore.messages[id] = [];
      receive({ type: "chat", id });
    }
    const answer = lang === "tr"
      ? "Bu bir **önizleme**: model bağlı değil. Gerçek pencereyi `python -m ui` ile aç."
      : "This is a **preview**: no model is connected. Open the real window with `python -m ui`.";
    demoStore.messages[id].push({ role: "user", text, via: "text", status: "" },
                                { role: "assistant", text: answer, via: "text", status: "" });
    const chat = demoStore.chats.find((c) => c.id === id);
    if (chat) chat.updated = Date.now() / 1000;
    const steps = [
      { type: "user", text, via: "text" },
      { type: "state", state: "thinking" },
      { type: "assistant_start" },
    ];
    answer.split(/(?<= )/).forEach((w) => steps.push({ type: "delta", text: w }));
    steps.push({ type: "assistant_done", status: "mode: general | request: chat tier 0" }, { type: "state", state: "ready" });
    steps.forEach((e, i) => setTimeout(() => receive(e), 60 * i));
    setTimeout(demoChats, 60 * steps.length);
  }

  function demo() {
    const tr = lang === "tr";
    const now = Date.now() / 1000;
    const log = [
      { role: "user", text: tr ? "logs klasöründeki server.log dosyasında en son hata ne?" : "What was the last error in logs/server.log?", via: "text", status: "" },
      { role: "assistant", text: tr ? "Son hata 2951. satırda: **disk kotası aşılmış**, `/var/data` klasörüne yazılamamış." : "The last error is on line 2951: the **disk quota was exceeded**, so nothing could be written to `/var/data`.", via: "text", status: "" },
    ];
    const code = [
      { role: "user", text: tr ? "calc.py'deki average fonksiyonunda hata ne?" : "What is wrong with average() in calc.py?", via: "voice", status: "" },
      { role: "assistant", text: tr ? "Döngü 1'den başlıyor, bu yüzden ilk eleman toplanmıyor:\n\n```python\nfor i in range(1, len(values)):\n    total += values[i]\n```\n\n`range(len(values))` olmalı." : "The loop starts at 1, so the first value is never added:\n\n```python\nfor i in range(1, len(values)):\n    total += values[i]\n```\n\nIt should be `range(len(values))`.", via: "voice", status: "" },
    ];
    const dict = [
      { role: "user", text: tr ? "Python'da dict nedir?" : "What is a dict in Python?", via: "text", status: "" },
      { role: "assistant", text: tr ? "Anahtar-değer çiftlerini tutan bir yapı: `{\"a\": 1}`." : "A structure of key-value pairs: `{\"a\": 1}`.", via: "text", status: "" },
    ];
    demoStore.chats = [
      { id: 1, title: tr ? "Sunucu günlüğündeki son hata" : "The last error in the server log", pinned: true, updated: now - 3 * 86400 },
      { id: 2, title: tr ? "average fonksiyonundaki hata" : "The bug in average()", pinned: false, updated: now - 600 },
      { id: 3, title: tr ? "Python'da dict" : "Dicts in Python", pinned: false, updated: now - 30 * 3600 },
    ];
    demoStore.messages = { 1: log, 2: code, 3: dict };
    receive({ type: "info", model: "qwen3.5:9b", hardware: "NVIDIA GeForce RTX 4060 Laptop GPU", mode: "general" });
    receive({ type: "state", state: "ready" });
    demoChats();
    receive({ type: "conversation", id: 2, messages: code });
  }

  // ------------------------------------------------------------------ start
  applyLanguage();
  setState("loading");
  let started = false;
  // The window's settings come from the bridge, not the address: WebView2 could not open
  // index.html?demo=1 at all ("File not found"). A browser preview still uses ?demo and ?lang.
  async function begin() {
    if (started) return;
    started = true;
    if (!api()) { demo(); return; }
    let settings = {};
    try { settings = (await api().settings()) || {}; } catch (e) { settings = {}; }
    if (!storedGet("halcyon.lang") && (settings.language === "tr" || settings.language === "en")) {
      lang = settings.language;
      applyLanguage();
    }
    if (settings.demo) demoMode = true;
    if (live()) api().ready(); else demo();
  }
  window.addEventListener("pywebviewready", begin);
  setTimeout(() => { if (!window.pywebview) begin(); }, 300);
})();
