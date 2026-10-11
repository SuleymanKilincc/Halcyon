# Licenses of what Halcyon uses

Halcyon's own code is [MIT](../LICENSE). It is a personal, non-commercial project, and everything it uses is free for that. Some of the parts it depends on carry stricter terms, which would matter to anyone who wanted to use Halcyon commercially or ship it as a bundled installer. They are listed here with the evidence, so nobody has to find out the hard way.

Checked on 2026-10-11 against each component's own license file, package metadata or model card (sources at the end). This is not legal advice.

**The repository contains no third-party model weights or voices.** Models are downloaded by the user from their original sources and are git-ignored, so Halcyon redistributes none of them.

## Code

All direct dependencies in `requirements.txt` are MIT, BSD or Apache-2.0 except two:

| Package | License | What it means |
|---|---|---|
| `piper-tts` (speech synthesis engine) | **GPL-3.0-or-later** | Fine to install and use. A *distributed bundle* that includes it (for example the packaged installer on the roadmap) would have to be offered under GPL-compatible terms, or fetch Piper at install time instead of including it. The older `rhasspy/piper` was MIT, but is archived. |
| `py7zr` (archive extraction) | LGPL-2.1-or-later | Used as a normal library; no obligation beyond keeping it replaceable. |

## Models and voices

| Component | License | Used for | Note |
|---|---|---|---|
| Whisper `large-v3-turbo` (faster-whisper conversion) | MIT | Speech recognition | |
| Silero VAD | MIT | Detecting speech | |
| `qwen3.5` (2B / 4B / 9B, via Ollama) | Apache-2.0 | The language model | |
| `embeddinggemma` | Gemma Terms of Use | Planned memory search | Permits commercial use, but with use restrictions and terms that must be passed on if the model is redistributed. Not an open-source license. |
| `bge-m3` | MIT | Planned memory search (alternative) | See [MEMORY.md](MEMORY.md) |
| Piper voice `tr_TR-dfki-medium` | **CC BY-NC-SA 4.0** | Turkish voice | Non-commercial; adaptations must be shared alike. |
| Piper voice `en_US-ryan-medium` | **CC BY-NC-SA 4.0** | English voice | Non-commercial; adaptations must be shared alike. |
| openWakeWord (code) | Apache-2.0 | Planned wake word | |
| openWakeWord pre-trained models | **CC BY-NC-SA 4.0** | Planned wake word | Its authors say this is because some training data has restrictive licenses. The license of a model *you* train is not stated by the project. |

## What this means in practice

- **Using Halcyon yourself, or as a portfolio project: no problem.** Everything above allows it.
- **A commercial product would need these replaced or relicensed:**
  - *Voices.* Piper's catalogue has exactly one Turkish voice, and it is non-commercial, so there is currently no permissively licensed Turkish voice in Piper. For English, `en_US-libritts_r-medium` lists CC BY 4.0 (whether the voice it was fine-tuned from adds terms was not checked). Another engine would be needed for Turkish: Chatterbox Multilingual (MIT, lists Turkish) is the candidate to evaluate, but it is much heavier than Piper.
  - *Piper's engine,* because of the GPL, or a decision to keep Halcyon's distributed form GPL-compatible.
  - *The wake word,* by training a model on data whose terms are clear.
- **Not used because of its license:** XTTS-v2 (a more natural voice) is under the Coqui Public Model License, which allows non-commercial use only, covers its outputs, and has no commercial license on offer because the company has closed.

## Sources

- Piper engine: `pip` metadata of the installed `piper-tts 1.8.0` (`GPL-3.0-or-later`); [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl).
- Piper voices: `MODEL_CARD` files in [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) for [tr_TR-dfki-medium](https://huggingface.co/rhasspy/piper-voices/raw/main/tr/tr_TR/dfki/medium/MODEL_CARD), [en_US-ryan-medium](https://huggingface.co/rhasspy/piper-voices/raw/main/en/en_US/ryan/medium/MODEL_CARD) and [en_US-libritts_r-medium](https://huggingface.co/rhasspy/piper-voices/raw/main/en/en_US/libritts_r/medium/MODEL_CARD); the catalogue listing of Turkish voices via the Hugging Face API.
- openWakeWord: [README](https://github.com/dscripka/openWakeWord).
- Whisper conversion: [model card](https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo). `bge-m3`: [model card](https://huggingface.co/BAAI/bge-m3).
- `qwen3.5` and `embeddinggemma`: the license text Ollama ships with each model (`ollama show <model> --license`); [Gemma Terms of Use](https://ai.google.dev/gemma/terms).
- XTTS-v2: [Coqui Public Model License](https://coqui.ai/cpml), as summarised by secondary sources.
- Python packages: `pip-licenses` run on the development environment.
