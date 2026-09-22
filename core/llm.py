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

Note on measuring any of this: repeating an identical prompt hits Ollama's KV
cache and reports ~120 ms, which no real turn will ever see. Measure with a
fresh prompt.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Any

from core.profiles import Profile

JARVIS_PERSONA = (
    "Sen Jarvis'sin: kullanicinin kendi bilgisayarinda calisan, ona bagli ve "
    "sakin bir asistan. Kullaniciya 'efendim' diye hitap edersin - her cumlede "
    "degil, dogal dustugu yerde. Olcülü, kendinden emin ve az konusan bir "
    "uslubun var; abartili neseli degilsin.\n"
    "Sesli konusuyorsun. Bu yuzden: kisa cevap ver, en fazla iki cumle. "
    "Madde isareti, baslik, kod blogu, emoji veya yildiz kullanma - bunlar "
    "sesli okundugunda anlamsiz. Sayilari ve kisaltmalari okunacak sekilde yaz.\n"
    "Kullanici hangi dilde konusursa o dilde cevap ver.\n"
    "Bir islemi yapabiliyorsan once yap, sonra sonucu tek cumleyle soyle. "
    "Yapamadigin bir sey istenirse uydurma; neyi yapamadigini kisaca soyle."
)

# Kept for callers that want the plain assistant with no persona or tools.
SPEECH_SYSTEM_PROMPT = JARVIS_PERSONA

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
        system: str = JARVIS_PERSONA,
        tools: list[Any] | None = None,
        history_turns: int = DEFAULT_HISTORY_TURNS,
    ) -> None:
        import ollama

        if base_url is None:
            import config

            base_url = config.OLLAMA_BASE_URL

        self.profile = profile
        self.model = profile.llm_model
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

        self._prewarm_lock = threading.Lock()
        self._prewarming = False
        self.last_tool_calls: list[str] = []

    # ------------------------------------------------------------- lifecycle

    def reset(self) -> None:
        """Forget the conversation, keep the loaded model."""
        self._history.clear()

    def warmup(self) -> None:
        """
        Load the weights before the first real turn.

        Consumed to completion deliberately: an abandoned warmup would leave
        the server generating, and the user's first question would queue
        behind it.
        """
        for _ in self._raw_stream([{"role": "user", "content": "merhaba"}],
                                  system="Tek kelimeyle cevap ver.", use_tools=False):
            pass

    def prewarm(self) -> None:
        """
        Wake the GPU in the background. Returns immediately.

        Called when the VAD hears speech start, so the ~2 s idle wake-up runs
        while the user is still talking instead of after they finish. Cheap
        enough to fire on every utterance: one token, no history, no tools.
        """
        with self._prewarm_lock:
            if self._prewarming:
                return
            self._prewarming = True

        def run() -> None:
            try:
                for _ in self._raw_stream(
                    [{"role": "user", "content": "."}],
                    system="Tek karakter yaz.", use_tools=False, num_predict=1,
                ):
                    pass
            except Exception:  # noqa: BLE001 - a failed prewarm must never break a turn
                pass
            finally:
                with self._prewarm_lock:
                    self._prewarming = False

        threading.Thread(target=run, name="jarvis-prewarm", daemon=True).start()

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
            "think": self.profile.llm_reasoning,
            "options": options,
        }
        if use_tools and self._tool_specs:
            payload["tools"] = self._tool_specs
        return self._client.chat(**payload)

    def stream(self, prompt: str, system: str | None = None) -> Iterator[str]:
        """
        Yield response text deltas for one user turn.

        Runs the tool loop transparently: if the model asks for a tool, it is
        executed and the conversation continues, so the caller sees only text.
        """
        self._history.append({"role": "user", "content": prompt})
        self.last_tool_calls = []
        spoken: list[str] = []

        try:
            # Bounded so one confused turn cannot spin forever while the user
            # sits in silence waiting for a reply.
            for round_index in range(4):
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

                response = self._raw_stream(self._history, system=system)
                try:
                    for chunk in response:
                        message = chunk.get("message", {}) or {}
                        text = message.get("content", "")
                        if text:
                            assistant_text.append(text)
                            spoken.append(text)
                            yield text
                        for call in message.get("tool_calls") or []:
                            tool_calls.append(call)
                finally:
                    close = getattr(response, "close", None)
                    if close is not None:
                        close()

                if not tool_calls:
                    self._history.append(
                        {"role": "assistant", "content": "".join(assistant_text)}
                    )
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
                yield "Bunu tamamlayamadim efendim."
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
                return name, f"Arac argumanlari okunamadi: {arguments!r}"

        tool = self._tools.get(name)
        if tool is None:
            return name, f"'{name}' diye bir arac yok."

        try:
            result = tool.invoke(arguments)
        except Exception as exc:  # noqa: BLE001 - tool errors are data for the model
            return name, f"Arac hatasi: {exc}"

        text = result if isinstance(result, str) else str(result)
        # A directory listing can be thousands of lines. The model only needs
        # enough to answer in two spoken sentences, and the rest is context
        # budget that pushes the KV cache out of VRAM.
        if len(text) > 4000:
            text = text[:4000] + "\n... (kisaltildi)"
        return name, text

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
              tools: list[Any] | None = None, system: str = JARVIS_PERSONA) -> SpeechLLM:
    return SpeechLLM(profile, temperature=temperature, base_url=base_url,
                     tools=tools, system=system)


def stream_reply(llm: SpeechLLM, prompt: str, system: str | None = None) -> Iterator[str]:
    return llm.stream(prompt, system)


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
        return False, f"Ollama'ya baglanilamadi ({base_url}): {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Ollama'ya baglanilamadi ({base_url}): {exc}"

    names = {model.get("name", "") for model in tags.get("models", [])}
    if profile.llm_model in names:
        return True, ""
    return False, (
        f"'{profile.llm_model}' kurulu degil. Once indirin:\n"
        f"    ollama pull {profile.llm_model}\n"
        f"  Kurulu modeller: {', '.join(sorted(names)) or '(yok)'}"
    )


def measure_idle_penalty(profile: Profile, gaps: tuple[int, ...] = (0, 10)) -> dict[int, float]:
    """Reproduce the idle wake-up measurement quoted in this module's docstring."""
    llm = SpeechLLM(profile, tools=None)
    llm.warmup()
    results: dict[int, float] = {}
    questions = ["Saat kac?", "Bugun hava nasil?", "Bana bir fikra anlat.", "Sistem nasil?"]
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
