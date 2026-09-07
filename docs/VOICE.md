# Ses Hattı (Faz 1)

Tamamen yerel, akışkan (streaming) ve sözü kesilebilir bir konuşma hattı.
Eski hattın yerini alır.

## Neyin yerine geçti

| | Eski | Yeni |
|---|---|---|
| Tetikleme | Butona bas, 5 sn sabit dinle | Silero VAD — sen sustuğunda anlar |
| STT | `recognize_google` (**internete gidiyordu**) | faster-whisper, %100 yerel |
| TTS | pyttsx3 / SAPI5 | Piper (ONNX), Türkçe `tr_TR-dfki-medium` |
| Üretim | Tüm cevap üretilir, sonra seslendirilir | Cümle cümle: ilk cümle bitince ses başlar |
| Kesme | Yok | Var — üstüne konuşunca susar |

## Kullanım

Sadece ses hattını dene (LLM yok, duyduğunu tekrarlar):

```bash
python -m voice.cli
```

Ollama modeliyle konuş:

```bash
python -m voice.cli --llm
```

Ses aygıtlarını listele / seç:

```bash
python -m voice.cli --devices
```

```bash
python -m voice.cli --llm --input 1 --output 11
```

Gecikme ölçümü (mikrofon gerektirmez — Piper ile cümle üretip kendi hattından geçirir):

```bash
python -m bench.latency
```

```bash
python -m bench.latency --llm
```

## Ölçülen sonuçlar

Bu makinede (Ryzen 8 çekirdek / 16 iş parçacığı, **GPU devre dışı**, `base`
modeli, 8 iş parçacığı):

| Aşama | Süre |
|---|---|
| STT (2.6 sn'lik cümle) | ~500 ms |
| İlk cümlenin sentezi | ~90-115 ms |
| **Sen sustuktan ilk sese kadar (LLM hariç)** | **medyan 638 ms** |

Faz 1 hedefi 1500 ms'ti. LLM'siz hat hedefin çok altında.

LLM dahil edildiğinde tablo değişiyor — çünkü qwen3.5:9b şu an **CPU'da**
çalışıyor (12 token/sn, ilk token 2.8 sn):

| Aşama | Süre |
|---|---|
| İlk token | 4.0 - 20.8 sn |
| Toplam ilk ses | medyan 8.5 sn |

Yani ses hattı hazır, **darboğaz tamamen GPU'nun devre dışı olmasında.**

## GPU

`torch.cuda.is_available()` şu an `False`. Sebebi sürücü ya da torch değil:
Windows RTX 4060'ı hiç görmüyor.

```
NVIDIA GeForce RTX 4060 Laptop GPU
Status: Unknown | Present: False
"Currently, this hardware device is not connected to the computer. (Code 45)"
```

`Win32_VideoController` yalnızca AMD Radeon tümleşik grafikleri listeliyor.
NVIDIA sürücüleri, `nvcuda.dll` ve `nvml.dll` kurulu — eksik olan cihazın
kendisi. En olası sebep dizüstünde dGPU'nun kapatılmış olması (Armoury Crate
/ MyASUS'ta "Eco Mode" veya BIOS'ta dGPU devre dışı). Değiştirdikten sonra
**yeniden başlatmak gerekir.**

Düzeldiğinde yapılacak tek şey yok — kod zaten otomatik algılıyor:

* `voice/stt.py` cihazı `auto` çözümlüyor, CUDA görürse `large-v3-turbo`'ya
  kendiliğinden geçiyor (`int8_float16`, ~1.6 GB VRAM).
* Ollama da GPU'yu kendiliğinden kullanır.

Beklenen: STT ~500 ms → ~200 ms **ve** belirgin biçimde daha doğru Türkçe.

## Model seçimi: hız ve doğruluk

CPU'da, int8, 8 iş parçacığı. Doğruluk 4 cümlelik bir örneklemde
(3 Türkçe + 1 İngilizce) kelimesi kelimesine tam eşleşme sayısıdır:

| Model | Süre | Tam eşleşme | Not |
|---|---|---|---|
| `tiny` | 269 ms | — | Türkçe kullanılamaz |
| `base` | ~1000 ms | 1 / 4 | **CPU varsayılanı.** İngilizce kusursuz, Türkçe bozuk |
| `small` | ~3150 ms | 2 / 4 | Türkçe belirgin düzeliyor |
| `large-v3-turbo` | ~13400 ms | 3 / 4 | **Hedef model — GPU şart** |

Türkçede modeller arası fark somut:

```
base            "BİVİ SAYA RIM'ın sıcaklığı kaç derece?"
small           "Bilgisayarımın sıcaklığı kaç derece?"      TAM
large-v3-turbo  "Bilgisayarımın sıcaklığı kaç derece?"      TAM

base            "Masal üstündeki bütün Pitom Dostyalarını isteri."
small           "Masa üstündeki bütün piton dosyalarını ister."
large-v3-turbo  "Masa üstündeki bütün Python dosyalarının listeli."
```

Son satır önemli: `small` "Python"u fonetik olarak "piton" duyuyor,
`large-v3-turbo` terim olarak tanıyor. Kod yazan bir asistan için bu fark
büyük.

İngilizce her boyutta kusursuz — `base` bile 1/1 tam eşleşme veriyor.
Türkçe model boyutuna duyarlı, İngilizce değil.

> Ölçüm notu: girdi Piper ile sentezlenmiş konuşmadır, gerçek insan sesi
> değil. Whisper genelde gerçek konuşmada daha iyi sonuç verir, dolayısıyla
> bu tablo bir alt sınır sayılmalıdır. Ayrıca Türkçe metni **diakritikleriyle
> yazmak şarttır** — "Bugun" yazılırsa Piper "boo-goon" der ve ölçüm anlamsız
> hale gelir.

`voice/stt.py` CUDA yokken `large-v3-turbo` yerine `base`'e düşer ve bunu
**sebebiyle birlikte** ekrana yazar. Zorlamak için:

```bash
JARVIS_STT_MODEL=small python -m voice.cli --llm
```

## Kulaklık uyarısı

Akustik yankı bastırma (AEC) yok. Hoparlörle kullanırsan mikrofon Jarvis'in
kendi sesini duyar; bu yüzden kesme eşiği (`BargeInSettings.threshold = 0.85`)
bilerek yüksek tutuldu — yani hoparlörde kesme daha zor tetiklenir.
**Kulaklıkla eşiği düşürebilirsin** ve kesme çok daha hızlı tepki verir.

Sistemde Voicemeeter kurulu görünüyor; ileride gerçek bir AEC yönlendirmesi
için kullanılabilir.

## Modüller

| Dosya | Sorumluluk |
|---|---|
| `voice/settings.py` | Gecikmeyi etkileyen tüm ayarlar tek yerde |
| `voice/audio.py` | Mikrofon yakalama + kesilebilir oynatma |
| `voice/vad.py` | Uç noktalama ve kesme algılama (ayrı eşikler) |
| `voice/stt.py` | faster-whisper sarmalayıcı, cihaz/model çözümleme |
| `voice/tts.py` | Piper sarmalayıcı + cümle akışı ayrıştırıcı |
| `voice/pipeline.py` | Durum makinesi: dinle → çöz → üret → konuş |
| `voice/models.py` | Piper seslerini indirir/doğrular |
| `voice/cli.py` | Canlı terminal testi |
| `bench/latency.py` | Mikrofonsuz gecikme ölçümü |

## Çok dillilik

Dil algılama her konuşma için Whisper tarafından otomatik yapılır; sabit bir
dil ayarı yoktur. `voice/settings.py` içindeki `candidate_languages` algılamayı
`("tr", "en")` ile sınırlar — Whisper kısa cümlelerde bazen alakasız bir dil
tahmin eder, bu sınır onu engeller. Algılanan dile göre TTS sesi de otomatik
değişir.

Ölçüm: 4/4 doğru algılama, güven 0.96 - 1.00.

**Bilinen sınır:** tek cümle içinde dil karıştırmak (Türkçe cümle + İngilizce
terim, bir geliştiricinin doğal konuşması) desteklenmiyor. Whisper cümle
başına tek bir dil seçer, TTS de cümlenin tamamını o dilin sesiyle okur —
Türkçe ses İngilizce kelimeleri okuduğunda kulağa kötü gelir. Cümle bazında
dil değiştirmek sorunsuz çalışır.

## Henüz yapılmadı

* Uyandırma sözcüğü ("Hey Jarvis") — Faz 5
* GUI entegrasyonu — Faz 2 (`gui.py` hâlâ eski hattı kullanıyor)
* Akustik yankı bastırma
* Konuşmacı tanıma
* Cümle içi dil karışımı (code-switching)
