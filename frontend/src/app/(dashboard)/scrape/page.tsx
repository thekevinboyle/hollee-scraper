"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api, fetcher } from "@/lib/api";
import type { ScrapeJob, PaginatedResponse } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useSSE } from "@/hooks/use-sse";

const STATES = [
  { code: "TX", name: "Texas", tier: 1 },
  { code: "NM", name: "New Mexico", tier: 1 },
  { code: "ND", name: "North Dakota", tier: 1 },
  { code: "OK", name: "Oklahoma", tier: 1 },
  { code: "CO", name: "Colorado", tier: 1 },
  { code: "WY", name: "Wyoming", tier: 2 },
  { code: "LA", name: "Louisiana", tier: 2 },
  { code: "PA", name: "Pennsylvania", tier: 2 },
  { code: "CA", name: "California", tier: 2 },
  { code: "AK", name: "Alaska", tier: 2 },
];

export default function ScrapePage() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [scraping, setScraping] = useState<string | null>(null);

  const sseUrl = activeJobId
    ? `${process.env.NEXT_PUBLIC_SSE_URL || "http://localhost:8000"}/api/v1/scrape/jobs/${activeJobId}/events`
    : null;
  const { data: progress } = useSSE(sseUrl);

  const { data: jobs } = useSWR<PaginatedResponse<ScrapeJob>>(
    "/api/v1/scrape/jobs?page_size=10", fetcher, { refreshInterval: activeJobId ? 3000 : 0 }
  );

  async function triggerScrape(stateCode: string) {
    setScraping(stateCode);
    try {
      const job = await api.post<ScrapeJob>("/scrape/", { state_code: stateCode });
      setActiveJobId(job.id);
      mutate("/api/v1/scrape/jobs?page_size=10");
    } finally {
      setScraping(null);
    }
  }

  const prog = progress as Record<string, unknown> | null;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Scrape</h1>

      {activeJobId && prog && (
        <Card className="mb-6">
          <CardHeader><CardTitle className="text-sm">Scrape in Progress</CardTitle></CardHeader>
          <CardContent>
            <Progress value={Number(prog.progress_pct ?? 0)} className="mb-2" />
            <p className="text-sm text-muted-foreground">
              {String(prog.current_stage ?? "Starting...")} — {String(prog.docs_processed ?? 0)} documents processed
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
              <Button size="sm" onClick={() => triggerScrape(s.code)} disabled={scraping === s.code}>
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
              <Button size="sm" variant="outline" onClick={() => triggerScrape(s.code)} disabled={scraping === s.code}>
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
            <TableHead>Documents</TableHead>
            <TableHead>Started</TableHead>
            <TableHead>Completed</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs?.items.map((job) => (
            <TableRow key={job.id}>
              <TableCell className="font-bold">{job.state_code}</TableCell>
              <TableCell>
                <Badge variant={job.status === "completed" ? "default" : job.status === "failed" ? "destructive" : "secondary"}>
                  {job.status}
                </Badge>
              </TableCell>
              <TableCell>{job.docs_processed}</TableCell>
              <TableCell className="text-xs">{new Date(job.started_at).toLocaleString()}</TableCell>
              <TableCell className="text-xs">{job.completed_at ? new Date(job.completed_at).toLocaleString() : "-"}</TableCell>
            </TableRow>
          ))}
          {(!jobs?.items || jobs.items.length === 0) && (
            <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-8">No scrape jobs yet</TableCell></TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
