"""
Language model access for the voice path.

Uses the ``ollama`` client directly rather than LangChain: one less layer on a
hot path, explicit control of ``think``, and a tool loop we can interrupt.
LangChain remains the right tool for ``agent.py``.

Three behaviours here exist because of measurements on this machine, not
because they are generically good ideas:

**Conversation memory.** Each turn used to send only the system prompt plus the
current sentence. "Show me" after "shall I show you?" therefore arrived with no
antecedent, and the model invented one. History is now carried and bounded.

**Idle wake-up (``prewarm``).** Time-to-first-token, warm model, fresh prompt:

    request sent immediately after the previous one     ~140 ms
    request sent 10 s after the previous one           ~2126 ms
    request sent 20 s after the previous one           ~2130 ms

A fixed ~2 s, independent of how long the gap was: the laptop GPU drops into a
low-power state when idle and has to spin back up. Every real conversational
turn has a gap like that in it, which is why the live assistant felt two
seconds slower than every benchmark. ``prewarm()`` is fired the moment the VAD
hears speech start, so the wake-up overlaps with the user still talking and has
finished by the time there is anything to answer.

**Abandoned streams.** Ollama serialises per loaded model, and a generation
whose client stops reading keeps running to ``num_predict``; the next request
queues behind it (~1000-1600 ms becomes ~2200-2350 ms). ``.close()`` does not
prevent this on either client. So ``num_predict`` is kept small in the profiles,
and callers that stop early drain the remainder. Barge-in is the one place that
genuinely cannot drain; there the cost lands on the next turn.

**The tool loop.** Measured with bench/task_eval.py (docs/TOOLS.md): a model that had read
two folders and one file was cut off by the round limit and said only "I could not finish
that"; another said "Let me check the other files." and stopped without calling anything; and
several reads in one turn can outgrow an 8k context, where Ollama silently drops the oldest
tokens, the system prompt first. So the last round offers no tools and asks for an answer
from what was found, a reply that only announces an action is sent back once to act, and the
messages are fitted to the context before every round (older tool results of the turn are
shortened first, then earlier turns dropped). Typing gets more rounds than speaking, where a
long silence is worse than a shorter answer.

Note on measuring any of this: repeating an identical prompt hits Ollama's KV
cache and reports ~120 ms, which no real turn will ever see. Measure with a
fresh prompt.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from core.profiles import Profile

HALCYON_PERSONA = (
    "You are Halcyon: a calm, loyal assistant running entirely on the user's own "
    "computer. Your manner is measured, confident and economical, never gushing.\n"
    "Address the user respectfully only now and then, never in every reply: "
    "'sir' in English, 'efendim' in Turkish.\n"
    "Talk like a calm person, not a system: everyday words, contractions ('I'm', "
    "'it's'), no stiff phrases such as 'I am functioning well'. After you answer, "
    "stop: never add 'Would you like me to ...?' or any other offer. Ask a question "
    "only when you cannot answer without the reply.\n"
    "You are speaking aloud, so keep answers short - two sentences at most. Never "
    "use bullet points, headings, code blocks, emoji or asterisks: they are "
    "meaningless when read aloud. Write numbers and abbreviations the way they "
    "should be spoken.\n"
    "Always reply in the language the user spoke.\n"
    "Never say you are doing, will do, or have done something unless you call the "
    "tool for it in this reply and its result confirms it; do not offer to 'try'.\n"
    "When you use a tool, answer only from what it returned. If the result does not "
    "contain the answer, say so instead of filling the gap from memory.\n"
    "Your own knowledge stops at a date in the past: for the latest version or release of "
    "something, news, prices or anything else that changes, search the web before answering.\n"
    "No backticks, code or commands in your replies: they cannot be spoken. "
    "Name files in words, without the extension and without quotes: 'the hello file', "
    "'the meeting notes'. That is only for what you say: in tool calls always use the exact "
    "file name, with its extension."
)

# Spoken when the tool loop gives up. Spoken words stay in the language the
# user spoke, so these are kept per language.
# Names used when telling the model which language this turn is in.
LANGUAGE_NAMES = {"en": "English", "tr": "Turkish"}

GIVE_UP = {
    "en": "I could not finish that, sir.",
    "tr": "Bunu tamamlayamadım efendim.",
}

# Kept for callers that want the plain assistant with no persona or tools.
SPEECH_SYSTEM_PROMPT = HALCYON_PERSONA

# How many rounds of tool calls one turn may use before it must answer. Speaking keeps it short:
# a long silence reads as a crash. Typing can afford a deeper search.
SPOKEN_TOOL_ROUNDS = 4
TYPED_TOOL_ROUNDS = 8

# A tool result longer than this is cut; the file tools return windows that fit (core/files.py).
TOOL_RESULT_CHARS = 4000
# Characters per token when budgeting the context: Turkish and numbered code lines tokenise
# worse than English prose, so this errs on the side of shortening too early.
CHARS_PER_TOKEN = 3.0
KEEP_TOOL_RESULTS = 2          # the newest results of a turn are never shortened first
SHORTENED_TOOL_CHARS = 600

# One-round instructions, appended to the system prompt for that round only.
FINAL_ROUND_NOTE = ("You have used all the tool calls for this request. Answer now from what the tools "
                    "returned; if something is still missing, say what you could not find.")
ACT_NOW_NOTE = ("You said you would do something, or asked whether to, but did not call a tool. Reading, "
                "listing and searching never need permission. Call the tool now instead of saying it again.")

_TOOL_VERB = r"(?:check|look|see|read|open|search|find|list|try|take a look|have a look|go through|verify)"
_ANNOUNCES = re.compile(
    # Saying it will act, in English ...
    rf"\b(?:let me {_TOOL_VERB}|i(?:'ll| will) {_TOOL_VERB}|i(?:'m| am) going to {_TOOL_VERB}"
    r"|checking (?:now|that|it)|one moment|just a (?:moment|second|sec))\b"
    # ... or asking leave to do what never needs it: reading, listing and searching change nothing.
    rf"|\b(?:would you like me to|do you want me to|shall i|should i|may i|can i) {_TOOL_VERB}\b"
    # ... and in Turkish: now, about to, or future ("bulacağım", measured on the 9B model).
    r"|bakayım|bakıyorum|bakacağım|okuyayım|okuyorum|okuyacağım|açayım|açıyorum|açacağım"
    r"|kontrol edeyim|kontrol ediyorum|kontrol edeceğim|arayayım|arıyorum|arayacağım|bulacağım"
    r"|inceleyeyim|inceliyorum|inceleyeceğim|listeleyeyim|listeliyorum|listeleyeceğim|göz atayım"
    r"|göz atacağım|bir saniye|bir dakika|bekleyin"
    r"|(?:okumamı|bakmamı|listelememi|aramamı|açmamı|incelememi|kontrol etmemi) ister misiniz"
    r"|izin verin|izin verirseniz|izniniz olursa",
    re.IGNORECASE)


def announces_action(text: str) -> bool:
    """
    The reply ends by saying it will do something ("Let me check the file.", "Dosyayı açıyorum.")
    instead of answering. Only short replies, and only their last two sentences, count: an
    answer that happens to say "let me" in the middle is an answer.
    """
    text = text.strip()
    if not text or len(text) > 400:
        return False
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    return any(_ANNOUNCES.search(sentence) for sentence in sentences[-2:])


# How many past turns to carry. Each turn is a user message plus an assistant
# message, so this is 8 exchanges - enough for "show me that one" to resolve,
# short enough that the context stays small and the KV cache stays warm.
DEFAULT_HISTORY_TURNS = 8


class SpeechLLM:
    """A streaming chat client sized and configured by a runtime profile."""

    def __init__(
        self,
        profile: Profile,
        *,
        temperature: float = 0.4,
        base_url: str | None = None,
        system: str = HALCYON_PERSONA,
        tools: list[Any] | None = None,
        history_turns: int = DEFAULT_HISTORY_TURNS,
    ) -> None:
        import ollama

        if base_url is None:
            import config

            base_url = config.OLLAMA_BASE_URL

        self.profile = profile
        self.model = profile.llm_model
        self.base_url = base_url
        self.system = system
        self.history_turns = history_turns
        self._client = ollama.Client(host=base_url)
        self._options = {
            "num_predict": profile.llm_num_predict,
            "num_ctx": profile.llm_num_ctx,
            "temperature": temperature,
        }

        self._history: list[dict[str, Any]] = []
        self._tools = {t.name: t for t in (tools or [])}
        self._tool_specs = [_to_ollama_tool(t) for t in (tools or [])]

        # What a mode (core/router.py) can change on top of a profile. `base_system` is
        # the prompt this client was built with, so leaving a mode can restore it.
        self.base_system = system
        self._tools_enabled = True
        self._supports_thinking = True
        self._switching = threading.Event()

        self.max_tool_rounds = SPOKEN_TOOL_ROUNDS
        self.last_rounds = 0           # generations the last turn took (for diagnostics and benchmarks)

        self._prewarm_lock = threading.Lock()
        self._prewarming = False
        self._prewarm_thread: threading.Thread | None = None
        self.last_tool_calls: list[str] = []

    # ------------------------------------------------------------- lifecycle

    def reset(self) -> None:
        """Forget the conversation, keep the loaded model."""
        self._history.clear()

    def reconfigure(self, profile: Profile) -> None:
        """Switch to another model or context length; the conversation is kept."""
        self.profile = profile
        self.model = profile.llm_model
        self._options["num_ctx"] = profile.llm_num_ctx
        self._options["num_predict"] = profile.llm_num_predict

    def tool_objects(self) -> list[Any]:
        """The tools this client was built with (a mode describes them in its own prompt)."""
        return list(self._tools.values())

    def apply_mode(self, profile: Profile, *, system: str | None = None, use_tools: bool = True,
                   supports_thinking: bool = True) -> None:
        """
        Run as `profile` with a mode's prompt, keeping the conversation.

        `use_tools` and `supports_thinking` come from asking Ollama what the model can do
        (model_capabilities): sending `tools` to a model without them, or `think` to a
        model that cannot, is an error rather than being ignored.
        """
        self.reconfigure(profile)
        self.system = self.base_system if system is None else system
        self._tools_enabled = use_tools
        self._supports_thinking = supports_thinking

    # How long a swap waits for a wake-up that was already running. A wake-up is one token,
    # so this is only reached when the GPU itself is stuck; the swap then goes ahead.
    PREWARM_WAIT_S = 30.0

    def begin_switch(self) -> None:
        """
        A model swap is in progress: background wake-ups must not load the old model again.

        New wake-ups are refused from here on, and one that is already running is waited
        for: it was sent for the old model, and if it reached Ollama after the unload it
        would load the old model again next to the new one (two models do not fit in 8 GB).
        """
        self._switching.set()
        running = self._prewarm_thread
        if running is not None and running.is_alive() and running is not threading.current_thread():
            running.join(timeout=self.PREWARM_WAIT_S)

    def end_switch(self) -> None:
        self._switching.clear()

    def placement(self) -> tuple[float, float] | None:
        """
        (GB the model needs, GB of it actually on the GPU), from Ollama.

        None if the model is not loaded or Ollama cannot be asked.
        """
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/ps", timeout=5) as response:
                loaded = json.load(response).get("models", [])
        except Exception:  # noqa: BLE001 - a failed check must not stop the assistant
            return None
        for entry in loaded:
            if entry.get("name") == self.model:
                return entry.get("size", 0) / 1024**3, entry.get("size_vram", 0) / 1024**3
        return None

    def unload(self) -> None:
        """Ask Ollama to drop this model from memory now."""
        try:
            self._client.generate(model=self.model, prompt="", keep_alive=0)
        except Exception:  # noqa: BLE001
            pass

    def warmup(self) -> None:
        """
        Load the weights before the first real turn.

        Consumed to completion deliberately: an abandoned warmup would leave
        the server generating, and the user's first question would queue
        behind it.
        """
        for _ in self._raw_stream([{"role": "user", "content": "merhaba"}],
                                  system="Answer in one word.", use_tools=False):
            pass

    def prewarm(self) -> None:
        """
        Wake the GPU in the background. Returns immediately.

        Called when the VAD hears speech start, so the ~2 s idle wake-up runs
        while the user is still talking instead of after they finish. Cheap
        enough to fire on every utterance: one token, no history, no tools.
        """
        if self._switching.is_set():
            return  # a model swap is under way; waking the old model would load it again
        with self._prewarm_lock:
            if self._prewarming:
                return
            self._prewarming = True

        def run() -> None:
            try:
                for _ in self._raw_stream(
                    [{"role": "user", "content": "."}],
                    system="Reply with one character.", use_tools=False, num_predict=1,
                ):
                    pass
            except Exception:  # noqa: BLE001 - a failed prewarm must never break a turn
                pass
            finally:
                with self._prewarm_lock:
                    self._prewarming = False

        thread = threading.Thread(target=run, name="halcyon-prewarm", daemon=True)
        self._prewarm_thread = thread
        thread.start()

    # ---------------------------------------------------------------- stream

    def _raw_stream(self, messages: list[dict[str, Any]], *, system: str | None = None,
                    use_tools: bool = True, num_predict: int | None = None):
        options = dict(self._options)
        if num_predict is not None:
            options["num_predict"] = num_predict
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system or self.system}, *messages],
            "stream": True,
            "options": options,
        }
        # A model that cannot think rejects the parameter instead of ignoring it, even when
        # the profile asks for reasoning: that model then simply answers without it.
        if self._supports_thinking:
            payload["think"] = self.profile.llm_reasoning
        if use_tools and self._tool_specs and self._tools_enabled:
            payload["tools"] = self._tool_specs
        return self._client.chat(**payload)

    def stream(self, prompt: str, system: str | None = None,
               language: str | None = None) -> Iterator[str]:
        """
        Yield response text deltas for one user turn.

        Runs the tool loop transparently: if the model asks for a tool, it is
        executed and the conversation continues, so the caller sees only text.
        """
        self._history.append({"role": "user", "content": prompt})
        self.last_tool_calls = []
        spoken: list[str] = []

        # Earlier turns pull the model towards their language: after a few English
        # turns a Turkish question was answered in English. Say which language
        # this turn is in; the history stays untouched.
        turn_system = system or self.system
        language_name = LANGUAGE_NAMES.get(language or "")
        if language_name:
            turn_system += f"\nThe user is speaking {language_name} right now: reply in {language_name}."

        rounds = max(1, int(self.max_tool_rounds))
        note = ""          # an instruction for one round only: act now, or answer now
        nudged = False
        self.last_rounds = 0
        try:
            # Bounded so one confused turn cannot spin forever while the user sits in silence
            # waiting for a reply. The last round offers no tools, so a turn that used them all
            # still ends in an answer instead of "I could not finish that".
            for round_index in range(rounds + 1):
                final = round_index == rounds
                if final:
                    note = FINAL_ROUND_NOTE
                tool_calls: list[dict[str, Any]] = []
                assistant_text: list[str] = []

                # Each round is a separate generation, so the model does not
                # know the previous one ended mid-flow: it produced
                # "...checking." and now starts "Sir, ...". Joined raw that is
                # "checking.Sir," - and the sentence splitter requires
                # whitespace after the full stop, so the whole answer becomes
                # one chunk and nothing is spoken until the very end.
                if round_index and spoken and not spoken[-1].endswith((" ", "\n")):
                    spoken.append(" ")
                    yield " "

                round_system = turn_system + ("\n" + note if note else "")
                note = ""
                messages = self._fit_context(self._history, round_system, use_tools=not final)
                self.last_rounds += 1
                response = self._raw_stream(messages, system=round_system, use_tools=not final)
                try:
                    for chunk in response:
                        message = chunk.get("message", {}) or {}
                        text = message.get("content", "")
                        if text:
                            assistant_text.append(text)
                            spoken.append(text)
                            yield text
                        if not final:
                            for call in message.get("tool_calls") or []:
                                tool_calls.append(call)
                finally:
                    close = getattr(response, "close", None)
                    if close is not None:
                        close()

                if not tool_calls:
                    reply = "".join(assistant_text)
                    self._history.append({"role": "assistant", "content": reply})
                    if (not final and not nudged and self._tools_enabled and self._tool_specs
                            and (announces_action(reply) or not reply.strip())):
                        # "Let me check the other files." and then nothing, or nothing at all:
                        # once per turn, send it back to do it.
                        nudged = True
                        note = ACT_NOW_NOTE
                        continue
                    if not reply.strip() and not "".join(spoken).strip():
                        # An empty answer is never shown as an answer (measured once on the
                        # 26B model, after nine rounds of searching).
                        yield GIVE_UP.get(language or "", GIVE_UP["en"])
                    return

                self._history.append({
                    "role": "assistant",
                    "content": "".join(assistant_text),
                    "tool_calls": tool_calls,
                })
                for call in tool_calls:
                    name, result = self._run_tool(call)
                    self.last_tool_calls.append(name)
                    self._history.append({"role": "tool", "name": name, "content": result})

            # Fell out of the loop still wanting tools: say so rather than
            # ending the turn in silence, which reads as a crash.
            if not spoken:
                yield GIVE_UP.get(language or "", GIVE_UP["en"])
        finally:
            self._trim_history()

    def _run_tool(self, call: dict[str, Any]) -> tuple[str, str]:
        function = call.get("function", {}) or {}
        name = function.get("name", "")
        arguments = function.get("arguments", {}) or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return name, f"Could not parse the tool arguments: {arguments!r}"

        tool = self._tools.get(name)
        if tool is None:
            return name, f"There is no tool called '{name}'."

        try:
            result = tool.invoke(arguments)
        except Exception as exc:  # noqa: BLE001 - tool errors are data for the model
            return name, f"Tool error: {exc}"

        text = result if isinstance(result, str) else str(result)
        # A directory listing can be thousands of lines. The model only needs
        # enough to answer, and the rest is context budget that pushes the KV
        # cache out of VRAM. The file tools return windows that fit; this is the
        # backstop, and it says how to get the rest instead of just stopping.
        if len(text) > TOOL_RESULT_CHARS:
            text = (text[:TOOL_RESULT_CHARS] + f"\n... (cut at {TOOL_RESULT_CHARS} of {len(text)} characters: "
                    "ask for a smaller part)")
        return name, text

    def _context_budget_chars(self, system: str, use_tools: bool) -> int:
        """Room for the messages, in characters: the context minus the reply, the prompt and the tools."""
        tokens = int(self.profile.llm_num_ctx) - int(self._options.get("num_predict") or 0)
        chars = int(tokens * CHARS_PER_TOKEN) - len(system)
        if use_tools and self._tools_enabled and self._tool_specs:
            chars -= len(json.dumps(self._tool_specs))
        return max(chars, 2000)

    def _fit_context(self, messages: list[dict[str, Any]], system: str, use_tools: bool) -> list[dict[str, Any]]:
        """
        The messages to send, shortened when they would not fit the context window.

        Ollama does not refuse an overlong prompt: it silently drops the oldest tokens, the system
        prompt first, and the model then answers without its instructions. So, in this order, until
        it fits: the turn's older tool results are shortened, whole earlier turns are dropped, every
        tool result but the newest is shortened, and finally the newest is cut. The question being
        answered is always kept. The stored history is not changed.
        """
        budget = self._context_budget_chars(system, use_tools)

        def size(items: list[dict[str, Any]]) -> int:
            # str(), not json.dumps(): the real client returns ToolCall objects, which json cannot
            # serialise (every tool round crashed on it; the dicts in the unit tests hid it).
            return sum(len(str(m.get("content") or "")) + len(str(m.get("tool_calls") or "")) + 16
                       for m in items)

        if size(messages) <= budget:
            return messages
        fitted = [dict(m) for m in messages]
        marker = "\n... (shortened to keep the conversation within the model's context; read it again if needed)"

        def shorten(index: int, keep: int) -> None:
            content = str(fitted[index].get("content") or "")
            if len(content) > keep + len(marker):
                fitted[index]["content"] = content[:keep] + marker

        tools = [i for i, m in enumerate(fitted) if m.get("role") == "tool"]
        for i in tools[:-KEEP_TOOL_RESULTS]:
            if size(fitted) <= budget:
                return fitted
            shorten(i, SHORTENED_TOOL_CHARS)

        # Whole earlier turns, oldest first; never the turn being answered.
        while size(fitted) > budget:
            current = max((i for i, m in enumerate(fitted) if m.get("role") == "user"), default=0)
            if current == 0:
                break
            next_user = next(i for i in range(1, current + 1) if fitted[i].get("role") == "user")
            del fitted[:next_user]

        tools = [i for i, m in enumerate(fitted) if m.get("role") == "tool"]
        for i in tools[:-1]:
            if size(fitted) <= budget:
                return fitted
            shorten(i, SHORTENED_TOOL_CHARS)
        if tools and size(fitted) > budget:
            over = size(fitted) - budget
            content = str(fitted[tools[-1]].get("content") or "")
            shorten(tools[-1], max(SHORTENED_TOOL_CHARS, len(content) - over - len(marker)))
        return fitted

    def _trim_history(self) -> None:
        # Trim on message count rather than turn count: tool calls add extra
        # messages, so a turn is not a fixed number of entries.
        limit = self.history_turns * 2
        if len(self._history) <= limit:
            return
        # Never start the retained window on a tool result, which would be an
        # answer with no question in front of it.
        cut = len(self._history) - limit
        while cut < len(self._history) and self._history[cut].get("role") != "user":
            cut += 1
        self._history = self._history[cut:]


def _to_ollama_tool(tool: Any) -> dict[str, Any]:  # noqa: ANN401
    """Convert a LangChain tool to the OpenAI/Ollama function-calling schema."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    spec = convert_to_openai_tool(tool)
    function = spec.get("function", {})
    # The docstrings in tools.py carry Args/Returns/Example blocks meant for a
    # reader. The model only needs the first paragraph, and the rest is tokens
    # spent on every single request.
    description = (function.get("description") or "").split("\n\n")[0].strip()
    if description:
        function["description"] = description
    return spec


def build_llm(profile: Profile, *, temperature: float = 0.4, base_url: str | None = None,
              tools: list[Any] | None = None, system: str | None = None) -> SpeechLLM:
    """
    A SpeechLLM with the Halcyon persona plus a statement of what it can do.

    The statements are generated, so they always match the tools actually
    enabled and the computer it runs on. Pass `system` to replace the whole prompt.
    """
    if system is None:
        from core.voice_tools import capability_statement, environment_statement

        system = HALCYON_PERSONA + "\n" + capability_statement(tools or [])
        if tools:
            system += "\n" + environment_statement()
    return SpeechLLM(profile, temperature=temperature, base_url=base_url,
                     tools=tools, system=system)


def stream_reply(llm: SpeechLLM, prompt: str, system: str | None = None,
                 language: str | None = None) -> Iterator[str]:
    return llm.stream(prompt, system, language)


def installed_models(base_url: str | None = None) -> set[str] | None:
    """Names of the models pulled into Ollama, or None if Ollama is unreachable."""
    if base_url is None:
        import config

        base_url = config.OLLAMA_BASE_URL
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as response:
            return {model.get("name", "") for model in json.load(response).get("models", [])}
    except Exception:  # noqa: BLE001
        return None


def check_model_available(profile: Profile, *, base_url: str | None = None) -> tuple[bool, str]:
    """
    Verify the profile's model is actually pulled.

    A missing model otherwise surfaces as a confusing mid-conversation error,
    several seconds into what looked like a working startup.
    """
    import urllib.error
    import urllib.request

    if base_url is None:
        import config

        base_url = config.OLLAMA_BASE_URL

    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as response:
            tags = json.load(response)
    except urllib.error.URLError as exc:
        return False, f"Could not connect to Ollama ({base_url}): {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not connect to Ollama ({base_url}): {exc}"

    names = {model.get("name", "") for model in tags.get("models", [])}
    if profile.llm_model in names:
        return True, ""
    return False, (
        f"'{profile.llm_model}' is not installed. Pull it first:\n"
        f"    ollama pull {profile.llm_model}\n"
        f"  Installed models: {', '.join(sorted(names)) or '(none)'}"
    )


def model_capabilities(model: str, base_url: str | None = None) -> set[str] | None:
    """
    What Ollama says the model can do ("completion", "tools", "thinking", "vision" ...).

    None when it cannot be asked (Ollama down, an older Ollama that does not report
    capabilities): callers then keep their defaults instead of guessing.
    """
    if base_url is None:
        import config

        base_url = config.OLLAMA_BASE_URL
    request = urllib.request.Request(
        f"{base_url}/api/show",
        data=json.dumps({"model": model}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            capabilities = json.load(response).get("capabilities")
    except Exception:  # noqa: BLE001
        return None
    return set(capabilities) if capabilities else None


def measure_idle_penalty(profile: Profile, gaps: tuple[int, ...] = (0, 10)) -> dict[int, float]:
    """Reproduce the idle wake-up measurement quoted in this module's docstring."""
    llm = SpeechLLM(profile, tools=None)
    llm.warmup()
    results: dict[int, float] = {}
    questions = ["What time is it?", "How is the weather?", "Tell me a joke.", "How is the system?"]
    for index, gap in enumerate(gaps):
        if gap:
            time.sleep(gap)
        started = time.perf_counter()
        first = None
        for _ in llm.stream(questions[index % len(questions)]):
            if first is None:
                first = time.perf_counter()
        results[gap] = (first - started) * 1000 if first else -1.0
        llm.reset()
    return results
