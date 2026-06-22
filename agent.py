"""
Meta Ad Library AI Agent
Stack: Playwright (scraping) + Groq API (analisis, gratis & cepat) + Supabase (storage)
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from groq import Groq
from playwright.async_api import async_playwright
from supabase import create_client, Client

load_dotenv()  # baca file .env di root folder project

# ─────────────────────────────────────────────
# CONFIG — isi via environment variable / .env
# ─────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "your_groq_key")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")  # model gratis Groq
SUPABASE_URL = os.getenv("SUPABASE_URL", "your_supabase_url")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "your_supabase_anon_key")

if SUPABASE_URL == "your_supabase_url" or not SUPABASE_URL:
    raise ValueError(
        "SUPABASE_URL belum di-set! Buat file .env di folder ini "
        "(copy dari .env.example) lalu isi dengan kredensial asli kamu."
    )

groq_client = Groq(api_key=GROQ_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ─────────────────────────────────────────────
# STEP 1: SCRAPING META AD LIBRARY
# (berbasis teks/regex — class CSS Facebook acak & berubah-ubah,
#  jadi kita anchor ke pola teks yang stabil: "ID Galeri:", "Aktif", dll)
# ─────────────────────────────────────────────
import re
from datetime import date as date_type

MONTH_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}
MONTH_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

def parse_started_running_date(text: str) -> str | None:
    """Parse teks tanggal Meta Ad Library ke ISO date (YYYY-MM-DD). Return None jika gagal."""
    text = text.strip().lower()
    # Format ID: "1 januari 2025" / EN: "january 1, 2025"
    m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
    if m:
        day, month_str, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = MONTH_ID.get(month_str) or MONTH_EN.get(month_str)
        if month:
            return date_type(year, month, day).isoformat()
    m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", text)
    if m:
        month_str, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        month = MONTH_ID.get(month_str) or MONTH_EN.get(month_str)
        if month:
            return date_type(year, month, day).isoformat()
    return None

# Pola teks penanda yang stabil (versi ID & EN, Facebook bisa tampilkan keduanya
# tergantung locale browser)
RE_AD_ID = re.compile(r"(?:ID Galeri|Library ID)\s*:\s*(\d+)", re.IGNORECASE)
RE_START_DATE = re.compile(
    r"(?:Mulai dijalankan pada|Started running on)\s*(.+)", re.IGNORECASE
)
RE_STATUS_ACTIVE = re.compile(r"\b(Aktif|Active)\b", re.IGNORECASE)
RE_SPONSORED = re.compile(r"\b(Bersponsor|Sponsored)\b", re.IGNORECASE)


async def scrape_competitor_ads(
    competitor_name: str,
    country: str = "ID",
    max_ads: int = 20,
) -> list[dict]:
    """
    Scrape iklan aktif dari Meta Ad Library berdasarkan nama kompetitor.
    Strategi: anchor ke teks "ID Galeri:" (selalu ada di tiap card, stabil
    lintas update Facebook) lalu naik ke parent container untuk ambil
    seluruh teks card tersebut. Tidak bergantung pada class CSS apapun.
    """
    ads = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="id-ID",
        )
        page = await context.new_page()

        # Buka Ad Library dengan filter aktif + negara
        url = (
            f"https://www.facebook.com/ads/library/"
            f"?active_status=active"
            f"&ad_type=all"
            f"&country={country}"
            f"&q={competitor_name}"
            f"&search_type=keyword_unordered"
            f"&media_type=all"
        )
        print(f"[Scraper] Membuka: {url}")
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)

        # Scroll untuk load lebih banyak iklan (lazy-loaded)
        prev_count = 0
        for _ in range(8):
            await page.keyboard.press("End")
            await page.wait_for_timeout(2000)
            anchors = await page.get_by_text(
                re.compile(r"ID Galeri|Library ID")
            ).all()
            if len(anchors) == prev_count:
                break  # tidak ada card baru ter-load, stop scroll
            prev_count = len(anchors)

        # Anchor: cari semua elemen yang mengandung teks "ID Galeri:" / "Library ID:"
        # Ini jauh lebih stabil daripada class CSS karena teks UI ini
        # konsisten dipakai Facebook untuk fitur transparansi iklan.
        id_anchors = await page.get_by_text(
            re.compile(r"ID Galeri|Library ID")
        ).all()
        print(f"[Scraper] Ditemukan {len(id_anchors)} anchor 'ID Galeri'")

        seen_ids = set()

        for i, anchor in enumerate(id_anchors[:max_ads]):
            try:
                # Naik beberapa level parent untuk dapat container card penuh.
                # Card biasanya 4-6 level di atas span ID Galeri.
                card = anchor
                card_text = ""
                for level in range(8):
                    handle = await card.evaluate_handle("el => el.parentElement")
                    parent = handle.as_element()
                    if not parent:
                        break
                    card = parent
                    text = await card.inner_text()
                    # Berhenti naik kalau sudah dapat blok teks yang cukup besar
                    # (indikasi sudah mencakup seluruh card, bukan cuma 1 baris)
                    if len(text) > 200 or level == 7:
                        card_text = text
                        break

                if not card_text:
                    continue

                # Ekstrak ad_id untuk dedup (kadang anchor bisa kena duplikat
                # saat scroll overlap)
                id_match = RE_AD_ID.search(card_text)
                ad_id = id_match.group(1) if id_match else f"unknown_{i}"
                if ad_id in seen_ids:
                    continue
                seen_ids.add(ad_id)

                # Deteksi platform dari aria-label/alt icon, BUKAN dari teks
                # (icon platform di Ad Library adalah elemen grafis/SVG tanpa
                # teks visible, jadi inner_text tidak bisa menangkapnya —
                # kita query atribut aksesibilitas-nya langsung).
                platforms = await extract_platforms_from_card(card)

                ad = parse_card_text(card_text, ad_id, competitor_name, country, url)
                if platforms:
                    ad["platforms"] = platforms

                ads.append(ad)
                print(f"[Scraper] Ad {i+1}: {ad['page_name']} | id={ad_id} | {ad['cta']} | platform={ad['platforms']}")

            except Exception as e:
                print(f"[Scraper] Error parsing card {i}: {e}")
                continue

        await browser.close()

    return ads


async def extract_platforms_from_card(card) -> list[str]:
    """
    Ambil nama platform (Facebook/Instagram/Messenger/Audience Network)
    dari atribut aria-label atau alt pada icon di dalam card. Icon platform
    di Ad Library tidak punya teks visible, jadi inner_text() tidak bisa
    dipakai — harus baca atribut aksesibilitas elemen <svg>/<img>/<i> nya.
    """
    valid_platforms = ["Facebook", "Instagram", "Messenger", "Audience Network"]
    found = []

    try:
        # Cek semua elemen yang punya aria-label di dalam card
        labeled_els = await card.query_selector_all("[aria-label]")
        for el in labeled_els:
            label = await el.get_attribute("aria-label")
            if not label:
                continue
            for vp in valid_platforms:
                if vp.lower() in label.lower() and vp not in found:
                    found.append(vp)

        # Fallback: cek atribut alt (untuk <img> icon)
        if not found:
            img_els = await card.query_selector_all("img[alt]")
            for el in img_els:
                alt = await el.get_attribute("alt")
                if not alt:
                    continue
                for vp in valid_platforms:
                    if vp.lower() in alt.lower() and vp not in found:
                        found.append(vp)

    except Exception:
        pass  # gagal ekstrak platform bukan fatal error, biarkan fallback default

    return found


def parse_card_text(
    card_text: str, ad_id: str, competitor_name: str, country: str, source_url: str
) -> dict:
    """
    Parse blok teks satu card iklan (hasil inner_text) menjadi field terstruktur.
    Pendekatan baris-per-baris karena urutan informasi di card relatif konsisten:
    [Status] [ID Galeri] [Tanggal mulai] [Platform] [Kategori] [Lihat Detail]
    [Nama advertiser] [Bersponsor] [Body copy...]
    """
    lines = [l.strip() for l in card_text.split("\n") if l.strip()]

    ad = {
        "ad_id": ad_id,
        "page_name": competitor_name,
        "ad_copy": "",
        "cta": "",
        "platforms": [],
        "media_type": "image",
        "started_running": "Unknown",
        "competitor_name": competitor_name,
        "country": country,
        "snapshot_url": f"https://www.facebook.com/ads/library/?id={ad_id}" if not ad_id.startswith("unknown") else source_url,
        "scraped_at": datetime.utcnow().isoformat(),
    }

    # Tanggal mulai
    date_match = RE_START_DATE.search(card_text)
    if date_match:
        ad["started_running"] = date_match.group(1).strip()

    # Cari index baris "Bersponsor" — nama advertiser biasanya tepat di atasnya
    for idx, line in enumerate(lines):
        if RE_SPONSORED.search(line) and idx > 0:
            ad["page_name"] = lines[idx - 1]
            # Body copy: semua baris setelah "Bersponsor" sampai akhir/limit
            body_lines = lines[idx + 1 : idx + 6]
            ad["ad_copy"] = " ".join(body_lines)
            break

    # Fallback kalau pola "Bersponsor" tidak ketemu — ambil baris terpanjang
    # sebagai body copy (heuristik: body iklan biasanya kalimat terpanjang)
    if not ad["ad_copy"] and lines:
        longest = max(lines, key=len)
        if len(longest) > 20:
            ad["ad_copy"] = longest

    # CTA umum yang dipakai Meta — cocokkan exact match per baris.
    # Daftar diperluas untuk cover CTA berbasis WhatsApp/Messenger yang
    # umum dipakai pengiklan Indonesia.
    known_ctas = [
        "Shop Now", "Belanja Sekarang", "Learn More", "Pelajari Selengkapnya",
        "Sign Up", "Daftar", "Send Message", "Kirim Pesan", "Download",
        "Unduh", "Get Offer", "Dapatkan Penawaran", "Contact Us", "Hubungi Kami",
        "Book Now", "Pesan Sekarang", "Apply Now", "Ajukan Sekarang",
        "Watch More", "Tonton Selengkapnya", "Subscribe", "Berlangganan",
        "WhatsApp", "Chat di WhatsApp", "Send WhatsApp Message",
        "Order Now", "Pesan via WhatsApp", "Get Directions", "Call Now",
        "Hubungi Sekarang", "Use App", "Install Now", "Pasang Sekarang",
    ]
    for line in lines:
        if line in known_ctas:
            ad["cta"] = line
            break

    # Bersihkan ad_copy dari residu UI player video ("0:00 / 0:30") dan
    # dari teks CTA yang ikut ke-capture di akhir body (CTA sudah
    # tersimpan terpisah di ad["cta"], tidak perlu dobel di ad_copy)
    if ad["ad_copy"]:
        cleaned = ad["ad_copy"]
        cleaned = re.sub(r"\d{1,2}:\d{2}\s*/\s*\d{1,2}:\d{2}", "", cleaned)
        if ad["cta"]:
            # Hapus CTA dari ekor ad_copy kalau ikut ke-capture
            cleaned = re.sub(rf"\s*{re.escape(ad['cta'])}\s*$", "", cleaned)
        ad["ad_copy"] = re.sub(r"\s+", " ", cleaned).strip()

    # Platform — deteksi MEDIA DISTRIBUSI iklan, bukan tujuan CTA.
    # "WhatsApp"/"Kirim Pesan" di body teks adalah CTA, bukan indikasi
    # platform tayang. Platform tayang sebenarnya ada di baris ikon
    # setelah label "Platform" (Facebook/Instagram/Messenger/Audience
    # Network) — kita cari baris itu secara spesifik, bukan scan
    # seluruh card_text yang bisa salah tangkap kata di body copy.
    platform_line_idx = None
    for idx2, line in enumerate(lines):
        if re.match(r"^Platform$", line, re.IGNORECASE):
            platform_line_idx = idx2
            break

    found_platforms = []
    if platform_line_idx is not None:
        # Baris setelah label "Platform" biasanya berisi nama platform
        # yang dipisah, atau platform terdeteksi via alt-text icon.
        # Karena icon tidak punya teks (cuma <svg>), kita fallback ke
        # baris setelah "Platform" sebagai kandidat, dicocokkan ke
        # whitelist platform yang valid.
        valid_platforms = ["Facebook", "Instagram", "Messenger", "Audience Network"]
        for line in lines[platform_line_idx : platform_line_idx + 4]:
            for vp in valid_platforms:
                if vp.lower() == line.strip().lower():
                    found_platforms.append(vp)

    ad["platforms"] = found_platforms if found_platforms else ["Facebook"]  # default aman

    return ad


# ─────────────────────────────────────────────
# STEP 2: ANALISIS DENGAN GROQ AI
# ─────────────────────────────────────────────
def analyze_ad_with_claude(ad: dict) -> dict:
    """
    Kirim data iklan ke Groq (Llama 3.3 70B) untuk analisis objective,
    strategi kreatif, dan rekomendasi. Nama fungsi tetap sama supaya
    tidak perlu ubah pemanggil di bagian lain kode.
    """
    prompt = f"""
Kamu adalah analis iklan digital berpengalaman. Analisis data iklan Facebook/Instagram berikut:

Data Iklan:
- Nama Pengiklan: {ad.get('page_name', '-')}
- Copy Iklan: {ad.get('ad_copy', '-')}
- CTA Button: {ad.get('cta', '-')}
- Platform: {', '.join(ad.get('platforms', []))}
- Media Type: {ad.get('media_type', '-')}
- Mulai Tayang: {ad.get('started_running', '-')}

Berikan analisis dalam format JSON berikut (tanpa markdown, hanya JSON murni):
{{
  "inferred_objective": "salah satu dari: AWARENESS | TRAFFIC | ENGAGEMENT | LEADS | APP_PROMOTION | SALES",
  "objective_confidence": "HIGH | MEDIUM | LOW",
  "objective_reasoning": "penjelasan singkat mengapa objective tersebut",
  "creative_strategy": "salah satu dari: direct_response | brand_awareness | social_proof | urgency | storytelling | discount | educational",
  "target_audience_guess": "perkiraan target audiens berdasarkan copy",
  "key_messages": ["pesan utama 1", "pesan utama 2"],
  "ad_strength_score": 1-10,
  "competitive_insight": "insight singkat untuk menghadapi iklan kompetitor ini",
  "suggested_counter_strategy": "strategi singkat untuk bersaing"
}}
"""

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1000,
        temperature=0.3,
        response_format={"type": "json_object"},  # Groq native JSON mode
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    # Bersihkan jika ada markdown fence (jaga-jaga, biasanya tidak perlu
    # karena response_format json_object sudah jamin output JSON murni)
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        analysis = json.loads(raw)
    except json.JSONDecodeError:
        analysis = {
            "inferred_objective": "UNKNOWN",
            "objective_confidence": "LOW",
            "objective_reasoning": raw,
            "creative_strategy": "-",
            "target_audience_guess": "-",
            "key_messages": [],
            "ad_strength_score": 0,
            "competitive_insight": "-",
            "suggested_counter_strategy": "-",
        }

    return analysis


# ─────────────────────────────────────────────
# STEP 3: SIMPAN KE SUPABASE
# ─────────────────────────────────────────────
def save_to_supabase(ad: dict, analysis: dict) -> dict:
    """
    Gabungkan data scraping + analisis, lalu upsert ke Supabase.
    """
    record = {
        "competitor_name": ad.get("competitor_name"),
        "page_name": ad.get("page_name"),
        "ad_copy": ad.get("ad_copy"),
        "cta": ad.get("cta"),
        "platforms": ad.get("platforms", []),
        "media_type": ad.get("media_type"),
        "started_running": ad.get("started_running"),
        "country": ad.get("country"),
        "snapshot_url": ad.get("snapshot_url"),
        "started_running_date": parse_started_running_date(ad.get("started_running") or ""),
        "scraped_at": ad.get("scraped_at"),
        # Hasil analisis Claude
        "inferred_objective": analysis.get("inferred_objective"),
        "objective_confidence": analysis.get("objective_confidence"),
        "objective_reasoning": analysis.get("objective_reasoning"),
        "creative_strategy": analysis.get("creative_strategy"),
        "target_audience_guess": analysis.get("target_audience_guess"),
        "key_messages": analysis.get("key_messages", []),
        "ad_strength_score": analysis.get("ad_strength_score"),
        "competitive_insight": analysis.get("competitive_insight"),
        "suggested_counter_strategy": analysis.get("suggested_counter_strategy"),
        "analyzed_at": datetime.utcnow().isoformat(),
    }

    result = supabase.table("competitor_ads").upsert(record).execute()
    return result.data


# ─────────────────────────────────────────────
# MAIN AGENT ORCHESTRATOR
# ─────────────────────────────────────────────
async def run_agent(
    competitor_name: str,
    country: str = "ID",
    max_ads: int = 20,
    on_progress=None,  # callback(dict) -> None
) -> dict:
    """
    Entry point utama agent. Jalankan scraping → analisis → simpan.
    on_progress dipanggil di setiap langkah untuk update status real-time.
    """
    def progress(message: str, **kwargs):
        print(f"[Agent] {message}")
        if on_progress:
            on_progress({"message": message, **kwargs})

    print(f"\n{'='*50}")
    print(f"[Agent] Mulai scraping: {competitor_name} | {country}")
    print(f"{'='*50}\n")

    # 1. Scraping
    progress("Membuka Meta Ad Library...", step="opening", ads_found=0, ads_analyzed=0)
    raw_ads = await scrape_competitor_ads(competitor_name, country, max_ads)
    print(f"\n[Agent] Total iklan ditemukan: {len(raw_ads)}")

    if len(raw_ads) == 0:
        progress("Tidak ada iklan ditemukan untuk kata kunci ini.", step="done", ads_found=0, ads_analyzed=0)
        return {
            "competitor": competitor_name,
            "total_ads_scraped": 0,
            "total_analyzed": 0,
            "objectives_found": [],
            "completed_at": datetime.utcnow().isoformat(),
        }

    progress(
        f"Ditemukan {len(raw_ads)} iklan. Memulai analisis AI...",
        step="analyzing",
        ads_found=len(raw_ads),
        ads_analyzed=0,
    )

    results = []
    for i, ad in enumerate(raw_ads):
        page = ad.get("page_name") or competitor_name
        progress(
            f"Menganalisis iklan {i+1}/{len(raw_ads)} — {page}",
            step="analyzing",
            ads_found=len(raw_ads),
            ads_analyzed=i,
            current_page=page,
        )
        print(f"\n[Agent] Menganalisis iklan {i+1}/{len(raw_ads)}...")

        # 2. Analisis AI
        analysis = analyze_ad_with_claude(ad)
        print(f"  → Objective: {analysis.get('inferred_objective')} ({analysis.get('objective_confidence')})")

        # 3. Simpan
        progress(
            f"Menyimpan iklan {i+1}/{len(raw_ads)} ke database...",
            step="saving",
            ads_found=len(raw_ads),
            ads_analyzed=i + 1,
            current_page=page,
        )
        saved = save_to_supabase(ad, analysis)
        results.append({"ad": ad, "analysis": analysis, "saved": saved})

        # Rate limit aman
        await asyncio.sleep(0.5)

    summary = {
        "competitor": competitor_name,
        "total_ads_scraped": len(raw_ads),
        "total_analyzed": len(results),
        "objectives_found": list({r["analysis"].get("inferred_objective") for r in results}),
        "completed_at": datetime.utcnow().isoformat(),
    }

    progress(
        f"Selesai! {len(results)} iklan berhasil dianalisis.",
        step="done",
        ads_found=len(raw_ads),
        ads_analyzed=len(results),
    )
    print(f"\n[Agent] Selesai! Summary: {json.dumps(summary, indent=2)}")
    return summary


# ─────────────────────────────────────────────
# RUN LANGSUNG (tes manual)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(
        run_agent(
            competitor_name="Tokopedia",  # ganti nama kompetitor
            country="ID",
            max_ads=10,
        )
    )