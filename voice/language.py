"""
Which language is this sentence in - Turkish or English?

Used to choose the voice that reads each sentence of a reply. The voice used to
follow the language Whisper detected in the *user's* speech, and that label is
unreliable on short utterances: an English "Hi Jarvis, how are you?" spoken
with a Turkish accent was labelled Turkish, so the correct English reply was
read out by the Turkish voice. What should decide the voice is the language of
the text being spoken, which is known exactly.

Only two languages are possible, so a small transparent scorer is enough:
Turkish-specific letters and frequent function words on each side. It is
measured against labelled sentences in tests/test_language.py.
"""

from __future__ import annotations

import re

_TURKISH_LETTERS = set("çğıöşüÇĞİÖŞÜ")

# Frequent short words that are very unlikely in the other language: function
# words, plus the acknowledgements and greetings assistant replies are made of
# ("Done.", "Tamam."). Content words are left out; they would make the lists
# open-ended.
_TR_WORDS = frozenset("""
    ve bir bu şu o için ile de da ki mi mı mu mü ne ben sen biz siz onlar
    var yok değil çok daha en gibi kadar sonra önce şimdi evet hayır tamam
    efendim lütfen teşekkür ederim nasıl neden nerede hangi kaç her hiç
    olarak olan oldu olur ama fakat veya ya ise eğer bunu şunu onu bana sana
    size içinde üzerinde altında misin musun mısınız ister istiyorum yapabilirim
    yapamam edemem göster aç kapat listele bul
    merhaba selam peki tabii hemen
""".split())

_EN_WORDS = frozenset("""
    the a an and or but if is are was were be been am do does did have has had
    i you he she it we they me my your our their this that these those there
    to of in on at for with from by about as into than then so not no yes
    can could would should will shall may might must sir please thank thanks
    what which who how why where when here all any some more most very just
    done sure sorry hello hi okay right
""".split())

_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")


def guess_language(text: str, fallback: str = "en") -> str:
    """Return "tr" or "en" for `text`; `fallback` when there is no evidence either way."""
    words = _WORD.findall(text)
    if not words:
        return fallback

    # Turkish casing differs (I -> ı, İ -> i), so each side gets its own lowercase.
    tr_words = [w.replace("I", "ı").replace("İ", "i").lower() for w in words]
    en_words = [w.lower() for w in words]

    tr_score = sum(w in _TR_WORDS for w in tr_words)
    # A word spelled with Turkish letters is Turkish evidence, counted once per
    # word, so a single Turkish name inside an English sentence ("Hello
    # Süleyman, how are you?") is outweighed by the English around it.
    tr_score += sum(any(ch in _TURKISH_LETTERS for ch in w) for w in words)
    en_score = sum(w in _EN_WORDS for w in en_words)

    if tr_score > en_score:
        return "tr"
    if en_score > tr_score:
        return "en"
    return fallback
