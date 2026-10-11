# How the project got here

The project began as a text agent and became a real-time voice assistant. This page is the short version of that path: what each stage built, what it got wrong, and what changed because of it. The documents in this folder were written during the early stages and describe those stages, not the current system. For the current system, see the [README](../../README.md) and [docs/VOICE.md](../VOICE.md).

## Stage 1 — A local text agent

A command-line agent: a local model served by Ollama, tools for files, the terminal and the web, and a human approval step before anything risky. First on LangChain, later moved to LangGraph (`MIGRATION_NOTES.md`).

*Documents:* `PROJECT_SUMMARY.md`, `ARCHITECTURE.md`, `QUICKSTART.md`, `EXAMPLES.md`, `TROUBLESHOOTING.md`, `MIGRATION_NOTES.md`

## Stage 2 — A desktop interface with voice

A dark, Iron-Man-inspired desktop UI with an animated waveform, speech input and a spoken reply. Speech was stitched together from off-the-shelf libraries, one request at a time: listen, wait for silence, transcribe, think, then speak. Recognition went through Google's online speech API, so the assistant was only partly local; only the speech output ran on the machine.

*Documents:* `PHASE2_SUMMARY.md`, `PHASE2_CHECKLIST.md`, `GUI_GUIDE.md`

## Stage 3 — More tools, safer tools, two languages

Browser automation, file downloads and archive extraction (the third phase of the original plan). Around the same time, approval prompts moved from the terminal into the interface, and automatic Turkish/English language detection was added with a matching voice.

*Documents:* `ADVANCED_TOOLS_GUIDE.md`, `ADVANCED_TOOLS_UPDATE.md`, `GUI_APPROVAL_GUIDE.md`, `GUI_APPROVAL_UPDATE.md`, `MULTILANG_GUIDE.md`, `MULTILANG_UPDATE.md`

## Stage 4 — Sessions and hardware awareness

Chat sessions stored in SQLite, and live hardware monitoring for the laptop it ran on.

*Documents:* `PHASE4_SUMMARY.md`, `PHASE4_IMPLEMENTATION.md`

## Stage 5 — A real-time voice pipeline, measured

The turn-based design above felt slow, so the voice path was rebuilt around streaming: voice-activity detection ends the turn, the model streams tokens, and the first finished sentence is spoken while the rest is still being written. The work changed character here. Every claim became a measurement:

- latency broken down per stage, and the largest costs found by measuring instead of guessing (a sleeping GPU, a context window too big for 8 GB of VRAM);
- a battery profile and a full-power profile, with the choice made from the hardware at startup;
- a conversation memory, a persona, and tool calling on the voice path.

## Stage 6 — Engineering around the model

- **Tests and CI.** The old interactive scripts moved to `scripts/manual/`, and an automated suite was added that needs no microphone, GPU or model server, run on Windows and Linux on every push.
- **GPU planner.** Model sizes are chosen from the free VRAM, and the placement is checked after loading, because a model that silently spills onto the CPU is slower than a smaller one that fits.
- **Speech-recognition quality.** Whisper invents sentences from silence; a benchmark with controlled noise and reverberation measured the problem and the filters built against it.
- **Honest capabilities.** The assistant is now told exactly which actions are switched off, and a 15-request evaluation measures whether it tells the truth about them.

## What the early documents got wrong

The early documents describe features as working that were switched off in the code, and they report no measurements. That is why the rewrite starts from numbers: a claim in the current documentation is either backed by a command that can be re-run or listed as a limitation.

## What is next

See the roadmap in the [README](../../README.md#roadmap).
