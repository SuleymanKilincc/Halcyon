# How the deep-mode models were chosen

Halcyon's everyday model is `qwen3.5:9b`. [Deep mode](MODES.md) needed a larger one for heavy coding and long stories, and the choice was made by measuring, not by reputation. This page records what was tried, why, what came out, and what the evidence does **not** show, so that the choice can be re-run or overturned.

## The question

An 8 GB card cannot hold two models, so deep mode costs a wait (10 seconds to two minutes) every time it is entered. The wait is only worth asking the user for if the deep model answers *clearly* better than the model already loaded. The question was therefore:

> For code, for facts about films and games, and for keeping an invented world consistent, is any model that fits this machine clearly better than `qwen3.5:9b`, and is a small specialist (a coder model) a cheaper way to get there?

## The machine and the method

Everything below was run on one machine: RTX 4060 Laptop GPU (8 GB), Ryzen 7 7735HS, 32 GB RAM, Windows 11, Ollama 0.40.18, every model at its default Ollama quantisation, context 4096 (10240 when thinking was on), a fixed seed.

Three harnesses, all in `bench/`, all talking to Ollama's HTTP API directly so that nothing of Halcyon's own prompts or tools influences the comparison:

| Harness | What it measures | How it decides |
|---|---|---|
| `python -m bench.code_eval --set easy` / `--set hard` | Whether a model writes working Python (8 tasks per set: parsing, graphs, caching, a repair task, a transaction store ...) | The code block of the reply is run against hidden asserts in a fresh, isolated interpreter. Pass or fail, no judgement involved. |
| `python -m bench.world_session --language en` / `tr` | Facts about films, games and books; a five-turn world with three characters whose traits must not change | A person reads the replies against a written list of rules (`RULES` in the script). Not automated, because keyword rules for "stayed consistent" would be a guess. |
| `python -m voice.cli --info` | Which pack a machine gets | The rules in `core/packs.py`, covered by `tests/test_packs.py` |

**The tests are tested.** A benchmark whose own tests are wrong produces confident nonsense, so every code task ships a reference solution (`bench/code_tasks/*.json`), and `tests/test_bench_code_eval.py` runs the hidden asserts against it on every test run. The same file checks that an empty answer fails every task, that the broken code shown in the two repair tasks fails its own asserts, that a never-ending reply is stopped, and that a cut-off reply fails cleanly. When the first hard-set results looked bad for every model, this is what ruled out "the tests are wrong" in minutes: the references pass.

**Fairness controls.** Same prompts, seed and options for every model; thinking switched off for models that have it (a separate run turned it on); the reply cap raised from 1200 to 3000 tokens in a re-run to rule out truncation as the explanation (it was not, apart from the verbose Light model, see below); one model at a time, so the models never competed for the card (a music player was open and held about 1 GB of VRAM throughout).

## The candidates, and why these

| Model | Download | Licence | Why it was a candidate | Verdict |
|---|---|---|---|---|
| `qwen3.5:9b` | 6.6 GB | Apache-2.0 | The baseline: what runs today | Stays as the general model |
| `qwen2.5-coder:7b` | 4.7 GB | Apache-2.0 | The classic small coding specialist; the obvious "code mode" model | Not better than the baseline; faster only |
| `mimo-v2.6:9b` | 6.6 GB | MIT | A fine-tune of Qwen3.5-9B whose vendor reports large gains on a software-engineering benchmark | Not better than the baseline here, with or without thinking |
| `bonsai-2:9b` | 3.2 GB | Apache-2.0 | A 2-bit version of the same base, the smallest and fastest candidate | Fast, but no better than the baseline |
| `gemma4:e4b` | 9.6 GB | Apache-2.0 | Already installed; small and quick; a candidate for machines that cannot carry a large model | **Light pack** |
| `gemma4:26b-a4b` | 18 GB | Apache-2.0 | A mixture-of-experts model (26B parameters, about 4B active per token), so it can run on 8 GB of VRAM plus system RAM at usable speed | **Standard pack** |

Considered and **not tested**, with the reason they were not pursued:

| Model | Why not |
|---|---|
| A dense 27B model (`qwen3.8:27b`, 18 GB) | Dense: every token touches every weight, so with most of it in system RAM it would run at CPU speed. A mixture-of-experts model of the same size is the better bet on this card. |
| `nemotron-3.5-lightning:30b` (about 19 GB, mixture of experts) | Same size class as the chosen model; no evidence was found that it would beat it, and each download of this size costs about two hours on the connection used here. |
| `ornith-1.5:9b` | No licence could be found, and the only independent review found was sceptical. |
| Community role-play fine-tunes | Unvetted licences and quality; the point of the story test is consistency, which these tend to trade for style. |
| `mistral-nemo:12b` | Kept in reserve as the next candidate for stories if the Light model's rule-breaking proves to matter. |

## Results

Code, thinking off, one run per model:

| Model | Easy set | Hard set | Speed |
|---|---|---|---|
| `qwen3.5:9b` | 6/8 | 3/8 | ~41 tok/s |
| `qwen2.5-coder:7b` | 6/8 | 2/8 | ~50 tok/s |
| `mimo-v2.6:9b` | 6/8 | 2/8 | ~43 tok/s |
| `bonsai-2:9b` | 6/8 | 2/8 | ~75 tok/s |
| `gemma4:e4b` | 8/8 | 4/8 | ~142 tok/s |
| `gemma4:26b-a4b` | 8/8 | 6/8 | ~41 tok/s |

With thinking on (reply cap 7000 tokens), the hard set: `qwen3.5:9b` 5/8 using 37,846 tokens (about 15 minutes), `mimo-v2.6:9b` 3/8 using 19,365. Thinking helps the baseline, at a price no conversation can pay.

Facts and world, in Turkish (the language the assistant is mostly used in):

| Model | Facts (6) | World rules kept (5 turns) |
|---|---|---|
| `gemma4:26b-a4b` | 6/6 | all kept |
| `gemma4:e4b` | 5/6 (dodged one) | one broken: an iron key was picked up without burning |
| `qwen3.5:9b` | 4/6, with invented names beside the right answers | two broken: the iron key, and the missing hand used |

In English, of five clear questions, the 26B model answered all five and `qwen3.5:9b` three: it named Lambert as Geralt's mentor in *The Witcher 3* (it is Vesemir) and Malenia as the form after Radagon in *Elden Ring* (it is the Elden Beast).

Speed of the large model: 25 to 46 tokens/s warm in English, 19 to 27 in Turkish, with part of the model on the CPU as Ollama chose. Loading took 30 to 55 s from a warm disk cache and about 115 s for the first answer after a cold start; in the live end-to-end check the switch took 36 s and the way back 10 s.

## What the choices were

1. **One deep mode, not a coding mode plus a story mode.** The small coding specialists were not better than the baseline at code, so a separate coding model would cost a wait for speed alone. The one model that was clearly better at code (the 26B) was also the one that was better at facts and worlds. One mode means one wait, one model to download, and a simpler thing to explain.
2. **Two packs, by what the machine can carry.** The 26B model needs about 18 GB for the weights; the Light model needs about 10. A pack's requirement is the **VRAM and RAM together**, because Ollama splits a model between them, plus a floor for each (some card for the speech model, some RAM for the system). Details and the estimates: [MODES.md](MODES.md#packs-which-model-deep-mode-runs-on).
3. **The persona was written from the failures.** Facts were invented and rules were broken by the small model, so deep mode's prompt tells the model to keep a running list of established facts, never to contradict it, and to say when it is unsure about a fact. This is a mitigation chosen from the results, not a measured fix: no run compared the same model with and without it.

## What this evidence does not show

- **One machine, one run per model.** Differences of one task are noise; only the large gaps (the 26B model against everything else on the hard set and on facts) mean something. Variation between runs of the same model was not measured.
- **Small sets.** Eight tasks per code set, six fact questions, five world turns. The gaps are real enough to choose on and too small to publish as a ranking.
- **Python only**, written from a one-sentence description. Nothing here says how the models behave on a real repository.
- **The Light model was measured with a 1200-token cap** and all four of its hard-set failures hit it; it was not re-run with a larger cap, so its hard-set score is a floor.
- **Worlds were five turns long.** Consistency over an hour is untested and needs a persistent world file (see "Not done yet" in [MODES.md](MODES.md)).
- **The English world prompt in `bench/world_session.py` is a cleaned version** (it states Captain Halle's gender, which the Turkish run did); the English probes are the ones that were run, the English world session has not been re-run with it.
- **Other machines.** Nothing below 8 GB of VRAM with 32 GB of RAM, nothing with the model fully on a large card, nothing on non-NVIDIA hardware was run. The packs are estimates there, and `--info` says which are which.
- **Quantisation.** Every model was run at Ollama's default; a different quantisation of the same model may behave differently.

## Re-running it

```bash
python -m bench.code_eval --check                              # the tests of the tests; no model needed
python -m bench.code_eval --set hard gemma4:26b-a4b qwen3.5:9b
python -m bench.code_eval --set hard --max-tokens 3000 gemma4:e4b
python -m bench.world_session --language tr gemma4:26b-a4b
```

A new candidate is added by pulling it and naming it; a new task by adding an entry (prompt, hidden asserts, reference solution) to `bench/code_tasks/*.json`. If a result changes the choice, the table in `core/packs.py` and the numbers in [MODES.md](MODES.md) are the two places to edit.
