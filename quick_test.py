"""Quick test - GUI ile Türkçe/İngilizce dil algılama testi"""
from langdetect import detect

test_sentences = [
    "Merhaba, bugün nasılsın?",
    "Hello, how are you today?",
    "Bir dosya oluştur",
    "Create a file",
    "Workspace klasöründeki dosyaları listele",
    "List files in workspace"
]

print("🌍 Dil Algılama Testi:\n")
for sentence in test_sentences:
    lang = detect(sentence)
    lang_name = "Türkçe 🇹🇷" if lang == "tr" else "İngilizce 🇬🇧"
    print(f"✓ '{sentence}'")
    print(f"  → Algılanan: {lang_name}\n")

print("\n✅ Dil algılama çalışıyor!")
print("\n💡 Not: Türkçe metinler algılanıyor,")
print("   sadece TTS sesi İngilizce olacak (David/Zira).")
print("\n🚀 GUI'yi başlatmak için: python gui.py")
