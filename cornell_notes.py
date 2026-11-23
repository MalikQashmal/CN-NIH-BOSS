# -*- coding: utf-8 -*-
"""
CORNELL NOTES OTOMATIS  (versi 2)
=================================
Mengisi template Cornell Notes (gambar CN.jpg) secara otomatis dari file teks,
memakai FONT TULISAN TANGAN milik kamu sendiri, dengan rotasi / posisi huruf
yang diacak sedikit-sedikit supaya hasilnya terlihat seperti ditulis tangan.

Langkah:
    1) python cornell_notes.py catatan.txt --font FontKu.ttf --template CN.jpg --kalibrasi
       -> membuat hasil/kalibrasi.png : template + garis warna yang menunjukkan
          DI MANA tulisan akan diletakkan. Ubah angka di POSISI sampai pas.
    2) python cornell_notes.py catatan.txt --font FontKu.ttf --template CN.jpg
       -> membuat 10 variasi CN di folder "hasil/".

Hasil (di folder "hasil/"):
    CN_01.pdf ... CN_10.pdf           -> tiap variasi (PDF semua halaman)
    CN_01_hal1.png ... CN_10_hal1.png -> gambar tiap variasi
    ringkasan.png                     -> semua variasi dalam satu lembar
    daftar_seed.txt                   -> seed tiap variasi (untuk membuat ulang yang bagus)
"""

import argparse
import copy
import datetime
import math
import os
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# =====================================================================
# 1. PENGATURAN  (ubah angka di sini sesuai selera)
# =====================================================================
# Semua nilai "px" di bawah dihitung untuk jarak garis tulis 60 px dan OTOMATIS
# diskalakan mengikuti jarak garis pada template kamu (apa pun resolusinya).

PENGATURAN = {
    # --- File ---
    "template": "CN.jpg",          # gambar template Cornell Notes
    "font": "Handwritten.ttf",          # <-- GANTI dengan font tulisan tangan kamu (.ttf / .otf)
    "output": "hasil",             # nama FOLDER hasil
    "jumlah_variasi": 10,          # berapa CN berbeda yang dibuat (acak rotasi tiap variasi)

    # --- Tulisan ---
    "ukuran_font": 67,           # None = otomatis mengikuti jarak garis. Atau isi angka (px), mis. 62
    "warna_tinta": (46, 44, 44),  # (R, G, B)  biru tinta pulpen. Hitam: (20, 20, 25)
    "transparansi_tinta": (235, 255),  # tekanan pulpen acak: pudar-tebal (0-255)
    "blur_tinta": 0.8,             # 0 = tajam sekali, 0.4-0.7 = lebih natural

    # --- Efek tulisan tangan (ROTASI & ACAK) ---
    "rotasi_std": 2.2,             # sebaran sudut putar tiap huruf (derajat)
    "rotasi_maks": 6.0,            # sudut putar maksimum (derajat) -> 0 = tidak ada rotasi
    "geser_vertikal": 1.8,         # huruf naik/turun acak (px)
    "variasi_ukuran": 0.05,        # huruf lebih besar/kecil acak (0.05 = +-5%)
    "variasi_ukuran_kata": 0.05,   # tiap KATA sedikit lebih besar/kecil dari kata lain (0 = seragam)
    "variasi_jarak": 1.2,          # jarak antar huruf acak (px)
    "jarak_huruf": 0.0,            # tambah jarak antar huruf (px, bisa negatif)
    "kemiringan_baris": 0.30,      # satu baris agak miring (derajat, acak per baris)
    "geser_awal_baris": 6,         # awal baris maju/mundur acak (px)

    # --- Khusus kolom PERTANYAAN ---
    "ukuran_pertanyaan": 0.92,     # ukuran dasar tulisan pertanyaan (1.0 = sama dengan catatan)
    "acak_ukuran_pertanyaan": (0.85, 1.30),  # tiap KALIMAT diacak lebih besar/kecil dalam rentang ini
                                              # (1.0, 1.0) = tidak diacak. Bisa diatur manual per kalimat: @besar, @kecil, @1.3

    # --- Lain-lain ---
    "tanda_dpi": 223,              # dpi untuk PDF
    "seed": None,                  # isi angka (mis. 1) supaya hasil selalu sama persis
    "shrink_minimal": 0.62,        # Topik/Nama/Rangkuman boleh mengecil sampai 62% jika kepanjangan
}

# =====================================================================
# 2. POSISI DI TEMPLATE
# =====================================================================
# Koordinat dalam PIXEL pada gambar template kamu.
#   "baseline" = garis dasar tulisan (bagian bawah huruf, bukan huruf g/y/p)
#   x = awal tulisan (kiri),  x2 = batas kanan.
#
# KOLOM BERGARIS (pertanyaan & catatan):
#   "baseline" = baseline BARIS PERTAMA. Baris-baris berikutnya turun otomatis
#   mengikuti jarak garis tulis di template.
#   Isi None = dideteksi otomatis dari template (disarankan, coba dulu).
#   Isi angka = dipakai persis seperti yang kamu tulis.
#
# Gunakan  --kalibrasi  untuk melihat hasil pengaturan ini secara visual.

POSISI = {
    # satu baris, ditulis di sebelah kanan label
    "nama":    {"x": 1520, "x2": 2300, "baseline": 275},
    "nim":     {"x": 1483, "x2": 2300, "baseline": 400},
    "tanggal": {"x": 1565, "x2": 2300, "baseline": 556},
    # beberapa baris
    "topik":   {"x": 240, "x2": 1318, "baselines": [368, 428, 488]},
    "rangkuman": {"x": 162, "x2": 2299, "baselines": [3130, 3177, 3224, 3271, 3318, 3365]},
    # kolom bergaris (ikut garis tulis template)
    "pertanyaan": {"x": None, "x2": None, "baseline": None},
    "catatan":    {"x": None, "x2": None, "baseline": None},
}

# Jarak antar garis & jumlah garis per halaman. None = dideteksi otomatis dari template.
GRID_MANUAL = {"jarak": None, "jumlah": 27.5}

# Cadangan jika deteksi otomatis gagal (ukuran template asli 1844 x 2576)
GRID_CADANGAN = {"pertama": 610, "jarak": 60.16, "jumlah": 26, "x_awal": 617, "x_akhir": 1690}
JARAK_ACUAN = 60.16

BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]

# Penanda ukuran kalimat yang bisa ditulis di depan kalimat pada file catatan:
#     @besar Apa itu AEIOU ?      @kecil Jelaskan 5 Elemen AEIOU !      @1.3 ...      @130% ...
UKURAN_NAMA = {"besar": 1.24, "sedang": 1.0, "kecil": 0.80}

PENANDA = re.compile(r"^(?:[-•*–]|\d+[.)]|[A-Za-z][.)])\s+")

# Pengganti jika font kamu tidak punya karakter tersebut
SUBSTITUSI = {
    "²": "^2", "³": "^3", "¹": "^1", "≤": "<=", "≥": ">=", "≠": "!=", "×": "x", "÷": "/",
    "•": "-", "–": "-", "—": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...",
    "→": "->", "←": "<-", "≈": "~", "°": "o", "µ": "u", "±": "+-", "√": "akar",
}

# =====================================================================
# 3. DETEKSI GARIS TULIS PADA TEMPLATE
# =====================================================================

def deteksiGrid(template):
    """
    Mencari garis tulis (garis hitam panjang yang jaraknya seragam) pada template.
    Mengembalikan dict(pertama, jarak, jumlah, x_awal, x_akhir) atau None bila gagal.
    """
    g = np.array(template.convert("L"), dtype=np.int16)
    H, W = g.shape
    x0, x1 = int(W * 0.42), int(W * 0.86)

    for thr in (170, 195, 215):
        frac = (g[:, x0:x1] < thr).mean(axis=1)
        idx = np.where(frac > 0.9)[0]
        if len(idx) == 0:
            continue
        grup = []
        for y in idx:
            if grup and y - grup[-1][-1] <= 3:
                grup[-1].append(y)
            else:
                grup.append([y])
        pusat = np.array([np.mean(gp) for gp in grup])
        if len(pusat) < 8:
            continue

        # rantai terpanjang dengan jarak seragam (membuang garis tepi kotak)
        d = np.diff(pusat)
        med = np.median(d)
        terbaik, mulai = (0, 0), 0
        for i in range(len(d)):
            if abs(d[i] - med) > 0.15 * med:
                if i - mulai > terbaik[1] - terbaik[0]:
                    terbaik = (mulai, i)
                mulai = i + 1
        if len(d) - mulai > terbaik[1] - terbaik[0]:
            terbaik = (mulai, len(d))
        garis = pusat[terbaik[0]:terbaik[1] + 1]
        if len(garis) < 8:
            continue

        # panjang horizontal garis pertama
        y = int(round(garis[0]))
        gelap = (g[max(y - 3, 0):y + 4, :] < thr).any(axis=0)
        cx = int(W * 0.64)
        if not gelap[cx]:
            continue
        a = b = cx
        while a > 0 and gelap[a - 1]:
            a -= 1
        while b < W - 1 and gelap[b + 1]:
            b += 1

        return {
            "pertama": float(garis[0]),
            "jarak": float((garis[-1] - garis[0]) / (len(garis) - 1)),
            "jumlah": int(len(garis)),
            "x_awal": int(a), "x_akhir": int(b),
        }
    return None


def siapkanLayout(template, cfg):
    """Menggabungkan hasil deteksi + pengaturan manual -> posisi final yang siap dipakai."""
    det = deteksiGrid(template)
    if det:
        g = dict(det)
        sumber = "terdeteksi otomatis"
    else:
        g = dict(GRID_CADANGAN)
        k = template.width / 1844
        for kunci in ("pertama", "jarak", "x_awal", "x_akhir"):
            g[kunci] *= k
        sumber = "DETEKSI GAGAL -> memakai perkiraan (atur manual lewat GRID_MANUAL & POSISI)"

    if GRID_MANUAL.get("jarak"):
        g["jarak"] = float(GRID_MANUAL["jarak"])
    if GRID_MANUAL.get("jumlah"):
        g["jumlah"] = int(GRID_MANUAL["jumlah"])

    skala = g["jarak"] / JARAK_ACUAN
    naik = 8 * skala  # tulisan "duduk" sedikit di atas garis

    pos = copy.deepcopy(POSISI)
    ct, pt = pos["catatan"], pos["pertanyaan"]
    if ct.get("x") is None:   ct["x"] = g["x_awal"] + 12 * skala
    if ct.get("x2") is None:  ct["x2"] = g["x_akhir"] - 10 * skala
    if pt.get("x2") is None:  pt["x2"] = g["x_awal"] - 27 * skala
    if pt.get("x") is None:   pt["x"] = g["x_awal"] - 497 * skala
    for p in (pt, ct):
        if p.get("baseline") is None:
            p["baseline"] = g["pertama"] - naik

    # konfigurasi efek diskalakan mengikuti resolusi template
    c = dict(cfg)
    for k in ("geser_vertikal", "variasi_jarak", "jarak_huruf", "geser_awal_baris", "blur_tinta"):
        c[k] = cfg[k] * skala
    if not c["ukuran_font"]:
        c["ukuran_font"] = round(46 * skala)
    c["_skala"] = skala

    print(f"Template {template.width} x {template.height} px | garis tulis {sumber}")
    print(f"  {g['jumlah']} garis, jarak {g['jarak']:.1f} px, garis pertama y={g['pertama']:.0f}, "
          f"x {g['x_awal']}-{g['x_akhir']} | ukuran huruf {c['ukuran_font']} px")
    return pos, g, c


# =====================================================================
# 4. MEMBACA FILE CATATAN
# =====================================================================

def bacaCatatan(path):
    """
    Format file teks:
        [TOPIK]  [NAMA]  [NIM]  [TANGGAL]  [PERTANYAAN]  [CATATAN]  [RANGKUMAN]
    """
    bagian = {}
    sekarang = None
    with open(path, encoding="utf-8") as f:
        for baris in f.read().splitlines():
            m = re.match(r"^\s*\[(\w+)\]\s*$", baris)
            if m:
                sekarang = m.group(1).lower()
                bagian[sekarang] = []
            elif sekarang is not None:
                bagian[sekarang].append(baris.rstrip())
    for v in bagian.values():
        while v and not v[0].strip():
            v.pop(0)
        while v and not v[-1].strip():
            v.pop()
    return bagian


def tanggalHariIni():
    t = datetime.date.today()
    return f"{t.day} {BULAN[t.month - 1]} {t.year}"


# =====================================================================
# 5. MESIN TULISAN TANGAN
# =====================================================================

class Penulis:
    def __init__(self, font_path, cfg, rng):
        self.font_path = font_path
        self.cfg = cfg
        self.rng = rng
        self._cache = {}
        self._glyph = {}
        self.hilang = set()

    def font(self, ukuran):
        ukuran = max(6, int(round(ukuran)))
        if ukuran not in self._cache:
            self._cache[ukuran] = ImageFont.truetype(self.font_path, ukuran)
        return self._cache[ukuran]

    # ---------- karakter yang tidak ada di font ----------
    def punyaGlyph(self, ch):
        if ch not in self._glyph:
            f = self.font(40)
            kosong = (f.getbbox("\U0010FFFF"), f.getlength("\U0010FFFF"))
            self._glyph[ch] = (f.getbbox(ch), f.getlength(ch)) != kosong
        return self._glyph[ch]

    def normalisasi(self, teks):
        out = []
        for ch in teks:
            if ch.isspace() or self.punyaGlyph(ch):
                out.append(ch)
            elif ch in SUBSTITUSI:
                out.append(SUBSTITUSI[ch])
            else:
                self.hilang.add(ch)
                out.append("?")
        return "".join(out)

    # ---------- pengukuran ----------
    def lebar(self, teks, ukuran):
        f = self.font(ukuran)
        return sum(f.getlength(c) for c in teks) + self.cfg["jarak_huruf"] * len(teks)

    # ---------- bungkus teks (word wrap) ----------
    def faktorUkuran(self, token):
        """'besar' / 'kecil' / '1.3' / '130%' -> faktor ukuran, atau None jika tidak dikenali."""
        t = token.lower().strip()
        if t in UKURAN_NAMA:
            return UKURAN_NAMA[t]
        try:
            v = float(t[:-1]) / 100 if t.endswith("%") else float(t.replace(",", "."))
        except ValueError:
            return None
        return min(max(v, 0.3), 3.0)

    def bungkus(self, paragraf, ukuran, lebar_maks, acak=None):
        """
        Mengubah list paragraf -> list (indent_px, teks, ukuran_px) per baris visual.
        - Paragraf yang diawali @besar / @kecil / @1.3 memakai ukuran itu.
        - acak=(lo, hi): paragraf TANPA penanda diberi ukuran acak dalam rentang tsb.
        """
        lebar_maks *= 0.97  # margin aman karena huruf diacak
        hasil = []
        for para in paragraf:
            faktor = None
            m = re.match(r"^\s*@(\S+)(?:\s+(.*))?$", para)
            if m:
                faktor = self.faktorUkuran(m.group(1))
                if faktor is not None:
                    para = m.group(2) or ""
            if not para.strip():
                hasil.append((0, "", ukuran))
                continue
            if faktor is None:
                faktor = float(self.rng.uniform(acak[0], acak[1])) if acak else 1.0
            u = ukuran * faktor

            spasi = self.lebar(" ", u)
            lead = len(para) - len(para.lstrip(" "))
            indent0 = lead * spasi
            isi = para.strip()
            pm = PENANDA.match(isi)
            gantung = indent0 + (self.lebar(pm.group(0), u) if pm else 0)

            cur, cur_indent = "", indent0
            for kata in isi.split():
                coba = (cur + " " + kata) if cur else kata
                if self.lebar(coba, u) + cur_indent <= lebar_maks:
                    cur = coba
                    continue
                if cur:
                    hasil.append((cur_indent, cur, u))
                    cur_indent, cur = gantung, ""
                cur = kata
                while self.lebar(cur, u) + cur_indent > lebar_maks and len(cur) > 1:
                    potong = len(cur) - 1
                    while potong > 1 and self.lebar(cur[:potong], u) + cur_indent > lebar_maks:
                        potong -= 1
                    hasil.append((cur_indent, cur[:potong], u))
                    cur_indent, cur = gantung, cur[potong:]
            if cur:
                hasil.append((cur_indent, cur, u))
        return hasil

    def bungkusMuat(self, paragraf, ukuran, lebar_maks, kapasitas):
        """Perkecil huruf bila perlu sampai muat dalam `kapasitas` baris."""
        u = ukuran
        minimal = ukuran * self.cfg["shrink_minimal"]
        langkah = max(1, round(2 * self.cfg["_skala"]))
        while True:
            baris = self.bungkus(paragraf, u, lebar_maks)
            if len(baris) <= kapasitas or u <= minimal:
                return baris, u
            u -= langkah

    # ---------- menggambar ----------
    def _stempel(self, ink, ch, f, x, y_dasar, sudut, alpha):
        warna = self.cfg["warna_tinta"]
        adv = f.getlength(ch)
        asc, desc = f.getmetrics()
        pad = int(f.size * 0.6) + 4
        w, h = int(adv) + 2 * pad, asc + desc + 2 * pad
        layer = Image.new("RGBA", (w, h), (*warna, 0))
        ImageDraw.Draw(layer).text((pad, pad + asc), ch, font=f,
                                   fill=(*warna, alpha), anchor="ls")
        if abs(sudut) > 0.01:
            layer = layer.rotate(sudut, resample=Image.BICUBIC,
                                 center=(pad + adv / 2, pad + asc))
        gabungkan(ink, layer, int(round(x - pad)), int(round(y_dasar - pad - asc)))

    def tulisBaris(self, ink, teks, x_awal, y_dasar, ukuran):
        c, rng = self.cfg, self.rng
        if not teks:
            return
        x = x_awal + (rng.uniform(-c["geser_awal_baris"], c["geser_awal_baris"])
                      if c["geser_awal_baris"] else 0)
        x0 = x
        skala = c["_skala"]
        miring = math.tan(math.radians(rng.normal(0, c["kemiringan_baris"])))
        fase = rng.uniform(0, 6.28)
        amp = c["geser_vertikal"] * 0.6
        vk = c.get("variasi_ukuran_kata", 0.0)
        skala_kata = 1 + rng.uniform(-vk, vk)

        for ch in teks:
            if ch == " ":
                x += self.lebar(" ", ukuran) * (1 + rng.normal(0, 0.12))
                skala_kata = 1 + rng.uniform(-vk, vk)   # kata berikutnya ukurannya sedikit beda
                continue
            f = self.font(ukuran * skala_kata * (1 + rng.uniform(-c["variasi_ukuran"], c["variasi_ukuran"])))
            sudut = float(np.clip(rng.normal(0, c["rotasi_std"]), -c["rotasi_maks"], c["rotasi_maks"]))
            y = (y_dasar + (x - x0) * miring
                 + amp * math.sin((x - x0) / (140.0 * skala) + fase)
                 + rng.normal(0, c["geser_vertikal"] * 0.5))
            alpha = int(rng.integers(c["transparansi_tinta"][0], c["transparansi_tinta"][1] + 1))
            self._stempel(ink, ch, f, x, y, sudut, alpha)
            x += f.getlength(ch) + c["jarak_huruf"] + rng.normal(0, c["variasi_jarak"])


def gabungkan(dst, src, x, y):
    """alpha_composite yang aman jika keluar batas gambar."""
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + src.width, dst.width), min(y + src.height, dst.height)
    if x0 >= x1 or y0 >= y1:
        return
    s = src.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    r = dst.crop((x0, y0, x1, y1))
    dst.paste(Image.alpha_composite(r, s), (x0, y0))


# =====================================================================
# 6. MERAKIT HALAMAN
# =====================================================================

def tulisKolom(pen, ink, baris, p, mulai, jarak, jumlah):
    """Menulis `baris` pada grid garis tulis, mulai dari indeks `mulai`."""
    for i in range(jumlah):
        idx = mulai + i
        if idx >= len(baris):
            break
        indent, teks, u = baris[idx]
        pen.tulisBaris(ink, teks, p["x"] + indent, p["baseline"] + i * jarak, u)


def tulisBlok(pen, ink, paragraf, p, ukuran):
    """Untuk Topik / Rangkuman: beberapa baris, otomatis mengecil jika kepanjangan."""
    lebar = p["x2"] - p["x"]
    baris, u = pen.bungkusMuat(paragraf, ukuran, lebar, len(p["baselines"]))
    if len(baris) > len(p["baselines"]):
        print(f"  [PERINGATAN] Teks terlalu panjang, hanya {len(p['baselines'])} baris yang muat.")
    for (indent, teks, s_), y in zip(baris, p["baselines"]):
        pen.tulisBaris(ink, teks, p["x"] + indent, y, s_)


def tulisSatuBaris(pen, ink, teks, p, ukuran):
    if not teks:
        return
    lebar = p["x2"] - p["x"]
    u = ukuran
    langkah = max(1, round(2 * pen.cfg["_skala"]))
    while pen.lebar(teks, u) > lebar * 0.97 and u > ukuran * pen.cfg["shrink_minimal"]:
        u -= langkah
    pen.tulisBaris(ink, teks, p["x"], p["baseline"], u)


def buatHalaman(template, pen, bagian, pos, grid, hal, total, baris_tanya, baris_cat):
    cfg = pen.cfg
    ukuran = cfg["ukuran_font"]
    ink = Image.new("RGBA", template.size, (0, 0, 0, 0))

    if bagian.get("topik"):
        tulisBlok(pen, ink, bagian["topik"], pos["topik"], ukuran)
    for kunci in ("nama", "nim", "tanggal"):
        teks = " ".join(bagian.get(kunci, [])).strip()
        if kunci == "tanggal" and teks.lower() in ("otomatis", "hari ini", "auto"):
            teks = tanggalHariIni()
        tulisSatuBaris(pen, ink, pen.normalisasi(teks), pos[kunci], ukuran)

    mulai = (hal - 1) * grid["jumlah"]
    tulisKolom(pen, ink, baris_tanya, pos["pertanyaan"], mulai, grid["jarak"], grid["jumlah"])
    tulisKolom(pen, ink, baris_cat, pos["catatan"], mulai, grid["jarak"], grid["jumlah"])

    if hal == total and bagian.get("rangkuman"):
        tulisBlok(pen, ink, bagian["rangkuman"], pos["rangkuman"], ukuran)

    if cfg["blur_tinta"] > 0:
        ink = ink.filter(ImageFilter.GaussianBlur(cfg["blur_tinta"]))
    return Image.alpha_composite(template, ink).convert("RGB")


# =====================================================================
# 7. KALIBRASI (gambar bantu untuk mengatur koordinat)
# =====================================================================

def buatKalibrasi(template, pos, grid, cfg, path):
    im = template.convert("RGB")
    d = ImageDraw.Draw(im)
    lw = max(2, round(grid["jarak"] / 28))
    try:
        fnt = ImageFont.load_default(size=max(14, round(grid["jarak"] / 3)))
    except TypeError:
        fnt = ImageFont.load_default()
    MERAH, HIJAU, BIRU, ORANYE = (230, 30, 30), (20, 150, 60), (30, 90, 230), (240, 140, 0)

    def garis(x, x2, y, warna):
        d.line([(x, y), (x2, y)], fill=warna, width=lw)

    for k in ("nama", "nim", "tanggal"):
        p = pos[k]
        garis(p["x"], p["x2"], p["baseline"], MERAH)
        d.text((p["x"], p["baseline"] - grid["jarak"] * 0.55), f"{k} (baseline {p['baseline']:.0f})", fill=MERAH, font=fnt)
    for k in ("topik", "rangkuman"):
        p = pos[k]
        for y in p["baselines"]:
            garis(p["x"], p["x2"], y, ORANYE)
        d.text((p["x"], p["baselines"][0] - grid["jarak"] * 0.55), k, fill=ORANYE, font=fnt)
    for k, warna in (("pertanyaan", HIJAU), ("catatan", BIRU)):
        p = pos[k]
        for i in range(grid["jumlah"]):
            y = p["baseline"] + i * grid["jarak"]
            garis(p["x"], p["x2"], y, warna)
        y_atas, y_bawah = p["baseline"] - grid["jarak"], p["baseline"] + (grid["jumlah"] - 1) * grid["jarak"]
        d.line([(p["x"], y_atas), (p["x"], y_bawah)], fill=warna, width=lw)
        d.line([(p["x2"], y_atas), (p["x2"], y_bawah)], fill=warna, width=lw)
        d.text((p["x"] + 6, y_atas - grid["jarak"] * 0.1),
               f"{k}: x={p['x']:.0f}  x2={p['x2']:.0f}  baseline={p['baseline']:.0f}", fill=warna, font=fnt)
    im.save(path)


# =====================================================================
# 8. PROGRAM UTAMA
# =====================================================================

def lembarRingkasan(daftar, path, kolom=5, lebar_thumb=460):
    """Gabungkan halaman pertama tiap variasi jadi satu gambar untuk dibandingkan."""
    try:
        fnt = ImageFont.load_default(size=26)
    except TypeError:
        fnt = ImageFont.load_default()
    w0, h0 = daftar[0][2].size
    tinggi_thumb = int(lebar_thumb * h0 / w0)
    baris = math.ceil(len(daftar) / kolom)
    gap, label_h = 16, 40
    W = kolom * (lebar_thumb + gap) + gap
    H = baris * (tinggi_thumb + label_h + gap) + gap
    kanvas = Image.new("RGB", (W, H), (235, 235, 235))
    d = ImageDraw.Draw(kanvas)
    for i, (no, seed, img) in enumerate(daftar):
        r, c = divmod(i, kolom)
        x = gap + c * (lebar_thumb + gap)
        y = gap + r * (tinggi_thumb + label_h + gap)
        d.text((x + 4, y + 4), f"#{no:02d}   seed {seed}", fill=(20, 20, 20), font=fnt)
        kanvas.paste(img.resize((lebar_thumb, tinggi_thumb), Image.LANCZOS), (x, y + label_h))
    kanvas.save(path)


def jalankan(file_catatan, cfg, hanya_kalibrasi=False):
    if not os.path.exists(cfg["template"]):
        raise SystemExit(f"Template tidak ditemukan: {cfg['template']}")
    template = Image.open(cfg["template"]).convert("RGBA")
    folder = cfg["output"]
    os.makedirs(folder, exist_ok=True)

    pos, grid, cfg = siapkanLayout(template, cfg)

    if hanya_kalibrasi:
        path = os.path.join(folder, "kalibrasi.png")
        buatKalibrasi(template, pos, grid, cfg, path)
        print(f"\nGambar kalibrasi: {path}")
        print("Garis merah/oranye/hijau/biru = tempat baseline tulisan akan diletakkan.")
        print("Geser angka di POSISI (atau isi None agar otomatis) lalu jalankan --kalibrasi lagi.")
        return

    if not os.path.exists(cfg["font"]):
        raise SystemExit(
            f"Font tidak ditemukan: {cfg['font']}\n"
            f"Letakkan file font kamu di folder ini lalu jalankan dengan:  --font NamaFont.ttf"
        )

    bagian = bacaCatatan(file_catatan)
    pen0 = Penulis(cfg["font"], cfg, np.random.default_rng(0))
    for k in ("topik", "pertanyaan", "catatan", "rangkuman"):
        bagian[k] = [pen0.normalisasi(t) for t in bagian.get(k, [])]
    for k in ("nama", "nim", "tanggal"):
        bagian[k] = [pen0.normalisasi(t) if k != "tanggal" else t for t in bagian.get(k, [])]
    if pen0.hilang:
        print("  [PERINGATAN] Font tidak punya karakter:", " ".join(sorted(pen0.hilang)),
              "-> diganti '?'. Ganti font atau ubah teksnya.")

    n = max(1, int(cfg["jumlah_variasi"]))
    if n == 1 and cfg["seed"] is not None:
        daftar_seed = [cfg["seed"]]
    else:
        dasar = cfg["seed"] if cfg["seed"] is not None else int(np.random.SeedSequence().entropy % 1_000_000)
        daftar_seed = [dasar + i for i in range(n)]

    ukuran = cfg["ukuran_font"]
    ringkas, catatan_seed = [], []
    for no, seed in enumerate(daftar_seed, 1):
        pen = Penulis(cfg["font"], cfg, np.random.default_rng(seed))
        baris_tanya = pen.bungkus(bagian.get("pertanyaan", []), ukuran * cfg["ukuran_pertanyaan"],
                                  pos["pertanyaan"]["x2"] - pos["pertanyaan"]["x"],
                                  acak=cfg["acak_ukuran_pertanyaan"])
        baris_cat = pen.bungkus(bagian.get("catatan", []), ukuran,
                                pos["catatan"]["x2"] - pos["catatan"]["x"])
        total = max(1, math.ceil(max(len(baris_tanya), len(baris_cat)) / grid["jumlah"]))
        if no == 1:
            print(f"Catatan: {len(baris_cat)} baris | Pertanyaan: {len(baris_tanya)} baris -> {total} halaman per CN")

        halaman = []
        for h in range(1, total + 1):
            img = buatHalaman(template, pen, bagian, pos, grid, h, total, baris_tanya, baris_cat)
            img.save(os.path.join(folder, f"CN_{no:02d}_hal{h}.png"))
            halaman.append(img)
        halaman[0].save(os.path.join(folder, f"CN_{no:02d}.pdf"), save_all=True,
                        append_images=halaman[1:], resolution=cfg["tanda_dpi"])

        ringkas.append((no, seed, halaman[0]))
        catatan_seed.append(f"CN_{no:02d}  seed {seed}")
        print(f"  Variasi {no:02d}/{n} selesai (seed {seed})")

    if n > 1:
        lembarRingkasan(ringkas, os.path.join(folder, "ringkasan.png"))
    with open(os.path.join(folder, "daftar_seed.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(catatan_seed) + "\n\n"
                "Untuk membuat ulang satu variasi persis sama:\n"
                "  python cornell_notes.py catatan.txt --font FontKu.ttf --variasi 1 --seed <angka seed>\n")
    print(f"\nSemua hasil ada di folder: {folder}/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Pembuat Cornell Notes otomatis bertulisan tangan")
    ap.add_argument("catatan", help="file teks isi catatan (lihat contoh_catatan.txt)")
    ap.add_argument("--font", help="file font tulisan tangan (.ttf/.otf)")
    ap.add_argument("--template", help="gambar template CN (default CN.jpg)")
    ap.add_argument("--out", help="nama folder hasil (default: hasil)")
    ap.add_argument("--variasi", type=int, help="jumlah CN berbeda yang dibuat (default: 10)")
    ap.add_argument("--ukuran", type=int, help="ukuran huruf (px); kosong = otomatis")
    ap.add_argument("--seed", type=int, help="angka tetap agar hasil selalu sama")
    ap.add_argument("--kalibrasi", action="store_true",
                    help="hanya buat gambar bantu posisi (hasil/kalibrasi.png)")
    a = ap.parse_args()

    cfg = dict(PENGATURAN)
    if a.font:     cfg["font"] = a.font
    if a.template: cfg["template"] = a.template
    if a.out:      cfg["output"] = a.out
    if a.variasi:  cfg["jumlah_variasi"] = a.variasi
    if a.ukuran:   cfg["ukuran_font"] = a.ukuran
    if a.seed is not None: cfg["seed"] = a.seed

    jalankan(a.catatan, cfg, hanya_kalibrasi=a.kalibrasi)