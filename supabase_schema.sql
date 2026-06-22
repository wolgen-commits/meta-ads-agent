-- ============================================
-- Supabase SQL Schema: competitor_ads
-- Jalankan di Supabase SQL Editor
-- ============================================

create table if not exists competitor_ads (
  id              uuid default gen_random_uuid() primary key,

  -- Data scraping
  ad_id           text unique,
  competitor_name text not null,
  page_name       text,
  ad_copy         text,
  cta             text,
  platforms       text[],
  media_type      text,        -- 'image' | 'video'
  started_running      text,
  started_running_date date,
  country         text default 'ID',
  snapshot_url    text,
  scraped_at      timestamptz default now(),

  -- Hasil analisis Claude AI
  inferred_objective       text,   -- AWARENESS | TRAFFIC | ENGAGEMENT | LEADS | APP_PROMOTION | SALES
  objective_confidence     text,   -- HIGH | MEDIUM | LOW
  objective_reasoning      text,
  creative_strategy        text,   -- direct_response | brand_awareness | dll
  target_audience_guess    text,
  key_messages             text[],
  ad_strength_score        int,    -- 1-10
  competitive_insight      text,
  suggested_counter_strategy text,
  analyzed_at              timestamptz
);

-- Index untuk query cepat di dashboard
create index on competitor_ads (competitor_name);
create index on competitor_ads (inferred_objective);
create index on competitor_ads (scraped_at desc);
create index on competitor_ads (ad_strength_score desc);

-- Enable Row Level Security (opsional, untuk multi-user)
alter table competitor_ads enable row level security;

-- Policy: semua user authenticated bisa read/write (sesuaikan kebutuhan)
create policy "authenticated users can read ads"
  on competitor_ads for select
  using (auth.role() = 'authenticated');

create policy "authenticated users can insert ads"
  on competitor_ads for insert
  with check (auth.role() = 'authenticated');
