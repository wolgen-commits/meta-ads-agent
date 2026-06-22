# Meta Ad Library AI Agent

Scrape iklan kompetitor dari Facebook Ad Library → analisis dengan Claude AI → simpan ke Supabase.

## File Structure
```
meta_ad_agent/
├── agent.py              # Core agent (scraping + AI analisis)
├── api_server.py         # FastAPI server (dipanggil Next.js)
├── supabase_schema.sql   # SQL schema, jalankan di Supabase SQL Editor
├── nextjs_api_route.ts   # Taruh di app/api/competitor-ads/route.ts
├── requirements.txt
└── .env.example
```

## Setup

### 1. Install dependencies Python
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Buat file .env
```bash
cp .env.example .env
# Edit .env dengan API key kamu
```

### 3. Setup Supabase
- Buka Supabase → SQL Editor
- Jalankan isi `supabase_schema.sql`

### 4. Jalankan Python API Server
```bash
uvicorn api_server:app --reload --port 8000
```

### 5. Setup Next.js
- Copy `nextjs_api_route.ts` ke `app/api/competitor-ads/route.ts`
- Tambah ke `.env.local`:
  ```
  AGENT_API_URL=http://localhost:8000
  ```

## Penggunaan dari Dashboard (Next.js)

### Trigger scraping
```js
// Dari komponen React
const res = await fetch('/api/competitor-ads', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    competitor_name: 'Tokopedia',
    country: 'ID',
    max_ads: 20
  })
});
const { job_id } = await res.json();
```

### Cek status job
```js
const status = await fetch(`http://localhost:8000/api/agent/status/${job_id}`);
```

### Fetch data untuk dashboard
```js
const ads = await fetch('/api/competitor-ads?competitor=Tokopedia&objective=SALES');
```

## Data yang Dihasilkan per Iklan

| Field | Contoh |
|---|---|
| `page_name` | Tokopedia |
| `ad_copy` | "Belanja hemat, cashback 50%..." |
| `cta` | Shop Now |
| `media_type` | video |
| `inferred_objective` | SALES |
| `objective_confidence` | HIGH |
| `creative_strategy` | discount |
| `ad_strength_score` | 8 |
| `target_audience_guess` | "Pembeli online usia 18-35" |
| `competitive_insight` | "Fokus pada price war..." |
| `suggested_counter_strategy` | "Tonjolkan value selain harga..." |

## Catatan Penting

- **Objective** tidak tersedia langsung dari Meta — ini adalah **inferensi AI** berdasarkan copy + CTA + format
- Scraping dari `adlibrary.facebook.com` adalah data **publik** yang memang disediakan Meta untuk transparansi
- Jika Facebook mengubah struktur DOM, selector di `agent.py` perlu diupdate (bagian `query_selector`)
- Untuk production: tambah proxy rotation agar tidak di-block
- Rate limit: agent sudah ada delay 0.5s antar iklan, tambah jika perlu
