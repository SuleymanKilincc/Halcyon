"""
Jarvis sistem raporu - PDF uretici.

    python docs/build_report.py docs/Jarvis_Sistem_Raporu.pdf

Gereken: reportlab (pip install reportlab) ve Windows'un Calibri/Consolas
fontlari (Turkce karakterler icin). Rapordaki sayilar elle girilmistir;
olcumler degistikce burada da guncellenmelidir.
"""

import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from reportlab.lib.fonts import addMapping

OUT = Path(sys.argv[1])

# ------------------------------------------------------------------ fontlar
F = "C:/Windows/Fonts/"
pdfmetrics.registerFont(TTFont("Calibri", F + "calibri.ttf"))
pdfmetrics.registerFont(TTFont("Calibri-Bold", F + "calibrib.ttf"))
pdfmetrics.registerFont(TTFont("Calibri-Italic", F + "calibrii.ttf"))
pdfmetrics.registerFont(TTFont("Calibri-BoldItalic", F + "calibriz.ttf"))
pdfmetrics.registerFont(TTFont("Consolas", F + "consola.ttf"))
addMapping("Calibri", 0, 0, "Calibri")
addMapping("Calibri", 1, 0, "Calibri-Bold")
addMapping("Calibri", 0, 1, "Calibri-Italic")
addMapping("Calibri", 1, 1, "Calibri-BoldItalic")

# ------------------------------------------------------------------ renkler
INK = colors.HexColor("#1B2430")
MUTED = colors.HexColor("#5B6B7C")
NAVY = colors.HexColor("#1F3A5F")
ACCENT = colors.HexColor("#0E7490")
ACCENT_SOFT = colors.HexColor("#E3F2F6")
HEAD_BG = colors.HexColor("#E9EEF4")
RULE = colors.HexColor("#C9D3DD")
WARN_SOFT = colors.HexColor("#FDF3E7")
WARN = colors.HexColor("#B45309")
GOOD_SOFT = colors.HexColor("#EAF6EE")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
FRAME_W = PAGE_W - 2 * MARGIN

# ------------------------------------------------------------------ stiller
def st(name, **kw):
    base = dict(fontName="Calibri", fontSize=10.5, leading=14.5, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)

S = {
    "title": st("title", fontName="Calibri-Bold", fontSize=34, leading=38, textColor=NAVY),
    "subtitle": st("subtitle", fontSize=15, leading=19, textColor=ACCENT),
    "meta": st("meta", fontSize=9.5, leading=13, textColor=MUTED),
    "h1": st("h1", fontName="Calibri-Bold", fontSize=17, leading=21, textColor=NAVY,
             spaceBefore=16, spaceAfter=7, keepWithNext=1),
    "h2": st("h2", fontName="Calibri-Bold", fontSize=12.5, leading=16, textColor=ACCENT,
             spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "body": st("body", spaceAfter=6, allowWidows=0, allowOrphans=0),
    "bullet": st("bullet", leftIndent=13, bulletIndent=2, spaceAfter=2.5, allowWidows=0, allowOrphans=0),
    "cell": st("cell", fontSize=9.5, leading=12.5),
    "cellb": st("cellb", fontName="Calibri-Bold", fontSize=9.5, leading=12.5),
    "head": st("head", fontName="Calibri-Bold", fontSize=9.5, leading=12.5, textColor=NAVY),
    "code": st("code", fontName="Consolas", fontSize=8.6, leading=11.5, textColor=INK),
    "quote": st("quote", fontSize=10, leading=14, textColor=INK),
    "small": st("small", fontSize=8.5, leading=11, textColor=MUTED),
    "tile_big": st("tile_big", fontName="Calibri-Bold", fontSize=16, leading=19,
                   textColor=NAVY, alignment=TA_CENTER),
    "tile_small": st("tile_small", fontSize=8.5, leading=11, textColor=MUTED,
                     alignment=TA_CENTER),
}


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def P(text, style="body"):
    return Paragraph(text, S[style])


def B(text):
    return Paragraph(text, S["bullet"], bulletText="•")


def code(text):
    return f'<font name="Consolas" size="9">{esc(text)}</font>'


def table(rows, widths, header=True, zebra=False, bold_first_col=False):
    data = []
    for r_i, row in enumerate(rows):
        out = []
        for c_i, cell in enumerate(row):
            if isinstance(cell, str):
                if header and r_i == 0:
                    style = "head"
                elif bold_first_col and c_i == 0:
                    style = "cellb"
                else:
                    style = "cell"
                cell = Paragraph(cell, S[style])
            out.append(cell)
        data.append(out)
    total = sum(widths)
    widths = [w * FRAME_W / total for w in widths]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                 ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY)]
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if i % 2 == 0:
                cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F7F9FB")))
    t.setStyle(TableStyle(cmds))
    return t


def callout(flowables, bg=ACCENT_SOFT, edge=ACCENT):
    t = Table([[flowables]], colWidths=[FRAME_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def keep(*items):
    return KeepTogether(list(items))


def tiles(items):
    cells = [[Paragraph(big, S["tile_big"]), Spacer(1, 2), Paragraph(small, S["tile_small"])]
             for big, small in items]
    w = FRAME_W / len(items)
    t = Table([cells], colWidths=[w] * len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
        ("LINEAFTER", (0, 0), (-2, -1), 2, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


# ------------------------------------------------------------------ diyagramlar
def _box(d, x, y, w, h, title, sub=None, fill=colors.white, stroke=NAVY, bold=True):
    d.add(Rect(x, y, w, h, rx=5, ry=5, fillColor=fill, strokeColor=stroke, strokeWidth=0.9))
    if sub:
        d.add(String(x + w / 2, y + h - 12.5, title, fontName="Calibri-Bold" if bold else "Calibri",
                     fontSize=9.5, fillColor=INK, textAnchor="middle"))
        d.add(String(x + w / 2, y + 5.5, sub, fontName="Calibri", fontSize=7.8,
                     fillColor=MUTED, textAnchor="middle"))
    else:
        d.add(String(x + w / 2, y + h / 2 - 3.2, title, fontName="Calibri-Bold" if bold else "Calibri",
                     fontSize=9.2, fillColor=INK, textAnchor="middle"))


def _arrow(d, x1, y1, x2, y2, color=NAVY, dash=None, head=True):
    ln = Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=1)
    if dash:
        ln.strokeDashArray = dash
    d.add(ln)
    if not head:
        return
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    s = 5
    p1 = (x2 - s * math.cos(ang - 0.45), y2 - s * math.sin(ang - 0.45))
    p2 = (x2 - s * math.cos(ang + 0.45), y2 - s * math.sin(ang + 0.45))
    d.add(Polygon([x2, y2, p1[0], p1[1], p2[0], p2[1]], fillColor=color, strokeColor=color))


def _label(d, x, y, text, color=MUTED, size=7.8, anchor="middle"):
    d.add(String(x, y, text, fontName="Calibri-Italic", fontSize=size, fillColor=color,
                 textAnchor=anchor))


def pipeline_diagram():
    W, H = FRAME_W, 282
    d = Drawing(W, H)
    bw, bh, gap = 190, 28, 11
    x = (W - bw) / 2 - 15
    steps = [
        ("Mikrofon", "16 kHz, 32 ms'lik kareler"),
        ("Silero VAD", "konuşma ne zaman başladı / bitti"),
        ("faster-whisper (STT)", "ses → metin + dil (tr / en)"),
        ("qwen3.5 @ Ollama (LLM)", "cevap kelime kelime akar"),
        ("Cümle ayırıcı", "ilk cümle hazır olunca bırakır"),
        ("Piper (TTS)", "metin → ses"),
        ("Hoparlör", None),
    ]
    ys = []
    y = H - 6 - bh
    for title, sub in steps:
        fill = ACCENT_SOFT if title.startswith("qwen") else colors.white
        _box(d, x, y, bw, bh, title, sub, fill=fill)
        ys.append(y)
        y -= bh + gap
    for i in range(len(ys) - 1):
        _arrow(d, x + bw / 2, ys[i], x + bw / 2, ys[i + 1] + bh)

    # sag taraf: prewarm, araclar, hafiza
    sx, sw = x + bw + 38, 150
    vad_y, llm_y = ys[1], ys[3]
    _box(d, sx, vad_y, sw, bh, "GPU ön-ısıtma", "konuşma başlar başlamaz", fill=GOOD_SOFT,
         stroke=colors.HexColor("#3E8E5E"))
    _arrow(d, x + bw, vad_y + bh / 2, sx, vad_y + bh / 2, color=colors.HexColor("#3E8E5E"))
    _box(d, sx, llm_y + 6, sw, 30, "Araçlar", "listele, sıcaklık, web", fill=colors.white)
    _box(d, sx, llm_y - 30, sw, 30, "Hafıza", "son 8 tur", fill=colors.white)
    _arrow(d, x + bw, llm_y + 24, sx, llm_y + 26)
    _arrow(d, sx, llm_y + 16, x + bw, llm_y + 16)
    _arrow(d, x + bw, llm_y + 6, sx, llm_y - 15)

    # sol taraf: soz kesme
    lx = x - 34
    vad_mid = ys[1] + bh / 2
    spk_mid = ys[6] + bh / 2
    _arrow(d, x, vad_mid, lx, vad_mid, color=WARN, dash=[3, 2], head=False)
    _arrow(d, lx, vad_mid, lx, spk_mid, color=WARN, dash=[3, 2], head=False)
    _arrow(d, lx, spk_mid, x, spk_mid, color=WARN, dash=[3, 2])
    _label(d, lx - 6, (vad_mid + spk_mid) / 2 + 6, "söz kesme:", color=WARN, anchor="end")
    _label(d, lx - 6, (vad_mid + spk_mid) / 2 - 5, "sen konuşursan", color=WARN, anchor="end")
    _label(d, lx - 6, (vad_mid + spk_mid) / 2 - 16, "oynatma durur", color=WARN, anchor="end")
    return d


def profile_diagram():
    W, H = FRAME_W, 182
    d = Drawing(W, H)
    G = colors.HexColor("#3E8E5E")
    _box(d, 0, 70, 68, 30, "Jarvis açılır", None, fill=HEAD_BG)
    _box(d, 86, 70, 104, 30, "CUDA var mı?", "PyTorch'a sorulur")
    _box(d, 214, 120, 100, 30, "VRAM ≥ 7 GB?", None)
    _box(d, 214, 18, 100, 30, "Kapalı dGPU var mı?", "Get-PnpDevice")
    rx = 344
    rw = W - rx
    _box(d, rx, 148, rw, 30, "performance", "large-v3-turbo + qwen3.5:9b", fill=GOOD_SOFT, stroke=G)
    _box(d, rx, 108, rw, 30, "performance-lowvram", "large-v3-turbo + qwen3.5:4b", fill=GOOD_SOFT, stroke=G)
    _box(d, rx, 40, rw, 30, "battery + uyarı", "\"G-Helper'da Standard moda geç\"", fill=WARN_SOFT, stroke=WARN)
    _box(d, rx, 2, rw, 30, "battery", "Whisper base + qwen3.5:2b (CPU)", fill=WARN_SOFT, stroke=WARN)
    _arrow(d, 68, 85, 86, 85)
    _arrow(d, 190, 92, 214, 135); _label(d, 199, 118, "evet", anchor="end")
    _arrow(d, 190, 78, 214, 33); _label(d, 201, 46, "hayır", anchor="end")
    _arrow(d, 314, 140, rx, 163); _label(d, 326, 158, "evet")
    _arrow(d, 314, 130, rx, 123); _label(d, 329, 117, "hayır")
    _arrow(d, 314, 38, rx, 55); _label(d, 326, 52, "evet")
    _arrow(d, 314, 28, rx, 17); _label(d, 329, 13, "hayır")
    return d


# ------------------------------------------------------------------ sayfa sablonu
def on_page(canvas, doc):
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont("Calibri", 8.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, PAGE_H - 12 * mm, "Jarvis · Sistem Tasarımı ve Proje Raporu")
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 12 * mm, "10 Ekim 2026")
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, PAGE_H - 13.5 * mm, PAGE_W - MARGIN, PAGE_H - 13.5 * mm)
    canvas.setFont("Calibri", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(PAGE_W / 2, 10 * mm, str(doc.page))
    canvas.restoreState()


# ------------------------------------------------------------------ icerik
story = []
add = story.append

# --- kapak blogu
add(Spacer(1, 18 * mm))
add(P("Jarvis", "title"))
add(Spacer(1, 4))
add(P("Yerel çalışan, sesli yapay zeka asistanı", "subtitle"))
add(Spacer(1, 2))
add(P("Sistem Tasarımı ve Proje Durum Raporu", "subtitle"))
add(Spacer(1, 10))
add(P("10 Ekim 2026  ·  Sürüm <b>091ccad</b>  ·  github.com/SuleymanKilincc/Jarvis (private)",
      "meta"))
add(Spacer(1, 14))
add(tiles([
    ("1,1–1,6 sn", "sen sustuktan ilk sese<br/>(GPU, ölçüldü)"),
    ("234–377 ms", "ses tanıma<br/>(large-v3-turbo, GPU)"),
    ("114–134 ms", "ilk kelimenin üretimi<br/>(qwen3.5:9b)"),
    ("%100 yerel", "konuşma internete<br/>gitmiyor"),
]))
add(Spacer(1, 14))

add(P("1. Özet", "h1"))
add(P("<b>Çalışan:</b> Tamamen bilgisayarın üzerinde çalışan, Türkçe ve İngilizce konuşabilen, "
      "sözü kesilebilen bir sesli asistan. Masaüstündeki dosyaları listeleyebiliyor, sistem "
      "sıcaklığını okuyabiliyor, internette arama yapabiliyor ve son 8 turu hatırlıyor. "
      "Bilgisayar şarjdayken ekran kartını (GPU), pildeyken işlemciyi (CPU) kendiliğinden kullanıyor."))
add(P("<b>Eksik:</b> README eski sistemi anlatıyor; testlerin hiçbiri hata yakalayamıyor; Iron Man "
      "arayüzü (GUI) hâlâ eski ses sistemine bağlı; dosya yazma, silme ve terminal komutları "
      "sesle bilerek kapalı (onay katmanını bekliyor); sesli konuşmalar kaydedilmiyor."))
add(P("<b>Sıradaki:</b> Önce projenin vitrinini düzeltmek (README, gerçek testler, otomatik "
      "test hattı), ardından en görünür iki özellik: <i>“Hey Jarvis”</i> uyandırma kelimesi ve ekranı görme."))

# --- kronoloji
add(P("2. Bu zamana kadar ne yapıldı", "h1"))
add(table([
    ["Aşama", "Ne oldu"],
    ["Başlangıç", "19 markdown dosyalı bir proje devralındı. Dokümanlar “yerel Whisper, yerel TTS, "
     "sandbox” diyordu; çalıştırılıp kontrol edildiğinde üçü de kapalı çıktı. Ses tanıma aslında "
     "Google'ın sunucusuna gidiyordu."],
    ["Faz 0 – Zemin", "Git kuruldu (proje hiç versiyonlanmamıştı), GitHub'da private repo açıldı. "
     "CUDA destekli PyTorch kuruldu. Dokümanlar düzenlendi, bağımlılık listesi gerçeğe çekildi."],
    ["Faz 1 – Ses hattı", "Ses sistemi sıfırdan yazıldı: yerel ses tanıma (faster-whisper), konuşma "
     "algılama (Silero VAD), yerel ses sentezi (Piper), cümle cümle konuşma, söz kesme."],
    ["GPU sorunu", "RTX 4060 sistemde hiç görünmüyordu. Sebep arıza değil, G-Helper'ın Eco "
     "(yalnız iGPU) moduydu. Windows kartı “Kod 45: bağlı değil” olarak raporluyordu."],
    ["Profiller", "Pil ve GPU için iki ayrı model seti tanımlandı; donanım açılışta algılanıp doğru "
     "set otomatik seçiliyor."],
    ["GPU ayarı", "Bağlam (context) penceresi 16.384'ten 8.192'ye indirildi: model artık 8 GB "
     "ekran belleğine tam sığıyor ve tamamen GPU'da çalışıyor."],
    ["Son tur", "Araç çağırma, konuşma hafızası, “efendim” diyen Jarvis kişiliği ve boşta uyuyan "
     "GPU'yu önceden uyandırma eklendi."],
], [1.1, 4.2], bold_first_col=True))
add(Spacer(1, 4))
add(P("Toplam 9 commit, yaklaşık 5.900 satır Python. Tüm değişiklikler GitHub'da.", "small"))

# --- yerel model
add(P("3. Yerel yapay zeka modeli nedir?", "h1"))
add(P("ChatGPT, Claude veya Gemini gibi modeller şirketlerin sunucularında çalışır: yazdığın metin "
      "internet üzerinden onlara gider, cevap geri gelir. <b>Yerel model</b> ise aynı türden bir "
      "programın senin bilgisayarında çalışan halidir. Modelin “bilgisi”, milyarlarca sayıdan "
      "(parametre) oluşan tek bir dosyadır. Jarvis'in tam güç modundaki modeli "
      f"{code('qwen3.5:9b')}:"))
add(table([
    ["Özellik", "Değer", "Anlamı"],
    ["Parametre sayısı", "9,7 milyar", "Modelin “beyin” büyüklüğü"],
    ["Dosya boyutu", "~6,6 GB", "Diskte ve ekran belleğinde kapladığı yer"],
    ["Sıkıştırma", "Q4_K_M", "Her sayı 16 bit yerine yaklaşık 4 bitle saklanıyor. Sıkıştırmasız "
     "hali ~19 GB olurdu; kalite kaybı küçük."],
    ["Yetenekler", "metin, görme, araç, düşünme", "Ollama'nın model bilgisiyle doğrulandı"],
    ["Desteklenen bağlam", "262.144 token", "Teorik üst sınır. Pratikte 8 GB bellek yüzünden 8.192 "
     "kullanılıyor."],
], [1.3, 1.5, 3.2], bold_first_col=True))

add(P("Neler yapabilir", "h2"))
for t in [
    "Türkçe ve İngilizce sohbet etmek, soru cevaplamak.",
    "<b>Araç kullanmak:</b> “klasörleri listele” dendiğinde gerçekten bir fonksiyon çağırıp "
    "sonucu okuyor.",
    "<b>Görmek:</b> resim ve ekran görüntüsü yorumlayabilir. Yetenek modelde var, henüz Jarvis'e "
    "bağlanmadı.",
    "Kısa kod yazmak, metin özetlemek, bir konuyu açıklamak.",
]:
    add(B(t))

add(P("Sınırları", "h2"))
add(table([
    ["Sınır", "Pratikte ne demek"],
    ["Zeka", "9 milyar parametreli bir model, bulut modellerinin çok gerisindedir. Çok adımlı "
     "mantıkta, uzun kodda ve matematikte hata yapar."],
    ["Uydurma (halüsinasyon)", "Bilmediğini uydurabilir. Hafıza eklenmeden önce, konuşmada hiç "
     "geçmeyen bir “tasarım önizlemesi”nden söz etti."],
    ["Güncel bilgi", "Yalnızca eğitim verisinde olanı bilir. Güncel bilgi için web arama aracını "
     "kullanması gerekir."],
    ["Bağlam penceresi", "8.192 token ≈ 6.000 kelime. Uzun bir belgeyi tek seferde okuyamaz."],
    ["Türkçe", "9B modelde iyi; 2B ve 4B modellerde zayıf (pil modunda anlamsız cevaplar görüldü)."],
    ["Araç güvenilirliği", "Küçük modeller bazen yanlış aracı ya da yanlış argümanı seçer."],
    ["Tek iş", "Ollama istekleri sıraya koyar; aynı anda iki şey düşünemez."],
], [1.4, 4.6], bold_first_col=True))
add(Spacer(1, 6))
add(callout([P("<b>Karşılığında kazanılanlar:</b> gizlilik (konuşmalar bilgisayardan çıkmaz), "
               "internetsiz çalışma, sıfır maliyet, kullanım limiti olmaması ve kişisel bilgisayara "
               "doğrudan erişim. Bulut modeli bunların hiçbirini aynı anda veremez.", "quote")]))

# --- ollama
add(P("4. Ollama nedir, neden seçildi?", "h1"))
add(P("Ollama, yerel yapay zeka modellerini <b>indiren, çalıştıran ve servis eden</b> bir "
      f"programdır. Arka planda {code('localhost:11434')} adresinde küçük bir sunucu açar. "
      "Jarvis bu adrese “şu soruyu cevapla” diye istek gönderir; cevap kelime kelime akarak geri "
      "gelir. Bu bilgisayarda kurulu sürüm: <b>0.40.2</b>."))
add(P("Neden Ollama", "h2"))
for t in [
    "<b>Zaten kuruluydu</b> ve ana model indirilmişti; kurulum maliyeti sıfırdı.",
    "<b>GPU ile CPU arasındaki paylaşımı kendisi yapıyor.</b> Model ekran belleğine sığmazsa bir "
    "kısmını işlemciye taşıyor. Bu canlı ölçüldü: 16.384 bağlamda “%84 GPU / %16 CPU”.",
    "<b>Model değiştirmek bir isim değiştirmek kadar kolay.</b> Pil ve GPU profillerinin bu kadar "
    "basit olmasının sebebi bu.",
]:
    add(B(t))
add(P("Alternatifler", "h2"))
add(table([
    ["Alternatif", "Neden şimdilik değil"],
    ["llama.cpp (doğrudan)", "Daha fazla kontrol, ama daha fazla kurulum ve bakım. İleride hız "
     "için değerlendirilebilir."],
    ["vLLM", "Çok kullanıcılı sunucular için tasarlanmış; Linux odaklı, daha çok ekran belleği ister."],
    ["NVIDIA TensorRT-LLM / NIM", "NVIDIA kartlarda en hızlı seçenekler, ama 8 GB'lık dizüstünde "
     "kurulum yükü çok ağır."],
    ["LM Studio", "İyi bir masaüstü arayüzü var, ama koddan yönetmek daha zor."],
], [1.6, 4.4], bold_first_col=True))
add(Spacer(1, 6))
add(P("Dürüst özet: Ollama en hızlı olduğu için değil, <b>en pratik varsayılan</b> olduğu için "
      "seçildi. Bugüne kadar yapılan hiçbir ölçümde darboğaz Ollama olmadı."))

# --- teknoloji
add(keep(P("5. Teknoloji yığını", "h1"),
    P("Projenin tamamı <b>Python 3.10</b> ile yazılıyor."),
    table([
    ["Katman", "Teknoloji", "Görevi"],
    ["Dil modeli", "Ollama + qwen3.5 (2b / 4b / 9b)", "Düşünme, cevap üretme, araç seçimi"],
    ["Model istemcisi", "ollama (ses yolu), LangChain / LangGraph (agent.py)", "Modelle konuşma"],
    ["Ses → metin", "faster-whisper (CTranslate2)", "Konuşmayı yazıya çevirir"],
    ["Konuşma algılama", "Silero VAD (PyTorch)", "Ne zaman başlayıp sustuğunu anlar"],
    ["Metin → ses", "Piper (ONNX Runtime)", "Jarvis'in sesi"],
    ["Ses donanımı", "sounddevice (PortAudio)", "Mikrofon ve hoparlör"],
    ["GPU hızlandırma", "PyTorch 2.14 + CUDA 12.6", "NVIDIA ekran kartını kullanma"],
    ["Arayüz", "CustomTkinter", "Iron Man temalı pencere"],
    ["Veritabanı", "SQLite + SQLAlchemy", "Sohbet kayıtları"],
    ["Web", "DuckDuckGo, BeautifulSoup, Playwright", "Arama, sayfa okuma, tarayıcı"],
    ["Donanım", "psutil, GPUtil, WMI, PowerShell", "Sıcaklık, GPU tespiti"],
    ["Sürüm kontrolü", "Git + GitHub", "Değişiklik geçmişi, yedek"],
], [1.25, 2.4, 2.35], bold_first_col=True, zebra=True),
    Spacer(1, 4),
    P("Diskteki modeller: Piper sesleri ~122 MB, Whisper modelleri ~2,3 GB, Ollama modelleri ~12 GB.",
      "small")))

# --- ses hatti
add(keep(P("6. Ses sisteminin mantığı", "h1"),
    P("Bir konuşma turu aşağıdaki gibi işliyor. Ortadaki sütun ana akış; sağda modelin "
      "kullandığı yardımcılar, solda ise söz kesme döngüsü var."),
    Spacer(1, 4),
    pipeline_diagram()))
add(Spacer(1, 6))
add(P(f"Terminalde görünen durumlar sırasıyla: {code('dinliyorum')} → {code('çözümlüyorum')} → "
      f"{code('düşünüyorum')} → {code('konuşuyorum')}."))
add(P("Tasarımın arkasındaki fikirler", "h2"))
for t in [
    "<b>Buton yok.</b> VAD, kullanıcının sustuğunu 480 ms'lik sessizlikten anlıyor. Daha kısası "
    "doğal duraklamalarda sözü keser; daha uzunu her tura ölü bekleme ekler.",
    "<b>Cevabın tamamı beklenmiyor.</b> Model ilk cümleyi bitirdiği an o cümle seslendiriliyor, "
    "gerisi bu sırada üretiliyor. Eski sistemde cevap tamamen hazır olana kadar sessizlik vardı.",
    "<b>Söz kesilebiliyor.</b> Jarvis konuşurken de mikrofon dinlemeye devam ediyor. Kendi sesini "
    "kullanıcının sesi sanmaması için bu sırada eşik yüksek tutuluyor (0,85). Yankı bastırma "
    "olmadığı için <b>kulaklık gerekiyor</b>.",
    "<b>GPU önceden uyandırılıyor.</b> Ekran kartı boşta kalınca güç tasarrufuna geçiyor ve "
    "uyanması ~2 saniye sürüyor. Uyandırma, kullanıcı konuşmaya başladığı anda tetikleniyor; "
    "kullanıcı konuşurken bu süre zaten geçmiş oluyor.",
    "<b>Konuşma hafızası.</b> Son 8 tur saklanıyor; “kaç tane vardı?” gibi takip soruları önceki "
    "cevaba bağlanabiliyor.",
]:
    add(B(t))

# --- igpu/dgpu
add(P("7. iGPU / dGPU geçişi nasıl oluyor?", "h1"))
add(P("Dizüstünde iki ekran kartı var: işlemcinin içindeki <b>AMD Radeon iGPU</b> (az güç harcar, "
      "yapay zeka için zayıf) ve <b>NVIDIA RTX 4060 dGPU</b> (8 GB ekran belleği, güçlü ama pili "
      "hızlı tüketir)."))
add(P("<b>Donanım tarafı:</b> G-Helper'ın <b>Eco</b> modunda dGPU'nun gücü tamamen kesiliyor ve "
      "Windows kartı “Kod 45: bağlı değil” olarak görüyor. <b>Standard</b> moda geçildiğinde kart "
      "tekrar bağlanıyor (bu projede yeniden başlatarak yapıldı)."))
add(keep(P("<b>Yazılım tarafı:</b> Jarvis açılışta aşağıdaki karar ağacını izliyor:"),
    Spacer(1, 4),
    profile_diagram()))
add(Spacer(1, 6))
add(P("Ortadaki alt soru önemli: Python'un standart araçları “bağlı olmayan” kartı hiç göremiyor ve "
      f"“GPU yok” sanıyor. Windows'un {code('Get-PnpDevice')} komutu ise “kart var ama kapalı” ile "
      "“kart yok” arasındaki farkı söyleyebiliyor. Bu sayede Jarvis sessizce yavaşlamıyor, sebebini "
      "ekrana yazıyor."))
add(table([
    ["Profil", "Ne zaman", "Ses tanıma", "Dil modeli"],
    ["battery", "GPU kapalı", "Whisper base (CPU)", "qwen3.5:2b"],
    ["performance", "GPU açık, VRAM ≥ 7 GB", "Whisper large-v3-turbo (GPU)", "qwen3.5:9b, bağlam 8.192"],
    ["performance-lowvram", "GPU var, VRAM < 7 GB", "Whisper large-v3-turbo (GPU)", "qwen3.5:4b"],
], [1.45, 1.55, 1.75, 1.6], bold_first_col=True))
add(Spacer(1, 6))
add(callout([P("<b>Sınır:</b> Profil açılışta bir kez seçiliyor. Konuşma sırasında şarj kablosu "
               f"çekilirse profil değişmez; programın yeniden başlatılması gerekir. Elle seçmek için: "
               f"{code('--profile battery')}", "quote")], bg=WARN_SOFT, edge=WARN))

# --- veritabani
add(P("8. Veritabanı", "h1"))
add(P(f"<b>Var, ama yarım kullanılıyor.</b> Türü <b>SQLite</b>: ayrı bir sunucu yok, "
      f"{code('jarvis_sessions.db')} adında tek bir dosya. Erişim <b>SQLAlchemy</b> ile, SQL yazmadan "
      "Python sınıfları üzerinden yapılıyor."))
add(table([
    ["Tablo", "Alanlar"],
    ["chat_sessions", "id, title (başlık), created_at, updated_at, is_pinned (sabitlenmiş mi)"],
    ["chat_messages", "id, session_id (hangi oturum), role (kullanıcı / asistan / sistem), "
     "content (içerik), timestamp"],
], [1.3, 4.7], bold_first_col=True))
add(Spacer(1, 6))
add(P("Şu anki içerik: 1 oturum, 0 mesaj. Veritabanına yalnızca eski arayüz yazıyor; "
      "<b>sesli konuşmaların hiçbiri kaydedilmiyor</b>. Jarvis'in 8 turluk hafızası yalnızca bellekte "
      "duruyor ve program kapanınca kayboluyor."))

# --- performans
add(keep(P("9. Ölçülen performans", "h1"),
    P("Aşağıdaki değerlerin tamamı bu bilgisayarda ölçüldü; tahmin değildir."),
    table([
    ["", "Pil modu (CPU)", "Tam güç (GPU)"],
    ["Ses tanıma", "~500 ms", "<b>234–377 ms</b>"],
    ["İlk kelimenin üretilmesi", "~1.000 ms", "<b>114–134 ms</b>"],
    ["Sen sustuktan ilk sese kadar", "en iyi 1,8 sn", "<b>1,1–1,6 sn</b>"],
    ["Türkçe ses tanıma doğruluğu", "zayıf", "iyi"],
], [2.2, 1.8, 1.8], bold_first_col=True)))
add(Spacer(1, 6))
add(keep(P("Aynı cümlenin iki sistemdeki hali", "h2"),
    table([
    ["Model", "“Bilgisayarımın sıcaklığı kaç derece?” cümlesinden duyulan"],
    ["Whisper base (CPU)", "“BİVİ SAYA RIM'ın sıcaklığı kaç derece?”"],
    ["Whisper large-v3-turbo (GPU)", "“Bilgisayarımın sıcaklığı kaç derece?” (kelimesi kelimesine doğru)"],
], [1.8, 4.2], bold_first_col=True)))
add(keep(P("Bağlam boyutu ve ekran belleği", "h2"),
    P("8 GB ekran belleğinde qwen3.5:9b'nin nereye yüklendiği, Ollama'nın kendi raporundan okundu:"),
    table([
    ["Bağlam (token)", "Yerleşim", "Sonuç"],
    ["8.192", "<b>%100 GPU</b>", "Seçilen değer"],
    ["12.288", "%86 GPU / %14 CPU", "Taşan katmanlar yavaşlatıyor"],
    ["16.384", "%84 GPU / %16 CPU", "Taşan katmanlar yavaşlatıyor"],
], [1.4, 2.0, 2.6]),
    Spacer(1, 4),
    P("Ders: Belleğe tam sığan küçük bir bağlam, sığmayan büyük bir bağlamı yener.", "small")))

# --- sorunlar
add(P("10. Bilinen sorunlar", "h1"))
add(table([
    ["#", "Sorun", "Önemi"],
    ["1", "README eski sistemi anlatıyor (pyttsx3, SpeechRecognition, “8 araç”).", "CV için kritik"],
    ["2", "6 test dosyasında 20 test fonksiyonu var ama <b>hiç assert yok</b>: hiçbiri başarısız "
          "olamıyor. pytest kurulu değil.", "CV için kritik"],
    ["3", "Iron Man arayüzü hâlâ eski ses sistemine bağlı (Google STT, robotik ses).", "Yüksek"],
    ["4", "Sesli konuşmalar veritabanına kaydedilmiyor.", "Orta"],
    ["5", "Yazma, silme ve terminal araçları sesle kapalı; onay katmanını bekliyor.", "Tasarım gereği"],
    ["6", "Ses robotik (Piper'ın tek Türkçe sesi kullanılıyor).", "Orta"],
    ["7", "Aynı cümlede Türkçe + İngilizce karışımı desteklenmiyor.", "Düşük"],
    ["8", "Yankı bastırma yok; kulaklık gerekiyor.", "Düşük"],
    ["9", "İki ayrı dil modeli yapısı var: agent.py (LangChain) ve ses yolu (ollama).",
     "Teknik borç"],
], [0.3, 4.5, 1.2]))

# --- yol haritasi
add(P("11. Yol haritası", "h1"))
add(P("Öncelik sırası <i>görülebilir + gerçek mühendislik + az emek</i> ölçütüne göre belirlendi."))
add(P("Kademe 1 · Vitrin (önce bunlar)", "h2"))
for t in [
    "<b>README'yi yeniden yazmak:</b> mimari diyagramı, ölçülmüş performans tablosu, kurulum, "
    "teknoloji listesi. İşe alımcının göreceği ilk ve çoğu zaman tek şey.",
    "<b>Gerçek testler + GitHub Actions:</b> cümle ayırıcı, profil seçimi ve VAD saf fonksiyonlar; "
    "test yazması kolay. Repodaki yeşil “CI passing” rozeti güçlü bir güven sinyali.",
    "<b>Demo videosu / GIF:</b> 30 saniyelik bir gösterim, README'nin en üstünde.",
]:
    add(B(t))
add(P("Kademe 2 · Jarvis'i Jarvis yapan özellikler", "h2"))
for t in [
    "<b>“Hey Jarvis” uyandırma kelimesi</b> (openWakeWord): gösterimde en çok etki bırakan özellik.",
    "<b>Ekranı görme:</b> model bu yeteneğe zaten sahip, yalnızca bağlanması gerekiyor. "
    "“Ekranıma bak, bu hata ne?”",
    "<b>Sesli onay katmanı:</b> “Bu dosyayı sileyim mi efendim?” → “Evet”. Yazma, silme ve "
    "terminal araçları bununla açılır; her işlem denetim kaydına yazılır.",
    "<b>Kalıcı hafıza:</b> konuşmaları veritabanına kaydetmek, ardından anlamsal arama (RAG): "
    "“Geçen hafta ne konuşmuştuk?”",
    "<b>Arayüzü yeni ses sistemine bağlamak.</b>",
    "<b>Doğal ses:</b> XTTS-v2 ile kullanıcının kendi sesinin klonu.",
]:
    add(B(t))
add(P("Kademe 3 · İleri", "h2"))
for t in [
    "<b>MCP desteği:</b> araçları Model Context Protocol üzerinden sunmak; Jarvis'in araçlarını "
    "başka yapay zeka uygulamaları da kullanabilir.",
    "Güvenlik katmanı oturduğunda <b>repoyu herkese açmak</b> ve lisans eklemek.",
]:
    add(B(t))

# --- cv
add(keep(P("12. CV için", "h1"),
    P("Yalnızca yapılmış ve ölçülmüş şeyler yazılmalı; mülakatta her kelimesi sorulabilir."),
    P("İngilizce", "h2"),
    callout([P("Built a fully local, voice-driven AI assistant (Python, Ollama, faster-whisper, Piper) "
               "with a streaming speech pipeline, barge-in interruption, LLM tool calling and "
               "hardware-aware model profiles. Reduced end-to-end voice latency to 1.1–1.6 s on an "
               "8 GB laptop GPU by profiling VRAM placement and GPU idle-wake behaviour.", "quote")])))
add(P("Türkçe", "h2"))
add(callout([P("Tamamen yerel çalışan, sesle kontrol edilen bir yapay zeka asistanı geliştirdim "
               "(Python, Ollama, faster-whisper, Piper). Akışkan ses hattı, söz kesme, araç çağırma "
               "ve donanıma göre otomatik model seçimi içeriyor. Ekran belleği yerleşimini ve GPU "
               "uyanma davranışını ölçerek uçtan uca ses gecikmesini 8 GB'lık dizüstü GPU'sunda "
               "1,1–1,6 saniyeye indirdim.", "quote")]))
add(P("Mülakat hikayeleri", "h2"))
add(P("“Karşılaştığın zor bir hatayı anlat” sorusu neredeyse her teknik mülakatta gelir. "
      "Bu projede üç güçlü örnek var:"))
for t in [
    "<b>Ölçüm aracının kendisi yanıltıyordu.</b> Benchmark her satırda neredeyse aynı ~3,7 saniyeyi "
    "veriyordu. Sorun modelde değildi: benchmark akışı yarıda bırakıyor, sunucu üretmeye devam ediyor "
    "ve her ölçüm bir öncekinin kuyruğunu bekliyordu. <i>Ders: tutarlılık, ölçümün doğru olduğunu "
    "değil, sabit bir maliyet olduğunu gösterebilir.</i>",
    "<b>Daha büyük ayar daha yavaştı.</b> Bağlamı 16k'dan 8k'ya indirmek sistemi hızlandırdı, çünkü "
    "16k'da model belleğe sığmıyor ve katmanların bir kısmı işlemciye taşınıyordu. <i>Ders: kapasite "
    "ayarları önce işin nerede çalışacağını belirler.</i>",
    "<b>Benchmark 140 ms, gerçek kullanım 2.200 ms.</b> İkisi de doğruydu. Benchmark istekleri art "
    "arda atıyordu; gerçek kullanıcı ise konuşup düşünüyor, o arada GPU uykuya geçiyordu. Çözüm, "
    "uyandırmayı kullanıcının zaten konuştuğu ana taşımaktı. <i>Ders: kullanıcı sistemi benchmark'tan "
    "farklı bir ritimle kullanır.</i>",
]:
    add(keep(B(t)))

# --- ek: proje yapisi
add(P("Ek · Proje yapısı", "h1"))
add(table([
    ["Dosya / klasör", "Satır", "Görevi"],
    [code("voice/"), "~1.430", "Ses hattı: VAD, STT, TTS, mikrofon, oynatma, durum makinesi, terminal aracı"],
    [code("core/"), "~740", "Donanım tespiti, profiller, dil modeli istemcisi, sesli araç listesi"],
    [code("bench/latency.py"), "220", "Mikrofonsuz gecikme ölçümü"],
    [code("tools.py"), "923", "12 araç: dosya, terminal, web, tarayıcı, indirme, arşiv, donanım"],
    [code("agent.py"), "285", "LangChain/LangGraph tabanlı metin ajanı (komut satırı)"],
    [code("gui.py"), "1.500", "Iron Man temalı arayüz (eski ses sistemine bağlı)"],
    [code("database.py"), "411", "SQLite oturum ve mesaj kayıtları"],
    [code("config.py"), "213", "Genel ayarlar, sistem istemi, güvenlik listeleri"],
    [code("docs/"), "", "VOICE.md (ses hattı ve ölçümler), eski faz belgeleri arşivi"],
], [1.6, 0.6, 3.8]))

doc = SimpleDocTemplate(
    str(OUT), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
    topMargin=MARGIN, bottomMargin=MARGIN,
    title="Jarvis – Sistem Tasarımı ve Proje Raporu", author="SuleymanKilincc",
    subject="Yerel sesli yapay zeka asistanı",
)
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("yazildi:", OUT)
