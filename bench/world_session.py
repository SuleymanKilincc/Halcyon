"""
Does a model know its films and games, and keep a made-up world consistent? Used to choose deep mode's models.

    python -m bench.world_session --language tr gemma4:26b-a4b qwen3.5:9b
    python -m bench.world_session --language en gemma4:e4b

Two parts, both through the Ollama HTTP API:

1. **Knowledge probes.** Six questions about films, games and books whose answers are well known
   (the last one is deliberately obscure, so an honest "I am not sure" is a good answer). A small
   model that invents a plausible name is the failure this catches.
2. **A world session.** The first message plants rules (a world where metal burns the skin, always
   dusk) and three characters with one fixed trait each (a mute cartographer, a ferryman afraid of
   water, a captain with one hand and a glass sword). Five turns then pull on those facts: a coin
   (metal) is offered, a weapon is drawn, an iron key is picked up, and the last turn asks for a summary.

Nothing here is scored automatically. Judging "did the world stay consistent" with keyword rules
would be a guess, so every reply is printed with its speed and the rules to look for, and the
verdict in docs/MODES.md is a person's reading of them: the facts that must hold are listed in
RULES below, and a turn that breaks one counts as a break. One run per model and a fixed seed, so
two models can be set side by side; it cannot say how a model behaves over hours.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434"

# (question, what a correct answer contains). The wording of each language is the test data.
PROBES = {
    "en": [
        ("Who directed the film Blade Runner (1982), and who played Deckard?", "Ridley Scott; Harrison Ford"),
        ("In The Witcher 3, who is Geralt's mentor at Kaer Morhen?", "Vesemir"),
        ("In Frank Herbert's Dune, what is the name of Paul Atreides' mother and what order does she belong to?",
         "Lady Jessica; Bene Gesserit"),
        ("In Elden Ring, what is the name of the final boss form that appears after Radagon?", "Elden Beast"),
        ("In the film Inception, what object does Cobb spin to test whether he is dreaming?", "a spinning top (totem)"),
        ("Dark Souls: what is the name of the first bell-ringing area boss in Undead Burg's region, below the "
         "Taurus Demon? Answer briefly, or say you are unsure.", "obscure: Capra Demon (Lower Undead Burg); honest doubt is fine"),
    ],
    "tr": [
        ("Blade Runner (1982) filmini kim yönetti ve Deckard karakterini kim oynadı?", "Ridley Scott; Harrison Ford"),
        ("The Witcher 3'te Geralt'ın Kaer Morhen'deki akıl hocası kim?", "Vesemir"),
        ("Frank Herbert'in Dune romanında Paul Atreides'in annesinin adı ne ve hangi tarikata ait?",
         "Lady Jessica; Bene Gesserit"),
        ("Elden Ring'de Radagon'dan sonra gelen son boss formunun adı nedir?", "Elden Beast"),
        ("Inception filminde Cobb rüyada olup olmadığını anlamak için hangi nesneyi döndürür?", "topaç"),
        ("Kırmızı Başlıklı Kız masalını yazan Charles Perrault'nun ülkesi neresi? Emin değilsen söyle.", "Fransa"),
    ],
}

WORLD = {
    "en": (
        "You are the game master of a text adventure. Stay strictly consistent with these facts; never contradict them.\n\n"
        "WORLD: The island of Verrath. Metal does not exist here: iron and steel burn the skin of anyone who touches "
        "them, so people use bone, glass and obsidian. It is always dusk.\nCHARACTERS:\n"
        "- Mira, a young cartographer. She is MUTE and communicates only by gestures and drawing in the sand.\n"
        "- Old Tomas, the ferryman, loud and superstitious, who is afraid of the water.\n"
        "- Captain Halle, a retired soldier with a glass sword and a missing left hand. A woman.\n"
        "Write 3-5 sentences per turn, describe what happens, and voice every character present who would act."),
    "tr": (
        "Sen bir metin macerasının oyun yöneticisisin. Aşağıdaki gerçeklere kesinlikle sadık kal, asla çelişme.\n\n"
        "DÜNYA: Verrath adası. Burada metal yoktur: demir ve çelik, dokunan herkesin cildini yakar; insanlar kemik, "
        "cam ve obsidyen kullanır. Hava her zaman alacakaranlıktır.\nKARAKTERLER:\n"
        "- Mira, genç bir haritacı. DİLSİZDİR, yalnızca jestlerle ve kuma çizerek anlaşır.\n"
        "- Yaşlı Tomas, gürültücü ve batıl inançlı kayıkçı, sudan korkar.\n"
        "- Yüzbaşı Halle, emekli bir asker; cam kılıcı var, sol eli yok. Kadındır.\n"
        "Her tur 3-5 cümle yaz, olanı anlat, sahnedeki ve harekete geçecek her karakteri konuştur. Türkçe yaz."),
}

TURNS = {
    "en": [
        "I arrive at the dock and greet everyone. I ask Mira what she is drawing.",
        "I offer Tomas a coin to take us across the water to the northern shore.",
        "Something moves in the fog and Captain Halle draws her weapon. What does she do and what does Mira do?",
        "I find an old iron key lying on the dock. I pick it up and put it in my pocket.",
        "Summarise, in a short list, the rules of this world and what each of the three characters is like, "
        "from what has happened.",
    ],
    "tr": [
        "İskeleye varıyorum, herkesi selamlıyorum. Mira'ya ne çizdiğini soruyorum.",
        "Tomas'a kuzey kıyısına geçirmesi için bir madeni para uzatıyorum.",
        "Sisin içinde bir şey kıpırdıyor, Yüzbaşı Halle silahını çekiyor. Halle ne yapıyor, Mira ne yapıyor?",
        "İskelede yatan eski bir demir anahtar buluyorum, alıp cebime koyuyorum.",
        "Bu dünyanın kurallarını ve üç karakterin nasıl biri olduğunu, olanlardan yola çıkarak kısa bir liste "
        "halinde özetle.",
    ],
}

# What the reader checks each reply against. A reply that breaks one of these counts as a break.
RULES = (
    "Mira never speaks aloud (gestures and sand drawings only)",
    "metal burns: the coin and the iron key are refused or hurt, never handled harmlessly",
    "Tomas is afraid of the water",
    "Halle has one hand (the left is missing), a glass sword, and is a woman",
    "it is always dusk",
)


def _post(path: str, body: dict, timeout: int = 1800) -> dict:
    request = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _chat(model: str, messages: list[dict], capabilities: list[str], num_predict: int) -> tuple[str, int, float, float, float]:
    body = {"model": model, "stream": False, "keep_alive": "10m", "messages": messages,
            "options": {"temperature": 0.7, "seed": 11, "num_predict": num_predict, "num_ctx": 4096}}
    if "thinking" in capabilities:
        body["think"] = False
    started = time.perf_counter()
    result = _post("/api/chat", body)
    wall = time.perf_counter() - started
    tokens, seconds = result.get("eval_count", 0), result.get("eval_duration", 1) / 1e9
    return result["message"]["content"].strip(), tokens, tokens / seconds, result.get("load_duration", 0) / 1e9, wall


def _unload(model: str) -> None:
    try:
        _post("/api/generate", {"model": model, "keep_alive": 0}, 60)
    except Exception:  # noqa: BLE001
        pass


def run(model: str, language: str) -> None:
    try:
        capabilities = _post("/api/show", {"model": model}, 30).get("capabilities", [])
    except Exception:  # noqa: BLE001
        capabilities = []
    print(f"\n########## {model}  language={language}  capabilities={capabilities}", flush=True)
    _unload(model)

    print("\n--- knowledge probes", flush=True)
    for question, expected in PROBES[language]:
        answer, tokens, speed, load, wall = _chat(model, [{"role": "user", "content": question}], capabilities, 200)
        print(f"Q: {question}\n   expected: {expected}\n   [{tokens} tok, {speed:.1f} tok/s, load {load:.1f}s, "
              f"wall {wall:.1f}s]\n   A: {answer[:420]}", flush=True)

    print("\n--- world session (read each reply against these rules)", flush=True)
    for rule in RULES:
        print(f"   * {rule}")
    history = [{"role": "system", "content": WORLD[language]}]
    for turn in TURNS[language]:
        history.append({"role": "user", "content": turn})
        reply, tokens, speed, _, wall = _chat(model, history, capabilities, 450)
        history.append({"role": "assistant", "content": reply})
        print(f"\nPLAYER: {turn}\n   [{tokens} tok, {speed:.1f} tok/s, wall {wall:.1f}s]\nGM: {reply}", flush=True)

    placement = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout.strip().splitlines()
    print("\nplacement:", placement[1] if len(placement) > 1 else "(not loaded)", flush=True)
    _unload(model)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+", help="Ollama model names")
    parser.add_argument("--language", choices=sorted(PROBES), default="en")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for model in args.models:
        run(model, args.language)
    return 0


if __name__ == "__main__":
    sys.exit(main())
