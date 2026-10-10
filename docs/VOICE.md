# The voice pipeline

A deep dive into how Jarvis listens, thinks and speaks, and the measurements behind each design decision. For an overview, start with the [README](../README.md).

All figures were measured on the development machine: AMD Ryzen 7 7735HS (8 cores / 16 threads), 32 GB RAM, NVIDIA RTX 4060 Laptop GPU with 8 GB VRAM, Windows 11.

## What it replaced

| | Original implementation | Current pipeline |
|---|---|---|
| Turn-taking | Press a button, listen for a fixed 5 s | Silero VAD detects when you stop talking |
| Speech-to-text | `recognize_google` (**audio sent to Google**) | faster-whisper, fully local |
| Text-to-speech | pyttsx3 / Windows SAPI5 | Piper (ONNX) |
| Generation | Whole answer generated, then spoken | Spoken sentence by sentence as it is generated |
| Interruption | Not possible | Talk over it and it stops |

## Running it

```bash
python -m voice.cli --info          # detected hardware and chosen profile
python -m voice.cli                 # echo mode: repeats what it heard, no LLM
python -m voice.cli --llm           # full assistant
python -m voice.cli --llm --profile battery
python -m voice.cli --devices       # list audio devices; then --input N --output M
```

Latency benchmark (no microphone needed: it synthesises speech with Piper and feeds it through the real pipeline):

```bash
python -m bench.latency
python -m bench.latency --llm
```

## How a turn works

```
microphone (16 kHz, 32 ms frames)
  -> Silero VAD          speech started?  ->  wake the GPU in the background
                         480 ms of silence = the user finished
  -> faster-whisper      text + detected language
  -> qwen3.5 via Ollama  streamed reply, may call tools, sees the last 8 turns
  -> sentence splitter   releases each sentence as soon as it is complete
  -> Piper TTS           plays it
     ^-- the microphone keeps listening: sustained speech stops playback
```

States shown in the terminal: `listening` → `transcribing` → `thinking` → `speaking`.

### Endpointing

The silence needed to end a turn (`VADSettings.min_silence_ms`, 480 ms) is the single most important latency setting: it is dead time added to every turn. Below ~350 ms, natural pauses between words get treated as the end of the sentence. A minimum of 160 ms of speech filters out coughs and clicks, and 320 ms of pre-roll audio is kept so the first syllable is not clipped.

### Streaming speech

The language model streams tokens; the sentence splitter releases a sentence the moment it ends with `.`, `!` or `?` followed by whitespace. Requiring the whitespace is what keeps `3.5 GB` from being split. Openers shorter than 12 characters ("Sure.") are merged into the next sentence, because spoken alone they sound clipped.

### Barge-in

The microphone stays open while Jarvis speaks. A separate, stricter detector (threshold 0.85, at least 280 ms of speech, ignored for the first 250 ms of playback) decides whether you are interrupting. It is stricter than normal listening because, without echo cancellation, the microphone also hears Jarvis through the speakers. **Use headphones**; with them the threshold can be lowered and interruption becomes much more responsive.

## Measurements

### GPU: RTX 4060 Laptop, 8 GB (`gpu-9b-8k`)

| Stage | Time |
|---|---|
| Speech-to-text (`large-v3-turbo`, CUDA) | 234–377 ms |
| Language model, first token (`qwen3.5:9b`, warm) | 114–134 ms |
| **First audio** (you stop speaking → you hear Jarvis) | **1105–1573 ms** |

### Battery profile (CPU only)

| Stage | Time |
|---|---|
| Speech-to-text (`base`, 8 threads) | ~500 ms |
| Language model, first token (`qwen3.5:2b`, warm, fresh prompt) | ~1000 ms |
| First sentence synthesis | ~340 ms |
| **First audio** | **best 1814 ms** |

`qwen3.5:4b` gave ~1600 ms first token under the same conditions; the 2B model was chosen for battery mode because on a voice turn speed is worth more than the extra accuracy.

### Speech-to-text model size vs accuracy

On CPU (int8, 8 threads), scored as exact word-for-word matches on three Turkish sentences and one English sentence:

| Model | Time per sentence | Exact matches | Notes |
|---|---|---|---|
| `tiny` | 269 ms | — | Unusable for Turkish |
| `base` | ~1000 ms | 1 / 4 | CPU default. English perfect, Turkish broken |
| `small` | ~3150 ms | 2 / 4 | Turkish clearly better |
| `large-v3-turbo` | ~13400 ms | 3 / 4 | GPU target model |

The difference in Turkish is concrete:

```
base            "BİVİ SAYA RIM'ın sıcaklığı kaç derece?"
large-v3-turbo  "Bilgisayarımın sıcaklığı kaç derece?"   (exact)

small           "Masa üstündeki bütün piton dosyalarını ister."
large-v3-turbo  "Masa üstündeki bütün Python dosyalarının listeli."
```

The second pair matters for an assistant that writes code: the small model hears "Python" phonetically as *piton*, the large one recognises the term. English was transcribed perfectly at every size; only Turkish is sensitive to model size.

> Measurement note: the input was speech synthesised by Piper, not a real voice, so treat these as a lower bound. Turkish test text **must keep its diacritics** — written as "Bugun" instead of "Bugün", Piper mispronounces it and the measurement becomes meaningless. An earlier version of this table was wrong for exactly that reason.

### Language detection

Detection runs per utterance and is restricted to the languages Jarvis has voices for (`candidate_languages = ("tr", "en")`), because on short audio Whisper sometimes guesses an unrelated language. Result: 4/4 correct, confidence 0.96–1.00. The reply voice switches with the detected language.

**Limitation:** mixing languages inside one sentence (Turkish with English technical terms, as developers often speak) is transcribed as a single language. Switching language between sentences works.

## Choosing models for the GPU

### Measured memory use

From `python -m bench.vram` on the 8 GB card (GiB):

| Component | 4k | 8k | 16k | 32k |
|---|---|---|---|---|
| qwen3.5:2b | 2.19 | 2.30 | 2.41 | 2.55 |
| qwen3.5:4b | 2.91 | 3.04 | 3.38 | 3.82 |
| qwen3.5:9b | 5.11 | 5.24 | 6.10 | 6.74 |

| Speech model (int8_float16) | GiB |
|---|---|
| Whisper base | 0.19 |
| Whisper small | 0.29 |
| Whisper large-v3-turbo | 1.01 |

The desktop and other programs held 0.83–0.92 GiB with nothing of ours loaded, leaving ~7.1 GiB free on the 8 GB card. The 27B model has not been downloaded; its figures in `core/vram.py` are scaled from the 9B ones and marked as estimates.

### Plan, then verify

`core/vram.py` walks a ladder of configurations from best to smallest and picks the first whose language model + speech model + a 0.5 GiB headroom fits the free memory. The headroom exists because Ollama decides placement with a larger internal estimate than the size it reports: with ~7.1 GiB free, the 9B model at 16k (6.10 GiB reported) still spilled onto the CPU. The value was calibrated so the planner accepts the configuration observed to run fully on the GPU here (9B at 8k with the large Whisper) and rejects the one observed to spill.

Because that headroom is not documented and was not fully predictable, the plan is only a first guess. `core/fit.py` then asks Ollama (`/api/ps`) how much of the loaded model is on the GPU; if any of it spilled, it unloads the model and steps down one rung. Forced onto 9B at 16k on the 8 GB card, it reported *"only 84% on the GPU"* — the same split measured by hand earlier — and settled on 9B at 8k at 100%.

The language model is loaded and checked before Whisper, so a step down can still switch to a smaller speech model.

The profile can be forced with `--profile` (`auto`, `battery`, or any configuration name such as `gpu-4b-8k`) or the `JARVIS_PROFILE` environment variable.

### GPU speech recognition needs PyTorch's CUDA libraries

faster-whisper (CTranslate2) does not ship cuBLAS or cuDNN; on Windows it finds them only if they are already loaded in the process. PyTorch's CUDA build bundles them and loads them on import. For a long time GPU transcription worked only because some other module happened to import torch first — measuring Whisper on its own failed with *"cublas64_12.dll is not found"*. `voice/stt.py` now imports torch explicitly before loading Whisper on the GPU.

### A switched-off GPU is not a missing GPU

Laptops can power the discrete GPU off entirely (for example the "Eco" GPU mode in ASUS's G-Helper). Windows then reports it as *installed but not connected* (Device Manager error Code 45), and Python's usual hardware queries — PyTorch, WMI's `Win32_VideoController` — report no GPU at all. `core/hardware.py` additionally asks `Get-PnpDevice`, which distinguishes the two cases, so Jarvis can say *why* it is running on the CPU and how to fix it, rather than silently degrading.

## Design findings

### A larger context window was slower

Placement of `qwen3.5:9b` on 8 GB of VRAM, read from `ollama ps` after loading:

| Context (tokens) | Placement |
|---|---|
| 8192 | **100% GPU** |
| 12288 | 86% GPU / 14% CPU |
| 16384 | 84% GPU / 16% CPU |

Any spill puts transformer layers on the CPU, and every token has to pass through them, so the whole generation runs at CPU speed. The largest context that still fits entirely in VRAM beats a nominally larger one. The model's advertised 262k context is a capability figure, not a usable runtime setting on this card.

### The GPU falls asleep between turns

Time to first token on a warm model:

```
request sent immediately after the previous one    ~140 ms
request sent 10 s after the previous one          ~2126 ms
request sent 20 s after the previous one          ~2130 ms
```

A fixed ~2 s regardless of the gap: the laptop GPU drops into a low-power state when idle and has to wake up. Benchmarks that fire requests back to back never see it; every real conversation does, because people pause to speak and listen. The fix (`SpeechLLM.prewarm`) sends a one-token request the moment the VAD hears speech *start*, so the wake-up overlaps with the user still talking.

### Abandoned streams cost the next turn

Ollama serialises requests per loaded model, and a generation whose client stops reading keeps running until `num_predict`. The next request queues behind it:

```
stream consumed to completion             ~1000–1600 ms first token
stream abandoned after the first token    ~2200–2350 ms first token
```

Closing the stream does not stop the server-side generation. Mitigations: `num_predict` is kept small, and callers that stop early drain the remainder. Barge-in is the one place that cannot drain; there the cost lands on the following turn.

This also explains an early benchmark that reported a near-identical ~3.7 s on every input: it abandoned each stream after the first sentence, so it was measuring its own queue. Suspiciously uniform numbers across different inputs indicate a fixed cost imposed by the harness, not the system under test.

> Measurement note: repeating an identical prompt hits Ollama's KV cache and reports ~120 ms, a figure no real turn will see. Always measure with fresh prompts.

## Modules

| File | Responsibility |
|---|---|
| `voice/settings.py` | Every setting that affects latency or turn-taking, in one place |
| `voice/audio.py` | Microphone capture and interruptible playback |
| `voice/vad.py` | Endpointing and barge-in detection, with separate thresholds |
| `voice/stt.py` | faster-whisper wrapper, device and model resolution |
| `voice/tts.py` | Piper wrapper, sentence splitter, speech text cleaning |
| `voice/pipeline.py` | Turn state machine: listen → transcribe → generate → speak |
| `voice/models.py` | Downloads and validates Piper voices |
| `voice/cli.py` | Terminal front end |
| `core/hardware.py` | GPU, VRAM, battery and CPU detection |
| `core/profiles.py` | Runtime profiles and their selection |
| `core/vram.py` | Measured memory use, configuration ladder, VRAM planner |
| `core/fit.py` | Checks placement after loading and steps down on a spill |
| `core/llm.py` | Streaming client, tool loop, memory, persona, GPU pre-warming |
| `core/voice_tools.py` | Which tools may be called by voice |
| `bench/latency.py` | Microphone-free latency benchmark |
| `bench/vram.py` | Measures GPU memory use per model and context length |

## Not done yet

- Wake word ("Hey Jarvis")
- Echo cancellation (headphones are required for now)
- The desktop UI (`gui.py`) still uses the original pipeline
- Speaker identification
- Mixed-language sentences
