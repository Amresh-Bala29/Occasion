export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-2.5 p-6 text-center">
      <h1 className="font-serif text-[44px] font-medium tracking-[-0.01em]">Occasion</h1>
      <p className="text-[15px] text-ink-soft">Plan any event with an autonomous agent team.</p>
      <a href="/dashboard" className="mt-2 font-semibold text-brand hover:underline">
        Open dashboard →
      </a>
    </main>
  );
}
