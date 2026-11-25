# Modes

One small local model does everyday talk well. A long coding job, a long story with a world to keep track of, or a question about a film or a game is a different workload: a larger model, a longer reply budget, a prompt that allows code blocks and asks for care. On an 8 GB card the two models do not fit together, so using the larger one means unloading the first and loading the other, which takes seconds to minutes.

So the question is never only "is this code?" but **"is this worth a wait?"** Halcyon answers it in three steps and never swaps models behind the user's back.

## Categories and tiers

Every request is placed in a **category** (`code`, `story`, `research`, `daily`, `chat`) and a **tier**:

| Tier | Meaning | Example | What happens |
|---|---|---|---|
| 0 | The current model handles it | "What does *idempotent* mean?", "What makes a good story?" | Answered. A switch is never offered. |
| 1 | Still fine, but this is the border | "Write a function that ...", "Write me a short story" | Answered. Counts towards a session. |
| 2 | A bigger model would clearly do better | "Write me a todo app from scratch", "Let us role-play, you are the game master" | Offers to switch. |

Three tier 1 turns of the same sustained work in a row (a coding *session*, a story that keeps growing) are treated as tier 2, because that is what the conversation has become.

The classifier (`core/modes.py: classify`) is rule-based on purpose. It runs on every turn, so it must cost nothing and behave the same way twice; its mistakes are cheap (at worst a question the user declines), and every rule is pinned by an example in `tests/test_modes.py`. "Scenario" and "plot" next to code are still code (a test scenario, a matplotlib plot); role-play is a story whatever else is in the request.

## What the user hears

The user hears about **modes**, not models. There is one heavy mode:

- **Deep mode** takes the work where a larger model measurably answered better: big coding jobs and long stories or role-play. Questions about films, games and books are also answered better there (the small model invented facts), but a question on its own never makes the assistant offer a switch: it is a lookup, tier 0, and in deep mode it counts as off-topic. Ask for deep mode by name when you want it for those. The assistant asks first, names the wait and the reason, and waits for a yes:

  > "This looks like a longer story to build, and deep mode suits it better. Switching takes about 30 to 120 seconds, because I have to unload the current model and load the deep one. Shall we switch?"

  *Yes* → announces, switches, then answers the request that was waiting. *No* → answers where it is, and stays quiet about that mode for six turns. Anything else is treated as a new request and the question lapses.
- **Research mode** only changes the prompt. Nothing to load, so nothing to ask; it says "Switching to research mode." and goes.

You can also ask by name at any time: *"switch to deep mode"* (also *"kod moduna geç"*, *"senaryo moduna geç"*, *"genel moda dön"*). The wait is still announced; there is nothing to confirm because you asked. A sentence that *refuses* a mode by name (*"I don't want deep mode"*, *"derin moda geçme"*) is never read as asking for it, and that mode is not offered for a while; a refusal worded in a sentence (*"No, just do it here"*, *"Hayır, burada devam et"*) answers an offer like a plain no.

After three turns that have nothing to do with the mode you are in, it offers to go back. The first switch is timed, and the next offer quotes the measured time instead of the estimate.

The offer is spoken in the language of the request (Turkish and English). One detail that mattered: `voice/tts.py` drops sentences that begin like a closing offer ("Shall I ...") after an answer, so the question is worded "Shall we ...?" and a test fails if any sentence of ours would be dropped.

## Packs: which model deep mode runs on

Deep mode needs a larger model, and a larger model needs more memory, so the model is chosen from what the machine can carry (`core/packs.py`):

| Pack | Model | Download | Needs | First load | Status |
|---|---|---|---|---|---|
| **Standard** | `gemma4:26b-a4b` | 18 GB | about **32 GB of VRAM and RAM together**, with at least 4 GB of VRAM and 8 GB of RAM | 30 to 120 s | Measured on an RTX 4060 Laptop (8 GB) with 32 GB of RAM, so 40 GB together; the 32 GB figure is an estimate |
| **Light** | `gemma4:e4b` | 9.6 GB | about **16 GB together**, with at least 4 GB of VRAM and 8 GB of RAM | 10 to 30 s | Measured on the same machine; the smaller requirements are estimates |

**The requirement is the total, not one kind of memory.** Ollama splits a model between the graphics card and system RAM, so what matters is that the two together hold it; the card's share decides how fast it runs, and a model that sits entirely on the card is the fastest. A machine with 16 GB of VRAM and 16 GB of RAM carries the Standard pack just as one with 8 GB and 24 GB does, and so does one with 24 GB and 8 GB. The two floors exist because a huge total in one kind is not enough: with almost no card the speech model has nowhere to run, and with almost no RAM the system and Halcyon's own models have no room. Halcyon only detects NVIDIA cards today; other hardware is not recognised and gets no deep mode.

A machine gets the best pack it satisfies; a pack that is already installed wins over a better one that is not. A machine too small for any pack (or with no supported GPU) gets **no deep mode at all**, so it is never offered something it cannot carry. `python -m voice.cli --info` lists the packs, marks each *measured*, *estimated* or *too small* for this machine, and shows what is installed. `HALCYON_DEEP_MODEL=<name>` names another model; it is used whatever the hardware says.

Only the development machine has been tested. *Measured* in `--info` means a machine like that one; every other machine that fits is an **estimate**: more of the model on the card should be faster, less of it slower, and nothing below the Light pack or above the Standard one has been run. The table is meant to grow when more machines have been tried, and every figure in it is one line in `core/packs.py`.

The pack is downloaded by the user, never by Halcyon: until it is installed, the assistant says so once, prints the command and the pack's size to the console, and carries on in general mode.

```bash
ollama pull gemma4:26b-a4b     # Standard, 18 GB
ollama pull gemma4:e4b         # Light, 9.6 GB
```

## What is switched

| | General mode | Deep mode (typed) | Deep mode (spoken) | Research mode |
|---|---|---|---|---|
| Model | the profile's own (`qwen3.5:9b` on 8 GB) | the pack's model | same | the profile's own |
| Reply budget | profile (300 tokens) | 1500 | 400 | 700 typed, 420 spoken |
| Prompt | the Halcyon persona | careful engineer, game master that keeps a list of established facts, honest about facts it is unsure of | the same, with code described in words (no symbols) | persona + "search first, name the source" |

The conversation is kept across a switch: after moving to deep mode, "what was my name?" still works. Before the new model loads, Ollama is asked what it can do (`/api/show`): a model without `tools` is not sent tools, and one without `thinking` is not sent the `think` parameter, because both are errors rather than being ignored. Capabilities Ollama does not report are left at their defaults.

A failed switch (model will not load, out of memory) rolls back to what was running and says so; the request is still answered.

## Using it

On by default in `python -m voice.cli --llm` and `--text`. Turn it off with `--no-modes`. In `--text` mode the grey line under each reply shows the mode and how the request was read:

```
tools: none | first text 2.2 s | mode: general | request: story tier 2 | waiting for your answer
```

## Measured

How the models were chosen, what was left out and why, and what this evidence does not show are in [MODEL_SELECTION.md](MODEL_SELECTION.md); the scripts are `bench/code_eval.py` and `bench/world_session.py`, and their own tests check the benchmark's asserts against reference solutions.

All through the Ollama HTTP API on the development machine (RTX 4060 Laptop 8 GB, 32 GB RAM), thinking off, one run each, fixed seed. With so few cases a one-task difference is noise; only the large gaps mean anything. The code tests have hidden asserts and were checked against reference solutions, so a failure is the model's.

**Code** (two sets of 8 Python tasks):

| Model | Easy set | Hard set | Speed |
|---|---|---|---|
| `qwen3.5:9b` (the general model) | 6/8 | 3/8 | ~41 tok/s |
| `qwen2.5-coder:7b` | 6/8 | 2/8 | ~50 tok/s |
| `mimo-v2.6:9b` | 6/8 | 2/8 | ~43 tok/s |
| `bonsai-2:9b` | 6/8 | 2/8 | ~75 tok/s |
| `gemma4:e4b` (Light) | 8/8 | 4/8 | ~142 tok/s |
| `gemma4:26b-a4b` (Standard, part on the CPU) | 8/8 | 6/8 | ~41 tok/s |

Small coding specialists were not better than the general model; what they bought was speed. Letting the 9B models think raised `qwen3.5:9b` from 3/8 to 5/8 on the hard set but cost 38k tokens (about 15 minutes), which is unusable in a conversation. Raising the reply cap from 1200 to 3000 tokens changed nothing, so truncation was not what separated the models (the Light model is verbose, though: all four of its hard-set failures hit the 1200-token cap, and it was not re-run with a larger one).

**Facts about films and games, and a five-turn world with three characters** (a mute cartographer, a ferryman afraid of water, a one-handed captain; a world where iron burns the skin), in Turkish:

| Model | Facts (6 questions) | World rules kept (5 turns) |
|---|---|---|
| `gemma4:26b-a4b` | 6/6 | all kept |
| `gemma4:e4b` | 5/6 (dodged one question) | one broken: an iron key was picked up without burning |
| `qwen3.5:9b` | 4/6, with invented names around the right answers | two broken: the iron key, and the missing hand used |

In English, of five clear questions, the 26B model answered 5 and the 9B model 3 (it named the wrong mentor in *The Witcher 3* and the wrong final boss in *Elden Ring*). The persona of deep mode therefore tells the model to say when it is not sure about a fact.

**Speed of switching.** The 26B model ran at 25 to 46 tokens/s warm, about 20 to 27 tokens/s in Turkish, with roughly 20% of it on the CPU. Loading it took 30 to 55 s from a warm disk cache and about 115 s for the first answer after a cold start, which is where the 30 to 120 s estimate comes from. The measured time replaces it after the first switch.

**End to end, typed, in Turkish, with the real models:** a role-play request was met with the offer (2.3 s, nothing loaded), *"evet"* announced the switch and loaded the 26B model in **36 s** (the first sentence of the story followed at once), the assistant opened with a list of established world facts as the prompt asks, and *"genel moda dön"* took **10 s**. The name given in the first turn was used in the first reply in deep mode, so the conversation survives the swap; a later "what was my name?" was read as the role-play character's name by both models, which is a prompt ambiguity inside a game, not lost history.

## Not done yet

- **Long scenarios.** The world session above is five turns with the rules in the prompt. A story that runs for hours needs a persistent *world file* (characters, rules, timeline) kept outside the chat context; that belongs with the "persistent memory" roadmap item.
- **Spoken code mode can only describe code.** Reading code aloud is useless, and the voice loop has no second channel to show it on screen. A display channel is the next step.
- **The classifier knows English and Turkish keywords only**, and a request with none of them (phrased in other words) is read as chat. That is the safe direction: no switch is offered.
- **Packs for other machines are estimates.** Only the development machine has been run: no other split of VRAM and RAM, nothing below the Light pack, nothing above the Standard one.
- Writing files by voice waits for the confirmation layer on the roadmap.
