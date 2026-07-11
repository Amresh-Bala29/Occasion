export default async function EventWorkspacePage({
  params,
}: {
  params: Promise<{ eventId: string }>;
}) {
  const { eventId } = await params;
  return <main>Event workspace: {eventId}</main>;
}
