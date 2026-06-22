// app/api/competitor-ads/route.ts
// Next.js App Router — endpoint untuk trigger agent & fetch data

import { NextRequest, NextResponse } from "next/server";

const AGENT_API = process.env.AGENT_API_URL || "http://localhost:8000";

// POST /api/competitor-ads → trigger scraping agent
export async function POST(req: NextRequest) {
  const body = await req.json();
  const { competitor_name, country = "ID", max_ads = 20 } = body;

  if (!competitor_name) {
    return NextResponse.json(
      { error: "competitor_name wajib diisi" },
      { status: 400 }
    );
  }

  try {
    const res = await fetch(`${AGENT_API}/api/agent/scrape`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ competitor_name, country, max_ads }),
    });

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      { error: "Agent tidak bisa dihubungi. Pastikan Python server running." },
      { status: 503 }
    );
  }
}

// GET /api/competitor-ads?competitor=Tokopedia&objective=SALES
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const competitor = searchParams.get("competitor") || "";
  const objective = searchParams.get("objective") || "";
  const limit = searchParams.get("limit") || "50";

  const params = new URLSearchParams({ limit });
  if (competitor) params.append("competitor", competitor);
  if (objective) params.append("objective", objective);

  try {
    const res = await fetch(`${AGENT_API}/api/ads?${params}`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ error: "Gagal fetch data" }, { status: 500 });
  }
}
