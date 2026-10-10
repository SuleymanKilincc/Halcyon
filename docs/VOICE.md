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

### Performance profile (GPU)

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

## Hardware profiles

| | `battery` | `performance` | `performance-lowvram` |
|---|---|---|---|
| When | no CUDA device | GPU with ≥ 7 GB VRAM | GPU with < 7 GB VRAM |
| Speech-to-text | `base` on CPU | `large-v3-turbo` on CUDA | `large-v3-turbo` on CUDA |
| Language model | `qwen3.5:2b`, 4k context | `qwen3.5:9b`, 8k context | `qwen3.5:4b`, 8k context |

The profile is chosen once at startup and can be forced with `--profile` or the `JARVIS_PROFILE` environment variable.

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
| `core/llm.py` | Streaming client, tool loop, memory, persona, GPU pre-warming |
| `core/voice_tools.py` | Which tools may be called by voice |
| `bench/latency.py` | Microphone-free latency benchmark |

## Not done yet

- Wake word ("Hey Jarvis")
- Echo cancellation (headphones are required for now)
- The desktop UI (`gui.py`) still uses the original pipeline
- Speaker identification
- Mixed-language sentences
