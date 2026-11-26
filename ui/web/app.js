// The Halcyon page. Draws the events of ui/session.py and calls the Python bridge in ui/app.py.
// Opened in a plain browser (no pywebview), or with ?demo=1, it plays sample events instead,
// so the design can be worked on without a model.
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
    },
  };
  const lang = (navigator.language || "en").toLowerCase().startsWith("tr") ? "tr" : "en";
  const t = (key) => (TEXT[lang] && TEXT[lang][key]) || TEXT.en[key] || key;

  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });

  // ---------------------------------------------------------------- elements
  const $ = (id) => document.getElementById(id);
  const conversation = $("conversation");
  const input = $("input");
  const send = $("send");
  const mic = $("mic");
  const status = $("status");
  const statusLabel = $("status-label");
  const mode = $("mode");
  const meta = $("meta");

  let current = null;       // the assistant bubble being written
  let currentText = "";
  let state = "loading";
  let micOn = false;

  // ------------------------------------------------- text: safe, lightly formatted
  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // Code fences, inline code, bold and paragraphs. Everything is escaped first: replies are
  // text from a model, and a model can be made to write HTML.
  function render(text) {
    const parts = escapeHtml(text).split(/```/);
    return parts.map((part, i) => {
      if (i % 2 === 1) {
        const code = part.replace(/^[\w+-]*\n/, "");
        return `<pre><code>${code.replace(/\n$/, "")}</code></pre>`;
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

  // ---------------------------------------------------------------- drawing
  function scrollDown() { conversation.scrollTop = conversation.scrollHeight; }

  function hideWelcome() {
    const welcome = $("welcome");
    if (welcome) welcome.remove();
  }

  function addMessage(role, text, via) {
    hideWelcome();
    const wrap = document.createElement("div");
    wrap.className = `message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = render(text);
    wrap.appendChild(bubble);
    if (via) {
      const small = document.createElement("span");
      small.className = "via";
      small.textContent = via;
      wrap.appendChild(small);
    }
    conversation.appendChild(wrap);
    scrollDown();
    return bubble;
  }

  function setState(next, detail) {
    state = next;
    status.dataset.state = next;
    statusLabel.textContent = detail && next === "loading" ? `${t("status.loading")}…` : t(`status.${next}`);
    status.title = detail || "";
    updateControls();
  }

  function updateControls() {
    const ready = state !== "loading" && state !== "error";
    const busy = ["thinking", "transcribing", "speaking"].includes(state) && !micOn;
    input.disabled = !ready || micOn || busy;
    send.disabled = input.disabled || !input.value.trim();
    mic.disabled = !ready && !micOn;
    mic.setAttribute("aria-pressed", micOn ? "true" : "false");
    mic.title = micOn ? t("mic.off") : t("mic.on");
    input.placeholder = micOn ? t("input.voice") : t("input.placeholder");
  }

  // ------------------------------------------------------------- events in
  function receive(event) {
    switch (event.type) {
      case "state":
        setState(event.state, event.detail);
        break;
      case "info":
        if (event.mode) mode.textContent = t(`mode.${event.mode}`);
        meta.textContent = [event.model, event.hardware].filter(Boolean).join(" · ");
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
        current.innerHTML = render(currentText);
        current.classList.add("typing");
        scrollDown();
        break;
      case "assistant_done":
        if (current) {
          current.classList.remove("typing");
          if (!currentText.trim()) current.parentElement.remove();
        }
        current = null;
        if (event.status === "interrupted") addNote(t("interrupted"));
        else if (event.status) {
          const match = /mode: (\w+)/.exec(event.status);
          if (match) mode.textContent = t(`mode.${match[1]}`);
        }
        break;
      case "error": {
        const bubble = addMessage("assistant", event.message);
        bubble.parentElement.classList.add("error");
        break;
      }
    }
  }

  function addNote(text) {
    const note = document.createElement("div");
    note.className = "note";
    note.textContent = text;
    conversation.appendChild(note);
    scrollDown();
  }

  // ------------------------------------------------------------ actions out
  const api = () => (window.pywebview && window.pywebview.api) || null;

  function submit() {
    const text = input.value.trim();
    if (!text || input.disabled) return;
    input.value = "";
    autosize();
    if (api()) api().send(text);
    else demoReply(text);
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
  mic.addEventListener("click", () => {
    micOn = !micOn;
    updateControls();
    if (api()) api().mic(micOn);
    else receive({ type: "state", state: micOn ? "listening" : "ready" });
  });

  window.halcyon = { receive };

  // ------------------------------------------------------------------ demo
  function demoReply(text) {
    const steps = [
      { type: "user", text, via: "text" },
      { type: "state", state: "thinking" },
      { type: "assistant_start" },
    ];
    const answer = lang === "tr"
      ? "Bu bir **önizleme**: model bağlı değil. Gerçek pencereyi `python -m ui` ile aç."
      : "This is a **preview**: no model is connected. Open the real window with `python -m ui`.";
    answer.split(/(?<= )/).forEach((w) => steps.push({ type: "delta", text: w }));
    steps.push({ type: "assistant_done", status: "mode: general | request: chat tier 0" }, { type: "state", state: "ready" });
    steps.forEach((e, i) => setTimeout(() => receive(e), 60 * i));
  }

  function demo() {
    const tr = lang === "tr";
    const events = [
      { type: "info", model: "qwen3.5:9b", hardware: "NVIDIA GeForce RTX 4060 Laptop GPU", mode: "general" },
      { type: "state", state: "ready" },
      { type: "user", text: tr ? "logs klasöründeki server.log dosyasında en son hata ne?" : "What was the last error in logs/server.log?", via: "text" },
      { type: "assistant_start" },
      { type: "delta", text: tr ? "Son hata 2951. satırda: **disk kotası aşılmış**, `/var/data` klasörüne yazılamamış." : "The last error is on line 2951: the **disk quota was exceeded**, so nothing could be written to `/var/data`." },
      { type: "assistant_done", status: "mode: general | request: daily tier 0" },
      { type: "user", text: tr ? "calc.py'deki average fonksiyonunda hata ne?" : "What is wrong with average() in calc.py?", via: "voice" },
      { type: "assistant_start" },
      { type: "delta", text: tr ? "Döngü 1'den başlıyor, bu yüzden ilk eleman toplanmıyor:\n\n```python\nfor i in range(1, len(values)):\n    total += values[i]\n```\n\n`range(len(values))` olmalı." : "The loop starts at 1, so the first value is never added:\n\n```python\nfor i in range(1, len(values)):\n    total += values[i]\n```\n\nIt should be `range(len(values))`." },
      { type: "assistant_done", status: "mode: general | request: code tier 1" },
    ];
    events.forEach((e, i) => setTimeout(() => receive(e), 120 * i));
  }

  // ------------------------------------------------------------------ start
  setState("loading");
  const isDemo = new URLSearchParams(location.search).has("demo");
  window.addEventListener("pywebviewready", () => { if (!isDemo) api().ready(); else demo(); });
  setTimeout(() => { if (!window.pywebview) demo(); }, 300);
})();
