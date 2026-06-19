// TODO (Day 5): Replace with live trace + diff viewer.
// This page will subscribe to ws://…/runs/{id}/stream and render
// AgentStepCard, LiveLogStream, and DiffViewer components in real time.

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Run {id}</h1>
      <p className="text-muted-foreground">
        Live trace + diff viewer — implemented Day 5.
      </p>
    </div>
  );
}
