"""
Language model access for the voice path.

Uses the ``ollama`` client directly rather than LangChain: one less layer on a
hot path, and explicit control of ``think`` per request. LangChain remains the
right tool for the agent/tool-calling path in ``agent.py``.

**Abandoned streams cost the next turn.** Ollama serialises requests per loaded
model, and a generation whose client stops reading keeps running to
``num_predict``; the next request queues behind it. Measured here, warm, as
time-to-first-token of the request *following* an abandoned stream:

    stream consumed to completion            ~1000-1600 ms   (fresh prompt)
    stream abandoned after the first token   ~2200-2350 ms

Calling ``.close()`` does **not** avoid this, on either client — that was
tested and it makes no difference. Two mitigations are in place instead:

* ``num_predict`` is kept small in the profiles, which bounds how long an
  orphaned generation can run.
* Callers that stop early drain the remainder once their measurements or
  playback decisions are done (see ``bench/latency.py``).

The one place that genuinely cannot drain is barge-in, where the point is to
stop immediately. There the penalty lands on the following turn and is partly
hidden by the user still speaking. On GPU, where generation is several times
faster, it shrinks proportionally.

Note on measuring this: repeating an identical prompt hits Ollama's KV cache
and reports ~120 ms, which is not a number any real turn will ever see. Always
measure with a fresh prompt.
"""

from __future__ import annotations

from collections.abc import Iterator

from core.profiles import Profile

SPEECH_SYSTEM_PROMPT = (
    "Sen Jarvis'sin, kullanicinin yerel bilgisayarinda calisan bir asistansin. "
    "Sesli konusuyorsun: cevaplarin kisa, dogal ve konusma dilinde olsun. "
    "Madde isareti, baslik, kod blogu veya emoji kullanma. En fazla iki cumle kur. "
    "Kullanici hangi dilde konusursa o dilde cevap ver."
)


class SpeechLLM:
    """A streaming chat client sized and configured by a runtime profile."""

    def __init__(self, profile: Profile, *, temperature: float = 0.4,
                 base_url: str | None = None) -> None:
        import ollama

        if base_url is None:
            import config

            base_url = config.OLLAMA_BASE_URL

        self.profile = profile
        self.model = profile.llm_model
        self._client = ollama.Client(host=base_url)
        self._options = {
            "num_predict": profile.llm_num_predict,
            "num_ctx": profile.llm_num_ctx,
            "temperature": temperature,
        }

    def stream(self, prompt: str, system: str = SPEECH_SYSTEM_PROMPT) -> Iterator[str]:
        """
        Yield response text deltas.

        The underlying stream is closed in a ``finally`` for tidiness, but see
        the module docstring: closing does not stop the server-side generation.
        Where you can afford to, drain this generator rather than abandoning it.
        """
        response = self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            stream=True,
            think=self.profile.llm_reasoning,
            options=self._options,
        )
        try:
            for chunk in response:
                text = chunk.get("message", {}).get("content", "")
                if text:
                    yield text
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()

    def warmup(self) -> None:
        """
        Load the model into memory before the first real turn.

        A cold first token costs 3.7-6.7 s on this machine; warm and on a fresh
        prompt it is ~1.0-1.6 s. Paying that during startup rather than during
        the user's first sentence is the whole point.

        The generation is consumed to completion deliberately. Abandoning it
        would leave the server generating into a stream nobody reads, and the
        user's first real question would then queue behind the warmup.
        """
        for _ in self.stream("merhaba", system="Tek kelimeyle cevap ver."):
            pass


def build_llm(profile: Profile, *, temperature: float = 0.4,
              base_url: str | None = None) -> SpeechLLM:
    return SpeechLLM(profile, temperature=temperature, base_url=base_url)


def stream_reply(llm: SpeechLLM, prompt: str,
                 system: str = SPEECH_SYSTEM_PROMPT) -> Iterator[str]:
    return llm.stream(prompt, system)


def check_model_available(profile: Profile, *, base_url: str | None = None) -> tuple[bool, str]:
    """
    Verify the profile's model is actually pulled.

    A missing model otherwise surfaces as a confusing mid-conversation error,
    several seconds into what looked like a working startup.
    """
    import json
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
