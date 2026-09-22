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

LLM dahil edildiğinde darboğaz dil modeline kayıyor — GPU kapalı olduğu için
her şey CPU'da. Pil profilinin (`qwen3.5:2b`) ölçülen sayıları aşağıdaki
[Profiller](#profiller-pil--tam-güç) bölümünde.

> Bu bölümde daha önce çok daha kötü sayılar yazıyordu (ilk token 4-20 sn,
> toplam 8.5 sn). Onlar ölçüm aracının kendi artefaktıydı: benchmark her turda
> LLM akışını yarıda bırakıyordu, sunucu üretmeye devam ediyordu ve bir
> sonraki tur o kuyruğun arkasında bekliyordu. Düzeltildikten sonra aynı
> donanımda ilk token 4-20 sn değil, ~1-1.6 sn. Ayrıntı: "Yarıda kesilen
> üretimin bedeli".

Ses hattının kendisi (STT + VAD + TTS) her koşulda hazır ve hızlı;
**GPU açıldığında kazanılacak yer dil modeli ve Türkçe doğruluğu.**

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
kendisi.

**Sebep bir arıza değil, bilinçli bir ayar:** dizüstü, pil ömrü için
**G-Helper üzerinden iGPU (Eco) moduna** alınmış. Bu modda dGPU PCI
veriyolundan tamamen ayrılır, dolayısıyla Kod 45 beklenen davranıştır.

GPU'yu kullanmak için G-Helper'da **Standard** (veya Optimus/Auto) moda geçip
**yeniden başlatmak** gerekir; şarja takılı olmak da önerilir.

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

## Profiller (pil / tam güç)

Dizüstü, dGPU açık mı kapalı mı olduğuna göre iki farklı makine. Sistem
başlangıçta donanımı algılayıp tutarlı bir model seti seçiyor — bileşenlerin
tek tek bozulmasını beklemiyor.

| | `battery` | `performance` |
|---|---|---|
| Ne zaman | CUDA yok (iGPU / Eco mod) | dGPU açık, VRAM ≥ 7 GB |
| STT | `base` @ CPU | `large-v3-turbo` @ CUDA |
| LLM | `qwen3.5:2b`, ctx 4096 | `qwen3.5:9b`, ctx 8192 |
| Beklenen ilk ses | ~2800 ms | **~1400 ms (ölçüldü)** |

### Tam güç modunda ölçülen (RTX 4060, ısınmış)

| Aşama | Süre |
|---|---|
| STT (`large-v3-turbo` @ CUDA) | 234 - 377 ms |
| LLM ilk token | 114 - 134 ms |
| **Toplam ilk ses** | **1105 - 1573 ms** |

Türkçe doğruluğu da beklendiği gibi düzeldi: "Sistem sıcaklığı nedir?"
kelimesi kelimesine doğru çıkıyor — CPU'daki `base` modeli aynı cümleyi
"BİVİ SAYA RIM'ın sıcaklığı kaç derece?" diye duyuyordu.

### VRAM: context boyutu modelin nereye yükleneceğini belirliyor

8 GB VRAM'de `qwen3.5:9b` için `ollama ps` ile ölçülen:

| ctx | Yerleşim |
|---|---|
| 8192 | **%100 GPU** |
| 12288 | %86 GPU / %14 CPU |
| 16384 | %84 GPU / %16 CPU |

En ufak taşma bile bazı katmanları CPU'ya atıyor ve üretimin tamamını CPU
hızına çekiyor. Bu yüzden VRAM'e tam sığan küçük context, sığmayan büyük
context'i yener. Profil 8192'ye sabitlendi.

Ara bir profil daha var: `performance-lowvram` — dGPU var ama 7 GB'ın altında
VRAM varsa hızlı STT'yi tutup LLM'i `qwen3.5:4b`'ye düşürüyor.

Ne çalıştığını görmek için:

```bash
python -m voice.cli --info
```

Elle seçmek için (`--profile` veya `JARVIS_PROFILE`):

```bash
python -m voice.cli --llm --profile battery
```

Profil seçimi **kendini açıklıyor** — dGPU kapalıysa sebebini ve çözümünü
yazıyor, sessizce küçük modele düşmüyor.

### Pil modunda ölçülen (GPU kapalı, `qwen3.5:2b`)

| Aşama | Süre |
|---|---|
| STT | ~500 ms |
| LLM ilk token (ısınmış, yeni prompt) | ~1000 ms |
| İlk cümlenin sentezi | ~340 ms |
| **Toplam ilk ses** | **en iyi 1814 ms, medyan ~3600 ms** |

`qwen3.5:4b` ile aynı ölçüm ~1600 ms ilk token veriyor; pil modunda 2b tercih
edildi çünkü sesli turda hız doğruluktan değerli. Doğruluk isteyen
`--model qwen3.5:4b` diyebilir.

### Yarıda kesilen üretimin bedeli

Ollama yüklü model başına istekleri sıraya alıyor. İstemci okumayı bırakınca
sunucu `num_predict`'e kadar üretmeye devam ediyor ve **sonraki istek onun
arkasında bekliyor**: ölçülen fark, ısınmış ve yeni bir prompt'ta

```
akış sonuna kadar tüketildi      ~1000-1600 ms
akış ilk token'dan sonra bırakıldı  ~2200-2350 ms
```

`.close()` bunu engellemiyor (iki istemcide de denendi). Bu yüzden profillerde
`num_predict` küçük tutuldu ve erken çıkan çağrılar kalanı boşaltıyor. Tek
boşaltamayan yer sözü kesme — orada ceza bir sonraki tura biniyor ve kullanıcı
zaten konuştuğu için kısmen gizleniyor. GPU'da üretim birkaç kat hızlı olduğu
için oransal olarak küçülüyor.

> Ölçüm tuzağı: aynı prompt'u tekrarlamak Ollama'nın KV önbelleğine düşüyor ve
> ~120 ms gösteriyor. Gerçek bir turda görülmeyecek bir sayı — her zaman yeni
> prompt'la ölçün.

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
