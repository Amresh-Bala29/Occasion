import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({ events: [] });
}

export async function POST(req: Request) {
  const body = await req.json();
  return NextResponse.json({ id: "evt_stub", ...body }, { status: 201 });
}
