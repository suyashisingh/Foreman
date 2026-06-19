// TODO (Day 5): Replace placeholder with a real virtualized log list
// fed by the WS client's log-line messages. Consider react-virtual for
// large streams.

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** A single log line emitted during a run. */
export interface LogLine {
  /** Monotonically increasing sequence number within the run. */
  seq: number;
  /** ISO-8601 timestamp at which the line was emitted. */
  timestamp: string;
  /** Log severity level. */
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
  /** Log message text. */
  message: string;
}

/** Props for the live log stream component. */
export interface LiveLogStreamProps {
  /** Ordered list of log lines received so far. */
  lines: LogLine[];
}

const levelColors: Record<LogLine["level"], string> = {
  DEBUG: "text-muted-foreground",
  INFO: "text-foreground",
  WARNING: "text-yellow-600 dark:text-yellow-400",
  ERROR: "text-red-600 dark:text-red-400",
};

/** Renders a list of log lines as a scrollable terminal-style card. */
export function LiveLogStream({ lines }: LiveLogStreamProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Live Log Stream</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="max-h-64 overflow-y-auto rounded bg-muted p-3 font-mono text-xs space-y-0.5">
          {lines.length === 0 ? (
            <p className="text-muted-foreground">Waiting for logs…</p>
          ) : (
            lines.map((line) => (
              <p key={line.seq} className={levelColors[line.level]}>
                <span className="opacity-50">{line.timestamp}</span>{" "}
                <span className="font-semibold">[{line.level}]</span>{" "}
                {line.message}
              </p>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
