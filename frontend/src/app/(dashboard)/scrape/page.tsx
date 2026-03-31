"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api, fetcher } from "@/lib/api";
import type { ScrapeJob } from "@/lib/schemas/api";
import { STATES } from "@/lib/constants";
import { API_BASE_URL } from "@/lib/env";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSSE } from "@/hooks/use-sse";

interface PaginatedJobs {
  items: ScrapeJob[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

function statusBadgeVariant(
  status: string
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "completed":
      return "default";
    case "failed":
      return "destructive";
    case "running":
      return "secondary";
    default:
      return "outline";
  }
}

export default function ScrapePage() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [scraping, setScraping] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const sseUrl = activeJobId
    ? `${API_BASE_URL}/api/v1/scrape/jobs/${activeJobId}/events`
    : null;
  const { data: progress } = useSSE(sseUrl);

  const { data: jobs } = useSWR<PaginatedJobs>(
    "/api/v1/scrape/jobs?page_size=10",
    fetcher,
    { refreshInterval: activeJobId ? 2000 : 10000 }
  );

  // Check if active job finished
  const activeJob = jobs?.items.find((j) => j.id === activeJobId);
  if (
    activeJob &&
    (activeJob.status === "completed" || activeJob.status === "failed")
  ) {
    // Clear active job after a short delay so user sees the final state
    setTimeout(() => setActiveJobId(null), 3000);
  }

  async function triggerScrape(stateCode: string) {
    setScraping(stateCode);
    setLastError(null);
    try {
      const job = await api.post<ScrapeJob>("/scrape/", {
        state_code: stateCode,
      });
      setActiveJobId(job.id);
      mutate("/api/v1/scrape/jobs?page_size=10");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to start scrape";
      setLastError(`${stateCode}: ${message}`);
    } finally {
      setScraping(null);
    }
  }

  const prog = progress as Record<string, unknown> | null;
  const isActive = !!activeJobId;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Scrape</h1>

      {lastError && (
        <Card className="mb-6 border-red-200 bg-red-50">
          <CardContent className="pt-4">
            <p className="text-sm text-red-700">{lastError}</p>
          </CardContent>
        </Card>
      )}

      {isActive && (
        <Card className="mb-6 border-blue-200 bg-blue-50">
          <CardHeader>
            <CardTitle className="text-sm">
              Scraping {activeJob?.state_code ?? "..."}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Progress
              value={
                prog
                  ? Number(prog.documents_processed ?? 0)
                  : activeJob?.status === "completed"
                    ? 100
                    : 10
              }
              className="mb-2"
            />
            <p className="text-sm text-muted-foreground">
              Status: <strong>{activeJob?.status ?? "pending"}</strong>
              {activeJob && activeJob.documents_found > 0 && (
                <span>
                  {" "}
                  — {activeJob.documents_processed} of{" "}
                  {activeJob.documents_found} documents processed
                </span>
              )}
              {activeJob?.status === "pending" && (
                <span> — Waiting for worker...</span>
              )}
              {activeJob?.status === "running" && (
                <span> — Scraping in progress...</span>
              )}
              {activeJob?.status === "completed" && <span> — Done!</span>}
            </p>
          </CardContent>
        </Card>
      )}

      <h2 className="text-lg font-semibold mb-3">Tier 1 States</h2>
      <div className="grid gap-3 md:grid-cols-5 mb-6">
        {STATES.filter((s) => s.tier === 1).map((s) => (
          <Card key={s.code}>
            <CardContent className="pt-4 text-center">
              <p className="font-bold">{s.name}</p>
              <p className="text-xs text-muted-foreground mb-2">{s.code}</p>
              <Button
                size="sm"
                onClick={() => triggerScrape(s.code)}
                disabled={scraping === s.code || isActive}
              >
                {scraping === s.code ? "Starting..." : "Scrape"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <h2 className="text-lg font-semibold mb-3">Tier 2 States</h2>
      <div className="grid gap-3 md:grid-cols-5 mb-8">
        {STATES.filter((s) => s.tier === 2).map((s) => (
          <Card key={s.code}>
            <CardContent className="pt-4 text-center">
              <p className="font-bold">{s.name}</p>
              <p className="text-xs text-muted-foreground mb-2">{s.code}</p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => triggerScrape(s.code)}
                disabled={scraping === s.code || isActive}
              >
                {scraping === s.code ? "Starting..." : "Scrape"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <h2 className="text-lg font-semibold mb-3">Scrape History</h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>State</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Found</TableHead>
            <TableHead>Processed</TableHead>
            <TableHead>Failed</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs?.items.map((job) => (
            <TableRow key={job.id}>
              <TableCell className="font-bold">{job.state_code}</TableCell>
              <TableCell>
                <Badge variant={statusBadgeVariant(job.status)}>
                  {job.status}
                </Badge>
              </TableCell>
              <TableCell>{job.documents_found}</TableCell>
              <TableCell>{job.documents_processed}</TableCell>
              <TableCell>{job.documents_failed}</TableCell>
              <TableCell className="text-xs">
                {new Date(job.created_at).toLocaleString()}
              </TableCell>
            </TableRow>
          ))}
          {(!jobs?.items || jobs.items.length === 0) && (
            <TableRow>
              <TableCell
                colSpan={6}
                className="text-center text-muted-foreground py-8"
              >
                No scrape jobs yet
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
