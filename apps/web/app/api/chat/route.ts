import { type NextRequest, NextResponse } from "next/server";

// Proxies a chat turn to the agent service.
export async function POST(req: NextRequest) {
  const body = await req.json();
  return NextResponse.json({ ok: true, echo: body });
}
