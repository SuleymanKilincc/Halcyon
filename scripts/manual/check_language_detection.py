"""
Manual check: language detection with langdetect, as used by the legacy GUI.

    python -m scripts.manual.check_language_detection

The sample sentences are mixed Turkish and English on purpose - they are the
data being classified.
"""

import sys

from langdetect import detect

SAMPLES = [
    "Merhaba, bugün nasılsın?",
    "Hello, how are you today?",
    "Bir dosya oluştur",
    "Create a file",
    "Workspace klasöründeki dosyaları listele",
    "List files in workspace",
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Language detection:\n")
    for sentence in SAMPLES:
        print(f"  {detect(sentence):>2}  {sentence}")


if __name__ == "__main__":
    main()
