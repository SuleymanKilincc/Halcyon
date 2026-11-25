"""
The conversation around mode switching (the rules live in core/modes.py).

``ModeController.handler`` has the same shape as the handlers the CLI already
uses - a transcript in, text deltas out - so it wraps the language model for the
voice loop and the typed mode alike, and neither needs to know it exists.

Every turn goes one of four ways:

1. **An answer to an open question.** The assistant asked "Shall we switch?" last
   turn; "evet" switches and then answers the request that was waiting, "hayır"
   answers it where we are, and remembers the no for a few turns so it does not
   ask again. Anything else is simply a new request: the question lapses.
2. **A mode named outright** ("switch to code mode", "genel moda dön"). The user
   asked, so there is nothing to confirm; the wait is still announced.
3. **A request that deserves another mode.** If entering it needs a model load,
   the assistant asks first and says how long it takes and why. If nothing has
   to load (a mode that only changes the prompt), it just says so and goes.
4. **Anything else**: answered by the current mode.

Two things keep it from nagging. A tier 2 request is the only thing that
proposes a switch, plus a coding *session* (three tier 1 coding turns in a row is
treated as tier 2, because that is what it has become). And a "no" silences
that mode for COOLDOWN_TURNS turns.

Going back mirrors going out: after OFF_TOPIC_TURNS turns that have nothing to do
with the mode we are in, the assistant offers to return to general mode.

Switching is the only slow thing here, and it is announced before it starts.
The handler yields the announcement and *then* loads, so in the voice loop the
sentence is spoken while the model swaps.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Any

from core.llm import installed_models, model_capabilities, stream_reply
from core.modes import (
    Intent,
    Mode,
    classify,
    default_modes,
    explicit_mode,
    parse_confirmation,
    say,
    seconds_phrase,
)
from core.profiles import Profile
from core.voice_tools import capability_statement, environment_statement
from voice.language import guess_language


@dataclass
class _Pending:
    """A switch the assistant has offered and is waiting to hear about."""

    mode: Mode
    prompt: str   # what the user asked; answered after the switch (or without it)
    kind: str     # "switch" (towards a specialist) or "return" (back to general)


@dataclass
class _State:
    """What the language model was last known to be running as, for rolling back a failed switch."""

    profile: Profile
    system: str
    use_tools: bool
    supports_thinking: bool


class ModeController:
    MOMENTUM_TURNS = 3     # tier 1 turns in a row in one category count as a tier 2 session
    OFF_TOPIC_TURNS = 3    # turns away from the current mode before offering to leave it
    COOLDOWN_TURNS = 6     # turns a declined mode stays quiet

    def __init__(
        self,
        llm: Any,  # noqa: ANN401 - core.llm.SpeechLLM, or anything shaped like it (see the tests)
        *,
        spoken: bool = True,
        modes: dict[str, Mode] | None = None,
        installed: Callable[[], set[str] | None] = installed_models,
        capabilities: Callable[[str], set[str] | None] = model_capabilities,
        log: Callable[[str], None] = print,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.llm = llm
        self.spoken = spoken
        self.modes = modes or default_modes()
        self.general = self.modes["general"]
        self._installed = installed
        self._capabilities = capabilities
        self.log = log
        self.clock = clock

        self.base_profile: Profile = llm.profile
        self.current: Mode = self.general
        self.pending: _Pending | None = None
        self.turn = 0
        self.last_intent: Intent | None = None
        self._recent: deque[Intent] = deque(maxlen=8)
        self._declined_until: dict[str, int] = {}
        self._told_missing: set[str] = set()
        self._load_seconds: dict[str, float] = {}   # measured, per model name
        self._state = _State(llm.profile, llm.base_system, True, True)

    # ------------------------------------------------------------------ status

    def status(self) -> str:
        """One line for the console: the mode and how the last request was read."""
        intent = self.last_intent
        read = f"{intent.category} tier {intent.tier}" if intent else "-"
        waiting = " | waiting for your answer" if self.pending else ""
        return f"mode: {self.current.key} | request: {read}{waiting}"

    # ----------------------------------------------------------------- handler

    def handler(self, transcript: Any) -> Iterator[str]:  # noqa: ANN401 - voice.stt.Transcript
        text = transcript.text.strip()
        language = guess_language(text, fallback=transcript.language)
        self.turn += 1
        self.llm.last_tool_calls = []

        if self.pending is not None:
            pending, self.pending = self.pending, None
            answer = parse_confirmation(text)
            if answer == "yes":
                yield from self._accept(pending, language)
                return
            if answer == "no":
                yield from self._decline(pending, language)
                return
            # Anything else is a new request; the question lapses without a word.

        named = explicit_mode(text)
        if named is not None and named in self.modes:
            self.last_intent = None
            yield from self._explicit(self.modes[named], language)
            return

        intent = classify(text)
        self.last_intent = intent
        self._recent.append(intent)

        target = self._wanted(intent)
        if target is None and self._drifted():
            target = self.general
        if target is not None and target.key != self.current.key:
            yield from self._propose(target, text, language, category=intent.category)
            return
        yield from self._answer(text, language)

    # ----------------------------------------------------------------- deciding

    def _tier(self, intent: Intent) -> int:
        """The tier, raised to 2 when the last few turns have been the same sustained work."""
        served = {category for m in self.modes.values() for category in m.categories}
        if intent.tier == 2 or intent.category not in served:
            return intent.tier
        streak = 0
        for earlier in reversed(self._recent):
            if earlier.category != intent.category or earlier.tier < 1:
                break
            streak += 1
        return 2 if streak >= self.MOMENTUM_TURNS else intent.tier

    def _wanted(self, intent: Intent) -> Mode | None:
        if self._tier(intent) < 2:
            return None
        return next((m for m in self.modes.values() if intent.category in m.categories), None)

    def _drifted(self) -> bool:
        """The last few turns have had nothing to do with the mode we are in."""
        categories = self.current.categories
        if not categories or len(self._recent) < self.OFF_TOPIC_TURNS:
            return False
        latest = list(self._recent)[-self.OFF_TOPIC_TURNS:]
        return all(intent.category not in categories for intent in latest)

    def _on_cooldown(self, mode: Mode) -> bool:
        return self._declined_until.get(mode.key, 0) > self.turn

    def _model_of(self, mode: Mode) -> str:
        return mode.model or self.base_profile.llm_model

    def _needs_load(self, mode: Mode) -> bool:
        return self._model_of(mode) != self.llm.model

    def _available(self, mode: Mode) -> bool:
        if mode.model is None:
            return True
        names = self._installed()
        return names is None or mode.model in names   # unknown: try, and fail gracefully

    def _seconds(self, mode: Mode, language: str) -> str:
        return seconds_phrase(language, mode.load_seconds, self._load_seconds.get(self._model_of(mode)))

    # ----------------------------------------------------------------- dialogue

    def _propose(self, target: Mode, prompt: str, language: str, category: str | None = None) -> Iterator[str]:
        if self._on_cooldown(target):
            yield from self._answer(prompt, language)
            return
        if not self._available(target):
            if target.key not in self._told_missing:
                self._told_missing.add(target.key)
                size = f" ({target.download_note})" if target.download_note else ""
                self.log(f"[modes] {target.name['en']} needs the model '{target.model}'{size}, which is not "
                         f"installed. Pull it once with: ollama pull {target.model}")
                yield say("missing", language, mode=target, current=self.current) + " "
            yield from self._answer(prompt, language)
            return
        if not self._needs_load(target):
            # Nothing to wait for, so nothing to ask.
            yield from self._enter(target, language)
            yield from self._answer(prompt, language)
            return

        kind = "return" if not target.categories else "switch"
        self.pending = _Pending(target, prompt, kind)
        yield say("ask_return" if kind == "return" else "ask_switch", language, mode=target,
                  current=self.current, seconds=self._seconds(target, language), category=category)

    def _accept(self, pending: _Pending, language: str) -> Iterator[str]:
        yield from self._enter(pending.mode, language)
        yield from self._answer(pending.prompt, language)

    def _decline(self, pending: _Pending, language: str) -> Iterator[str]:
        self._declined_until[pending.mode.key] = self.turn + self.COOLDOWN_TURNS
        yield say("declined", language, mode=self.current) + " "
        yield from self._answer(pending.prompt, language)

    def _explicit(self, target: Mode, language: str) -> Iterator[str]:
        self._declined_until.pop(target.key, None)
        if target.key == self.current.key:
            yield say("already", language, mode=self.current)
            return
        if not self._available(target):
            yield say("missing", language, mode=target, current=self.current)
            return
        yield from self._enter(target, language)

    def _answer(self, text: str, language: str) -> Iterator[str]:
        yield from stream_reply(self.llm, text, language=language)

    # ---------------------------------------------------------------- switching

    def _enter(self, target: Mode, language: str) -> Iterator[str]:
        """Announce, switch, report. The announcement goes out before the slow part starts."""
        if self._needs_load(target):
            yield say("switching_hard", language, mode=target, seconds=self._seconds(target, language)) + " "
        else:
            yield say("switching_soft", language, mode=target) + " "

        if self._apply(target):
            self.current = target
            yield say("ready", language, mode=target) + " "
        else:
            yield say("failed", language, mode=target, current=self.current) + " "

    def _profile_for(self, mode: Mode) -> Profile:
        if mode.key == self.general.key:
            return self.base_profile
        changes: dict[str, Any] = {
            "name": f"{self.base_profile.name}+{mode.key}",
            "label": f"{self.base_profile.label} + {mode.key}",
        }
        if mode.model:
            changes["llm_model"] = mode.model
        predict = mode.num_predict_spoken if self.spoken else mode.num_predict_typed
        if predict:
            changes["llm_num_predict"] = predict
        return replace(self.base_profile, **changes)

    def _system_for(self, mode: Mode, use_tools: bool) -> str:
        persona = mode.persona_spoken if self.spoken else mode.persona_typed
        if persona:
            tools = self.llm.tool_objects() if use_tools else []
            system = persona + "\n" + capability_statement(tools)
            return system + ("\n" + environment_statement() if tools else "")
        system = self.llm.base_system
        return system + ("\n" + mode.addendum if mode.addendum else "")

    def _apply(self, mode: Mode) -> bool:
        profile = self._profile_for(mode)
        changing = profile.llm_model != self.llm.model
        started = self.clock()
        self.llm.begin_switch()
        try:
            capabilities = self._capabilities(profile.llm_model) if changing else None
            # Unknown (Ollama too old to say): keep the defaults rather than guess.
            use_tools = capabilities is None or "tools" in capabilities
            supports_thinking = capabilities is None or "thinking" in capabilities
            if changing:
                self.llm.unload()          # free the card first: two models do not fit in 8 GB
            self.llm.apply_mode(profile, system=self._system_for(mode, use_tools),
                                use_tools=use_tools, supports_thinking=supports_thinking)
            if changing:
                self.llm.warmup()
        except Exception as exc:  # noqa: BLE001 - a failed switch must leave a working assistant
            self.log(f"[modes] switching to {mode.key} failed: {exc}")
            self._roll_back()
            return False
        finally:
            self.llm.end_switch()

        if changing:
            self._load_seconds[profile.llm_model] = self.clock() - started
        self._state = _State(profile, self.llm.system, use_tools, supports_thinking)
        return True

    def _roll_back(self) -> None:
        """Back to what was running; the old model was unloaded, so ask for it again (best effort)."""
        state = self._state
        try:
            self.llm.apply_mode(state.profile, system=state.system, use_tools=state.use_tools,
                                supports_thinking=state.supports_thinking)
            self.llm.warmup()
        except Exception as exc:  # noqa: BLE001
            self.log(f"[modes] could not restore the previous mode: {exc}")
