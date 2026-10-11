"""
Which embedding model should the assistant's long-term memory use?

    python -m bench.embedding_eval
    python -m bench.embedding_eval --models bge-m3 embeddinggemma

A memory feature stores short facts about the user and later retrieves the
right one for a spoken question. Retrieval works by comparing embeddings, so
the model must (a) match a question to a fact that shares almost no words with
it, and (b) do so across Turkish and English, because the user speaks both and
facts are stored in whichever language they were said.

Twenty facts (ten per language) and thirty-one questions with one correct
fact each: same-language paraphrases, and cross-language ones. Reported:
how often the correct fact is ranked first, and within the first three.
Small by design - it separates a model that works from one that does not and
shows the cost, it is not a ranking of embedding models in general.
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

FACTS = [
    # English
    "The user's favorite programming language is Python.",
    "The user lives in Istanbul and studies computer engineering.",
    "The user's laptop has an RTX 4060 with 8 GB of video memory.",
    "The user prefers answers in English but sometimes speaks Turkish.",
    "The user's operating systems exam is on the 14th of January.",
    "The user will study abroad for one semester next spring.",
    "The user's sister is called Elif and works as a nurse.",
    "The user does not like spicy food.",
    "The thesis project folder is called optik_otomasyon.",
    "The user goes to the library on weekdays to study.",
    # Turkish
    "Kullanıcının en sevdiği renk lacivert.",
    "Kullanıcı hafta sonları futbol oynuyor.",
    "Kullanıcının doğum günü 3 Mart.",
    "Kullanıcı pilden tasarruf etmek için ekran kartını kapatıp tümleşik ekran kartına geçiyor.",
    "Kullanıcının babası Ankara'da emekli öğretmen.",
    "Kullanıcı sabahları kahve yerine çay içiyor.",
    "Kullanıcının bitirme projesi sesli bir yapay zeka asistanı.",
    "Kullanıcı Polonya'da iş bulmak istiyor.",
    "Kullanıcının mobil veri paketi sınırlı.",
    "Kullanıcı gece geç saatlerde kod yazmayı seviyor.",
]

# (group, question, index of the one correct fact)
QUESTIONS = [
    ("same-language en", "What do I like to program in?", 0),
    ("same-language en", "Which city do I live in?", 1),
    ("same-language en", "How much graphics memory do I have?", 2),
    ("same-language en", "Which language should you answer me in?", 3),
    ("same-language en", "When is my operating systems test?", 4),
    ("same-language en", "Do I have plans to go to another country for school?", 5),
    ("same-language en", "What does my sister do for a living?", 6),
    ("same-language en", "Do I enjoy hot peppers?", 7),
    ("same-language en", "Where is my thesis stored?", 8),
    ("same-language en", "Where do I usually study during the week?", 9),
    ("same-language tr", "En sevdiğim renk hangisiydi?", 10),
    ("same-language tr", "Hafta sonu hangi sporu yaparım?", 11),
    ("same-language tr", "Doğum günüm ne zaman?", 12),
    ("same-language tr", "Bataryayı uzatmak için ne yapıyorum?", 13),
    ("same-language tr", "Babam ne iş yapıyordu?", 14),
    ("same-language tr", "Sabahları ne içerim?", 15),
    ("same-language tr", "Mezuniyet çalışmam ne hakkında?", 16),
    ("same-language tr", "Hangi ülkede iş arıyorum?", 17),
    ("same-language tr", "İnternet paketim nasıl?", 18),
    ("same-language tr", "Hangi saatlerde kod yazarım?", 19),
    ("en question, tr fact", "What is my favorite color?", 10),
    ("en question, tr fact", "Do I play any sports?", 11),
    ("en question, tr fact", "When is my birthday?", 12),
    ("en question, tr fact", "Where does my father live?", 14),
    ("en question, tr fact", "Do I have a limit on my phone data?", 18),
    ("tr question, en fact", "Hangi programlama dilini severim?", 0),
    ("tr question, en fact", "Nerede yaşıyorum?", 1),
    ("tr question, en fact", "Ekran kartımın belleği ne kadar?", 2),
    ("tr question, en fact", "Kız kardeşimin adı ne?", 6),
    ("tr question, en fact", "Acı yemeği sever miyim?", 7),
    ("tr question, en fact", "Haftanın günlerinde nerede ders çalışırım?", 9),
]

# Some embedding models are trained with task prefixes and perform worse
# without them; each is given the format its authors document.
PREFIXES = {
    "embeddinggemma": ("task: search result | query: ", "title: none | text: "),
}


def embed(model: str, texts: list[str]) -> np.ndarray:
    import ollama

    vectors = np.array(ollama.embed(model=model, input=texts)["embeddings"], dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def evaluate(model: str) -> dict:
    query_prefix, doc_prefix = PREFIXES.get(model.split(":")[0], ("", ""))
    texts_facts = [doc_prefix + f for f in FACTS]
    texts_questions = [query_prefix + q for _, q, _ in QUESTIONS]
    # The first call after a model is loaded measures loading and placement, not
    # the model (one run reported 737 ms per text; the next run, 11 ms). Run
    # the whole job once to warm up, then time it three times and keep the best.
    embed(model, texts_facts + texts_questions)
    timings = []
    for _ in range(3):
        t0 = time.perf_counter()
        facts = embed(model, texts_facts)
        questions = embed(model, texts_questions)
        timings.append((time.perf_counter() - t0) * 1000 / (len(FACTS) + len(QUESTIONS)))
    per_text_ms = min(timings)

    ranks = []
    for row, (_, _, correct) in zip(questions @ facts.T, QUESTIONS):
        order = np.argsort(-row)
        ranks.append(int(np.where(order == correct)[0][0]) + 1)

    groups: dict[str, list[int]] = {}
    for (group, _, _), rank in zip(QUESTIONS, ranks):
        groups.setdefault(group, []).append(rank)
    return {"model": model, "dim": facts.shape[1], "ms": per_text_ms, "ranks": ranks, "groups": groups}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=["bge-m3", "embeddinggemma"])
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args()

    results = [evaluate(m) for m in args.models]
    width = max(len(g) for g in results[0]["groups"])
    print(f"{'':{width}}  " + "  ".join(f"{r['model']:>22}" for r in results))
    for group in results[0]["groups"]:
        cells = []
        for r in results:
            ranks = r["groups"][group]
            cells.append(f"top1 {sum(x == 1 for x in ranks)}/{len(ranks)}  top3 {sum(x <= 3 for x in ranks)}/{len(ranks)}")
        print(f"{group:{width}}  " + "  ".join(f"{c:>22}" for c in cells))
    total = len(QUESTIONS)
    print(f"{'all':{width}}  " + "  ".join(
        f"{'top1 %d/%d  top3 %d/%d' % (sum(x == 1 for x in r['ranks']), total, sum(x <= 3 for x in r['ranks']), total):>22}"
        for r in results))
    print(f"{'ms per text':{width}}  " + "  ".join(f"{r['ms']:>22.1f}" for r in results))
    print(f"{'dimensions':{width}}  " + "  ".join(f"{r['dim']:>22}" for r in results))
    if args.show_misses:
        for r in results:
            print(f"\n{r['model']} - not ranked first:")
            for (group, question, correct), rank in zip(QUESTIONS, r["ranks"]):
                if rank > 1:
                    print(f"  rank {rank}  [{group}] {question}  -> expected: {FACTS[correct]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
