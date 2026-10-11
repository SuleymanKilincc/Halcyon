# Memory: choosing the embedding model

Persistent memory is on the roadmap but not built. This page records the one decision that can be made, and measured, before building it: which model turns a fact and a spoken question into vectors that can be compared.

A memory stores short facts ("my sister is called Elif and is a nurse") and later has to find the right one for a question that shares almost no words with it ("what does my sister do?"). It must do that in Turkish and English, and across them, because facts are stored in whichever language they were said.

## Measurement

`python -m bench.embedding_eval` embeds 20 facts (10 per language) and asks 31 questions with exactly one correct fact each: ten same-language English, ten same-language Turkish, five English questions about Turkish facts, six Turkish questions about English facts. It reports how often the correct fact is ranked first and within the first three. Both models run through Ollama on the GPU.

| | `bge-m3` (MIT) | `embeddinggemma` (Gemma terms) |
|---|---|---|
| English → English | 10 / 10 | 10 / 10 |
| Turkish → Turkish | 8 / 10 | 10 / 10 |
| English question, Turkish fact | 5 / 5 | 5 / 5 |
| Turkish question, English fact | 6 / 6 | 5 / 6 |
| **Correct fact ranked first** | **29 / 31** | **30 / 31** |
| **Correct fact in the first three** | **31 / 31** | **31 / 31** |
| Time per text, warm (best of 3) | 11.0 ms | 11.2 ms |
| Vector size | 1024 | 768 |
| Download | 1.2 GB | 621 MB |

## Reading it

- **Accuracy is a tie.** The two first-place misses of `bge-m3` and the one of `embeddinggemma` are single questions, which is within what a different wording would change. Both always had the right fact in the top three, and a memory that hands the language model the top three facts would have answered all 31. With 31 questions this cannot rank the models; it shows that either works across Turkish and English.
- **Speed is a tie, once warm.** About 11 ms per text for both, on the GPU. A first measurement had reported 737 ms against 111 ms; repeating it gave 10.6 against 11.0. The first run had measured the model being loaded, not the model, and the benchmark now warms up and times the best of three. The lesson carries over to the feature: the first lookup after a model loads is slow, so it needs a warm-up like the language model's.
- **What is left is size and license.** `bge-m3` is MIT and twice the download (1.2 GB against 621 MB); `embeddinggemma` is under Google's Gemma Terms of Use (commercial use allowed, with use restrictions; see [LICENSES.md](LICENSES.md)).

## Decision

Default to **`bge-m3`**: with accuracy and speed tied, the clean MIT license wins for a project that is itself MIT. Keep **`embeddinggemma`** as the configurable smaller alternative (half the download). Revisit when the memory exists and there are real facts to retrieve: the measurement should then be repeated on them.
