// TODO (Day 5): Replace placeholder with a real unified-diff renderer
// (e.g. react-diff-view or a custom syntax-highlighted implementation)
// and wire the approve/reject action to POST /runs/{id}/diffs/{file}/review.

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** Props for a single file diff produced by an agent run. */
export interface DiffViewerProps {
  /** Repo-relative path of the changed file. */
  filePath: string;
  /** The raw unified-diff patch string. */
  patch: string;
  /** Whether a reviewer has approved this diff. */
  approved: boolean;
}

/** Renders a file diff placeholder. Real diff rendering added Day 5. */
export function DiffViewer({ filePath, patch, approved }: DiffViewerProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-mono">{filePath}</CardTitle>
          <Badge variant={approved ? "default" : "secondary"}>
            {approved ? "Approved" : "Pending review"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <pre className="overflow-x-auto rounded bg-muted p-3 text-xs text-muted-foreground">
          {patch || "— no diff —"}
        </pre>
      </CardContent>
    </Card>
  );
}
