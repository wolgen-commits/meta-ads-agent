"""
Test script — verifikasi scraping BERHASIL sebelum jalankan full agent.
Jalankan: python test_scrape.py "Tokopedia"

Output: cetak hasil scraping mentah (belum dianalisis AI, belum disimpan DB)
supaya kamu bisa cek apakah parsing-nya sudah benar.
"""

import asyncio
import sys
import json
from agent import scrape_competitor_ads


async def main():
    competitor = sys.argv[1] if len(sys.argv) > 1 else "Tokopedia"
    print(f"Testing scrape untuk: {competitor}\n")

    ads = await scrape_competitor_ads(competitor, country="ID", max_ads=5)

    print(f"\n{'='*60}")
    print(f"HASIL: {len(ads)} iklan ditemukan")
    print(f"{'='*60}\n")

    for i, ad in enumerate(ads):
        print(f"--- Iklan {i+1} ---")
        print(json.dumps(ad, indent=2, ensure_ascii=False))
        print()

    if not ads:
        print("⚠️  TIDAK ADA DATA. Kemungkinan penyebab:")
        print("  1. Selector teks 'ID Galeri' tidak match (cek locale browser)")
        print("  2. Facebook minta login/captcha (cek dengan headless=False)")
        print("  3. Kompetitor tidak punya iklan aktif di negara ini")
        print("\nCoba jalankan ulang dengan headless=False di agent.py untuk")
        print("lihat browser secara visual dan debug manual.")


if __name__ == "__main__":
    asyncio.run(main())
