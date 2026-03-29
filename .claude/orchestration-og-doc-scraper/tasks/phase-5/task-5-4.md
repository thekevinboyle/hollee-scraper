# Task 5.4: Scrape Trigger & Progress

## Objective

Implement the scraping control panel page with a grid of state-specific "Scrape" buttons, a "Scrape All" button, real-time SSE progress display (percentage bar, current stage, documents found/processed, elapsed time, error log), and a scrape history table showing past jobs with status and timestamps.

## Context

Scraping is on-demand only (DISCOVERY D3, D14). Users trigger scrapes from the dashboard and watch progress in real time. The frontend sends a `POST /api/v1/scrape` to the FastAPI backend (built in Task 3.2), which enqueues a Huey task and returns a job ID immediately. The frontend then opens an SSE connection directly to FastAPI (bypassing the Next.js rewrite proxy, which may buffer the stream) to receive live progress events. This task builds the UI for that entire flow.

## Dependencies

- Task 5.1 - Frontend foundation (layout, API client, types)
- Task 3.2 - Scrape API endpoints (`POST /api/v1/scrape`, `GET /api/v1/scrape/jobs`, `GET /api/v1/scrape/jobs/{id}`, `GET /api/v1/scrape/jobs/{id}/events` SSE)

## Blocked By

- 5.1, 3.2

## Research Findings

Key findings from research files relevant to this task:

- From `dashboard-map-implementation.md` Section 1.3: SSE is the right choice for scraping progress (one-way server-to-client). Use native `EventSource` API, no extra library. SSE endpoints should connect directly to FastAPI (not through Next.js rewrite) since rewriting may buffer the stream.
- From `nextjs-dashboard` skill: SSE hook pattern -- `new EventSource(`http://localhost:8000/api/v1/scrape/jobs/${jobId}/events`)`. Must use `NEXT_PUBLIC_SSE_URL` environment variable (always `http://localhost:8000` from browser).
- From `nextjs-dashboard` skill: Progress data includes `status`, `docs_found`, `docs_downloaded`, `docs_processed`, `current_step`, `errors`, `progress_pct`.
- From `dashboard-map-implementation.md` Section 1.3: Production considerations -- set heartbeat events every ~15 seconds, handle `onerror` by closing the connection, clean up on component unmount.
- From `og-scraper-architecture` skill: SSE endpoint is `GET /api/v1/scrape/jobs/{id}/events`. Scrape is triggered via `POST /api/v1/scrape` with body `{ state_code: "TX" }` or `{ state_code: "all" }`. Job statuses: pending, running, completed, failed, cancelled.
- From `og-scraper-architecture` skill: 10 supported states -- Tier 1: TX, NM, ND, OK, CO. Tier 2: WY, LA, PA, CA, AK.

## Implementation Plan

### Step 1: Create SSE Hook

Build a reusable React hook that manages an EventSource connection for real-time scrape progress. This is the most critical piece -- SSE must bypass the Next.js rewrite proxy.

```typescript
// frontend/src/hooks/use-sse.ts
'use client';

import { useEffect, useState, useRef, useCallback } from 'react';

export interface SSEOptions {
  onMessage?: (event: MessageEvent) => void;
  onError?: (event: Event) => void;
  eventName?: string; // default: 'progress'
}

export function useSSE<T>(url: string | null, options: SSEOptions = {}) {
  const [data, setData] = useState<T | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!url) {
      setIsConnected(false);
      return;
    }

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    const eventName = options.eventName || 'progress';
    eventSource.addEventListener(eventName, (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data) as T;
        setData(parsed);
        options.onMessage?.(event);
      } catch (e) {
        console.error('Failed to parse SSE data:', e);
      }
    });

    // Listen for 'complete' event to auto-close
    eventSource.addEventListener('complete', (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data) as T;
        setData(parsed);
      } catch (e) {
        // ignore
      }
      eventSource.close();
      setIsConnected(false);
    });

    eventSource.onerror = (event) => {
      setError('SSE connection error');
      setIsConnected(false);
      options.onError?.(event);
      eventSource.close();
    };

    return () => {
      eventSource.close();
      eventSourceRef.current = null;
      setIsConnected(false);
    };
  }, [url]); // Re-connect if URL changes

  const close = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setIsConnected(false);
  }, []);

  return { data, isConnected, error, close };
}
```

### Step 2: Create Scrape Progress Hook

A higher-level hook that wraps `useSSE` specifically for scrape job progress, managing the SSE URL construction and job lifecycle.

```typescript
// frontend/src/hooks/use-scrape-progress.ts
'use client';

import { useSSE } from './use-sse';
import type { ScrapeJob } from '@/lib/types';

export function useScrapeProgress(jobId: string | null) {
  // SSE connects directly to FastAPI, bypassing Next.js rewrite proxy
  const sseBaseUrl = process.env.NEXT_PUBLIC_SSE_URL || 'http://localhost:8000';
  const url = jobId ? `${sseBaseUrl}/api/v1/scrape/jobs/${jobId}/events` : null;

  return useSSE<ScrapeJob>(url, {
    eventName: 'progress',
  });
}
```

### Step 3: Create State Scrape Grid

A grid of cards, one per state, each showing the state name, last scrape date, document count, and a "Scrape" button. Include a prominent "Scrape All" button.

```typescript
// frontend/src/components/scrape/state-scrape-grid.tsx
'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PlayCircle, Loader2 } from 'lucide-react';

interface StateInfo {
  code: string;
  name: string;
  tier: 1 | 2;
  last_scraped_at: string | null;
  well_count: number;
  doc_count: number;
}

const STATES: StateInfo[] = [
  { code: 'TX', name: 'Texas', tier: 1, last_scraped_at: null, well_count: 0, doc_count: 0 },
  { code: 'NM', name: 'New Mexico', tier: 1, last_scraped_at: null, well_count: 0, doc_count: 0 },
  { code: 'ND', name: 'North Dakota', tier: 1, last_scraped_at: null, well_count: 0, doc_count: 0 },
  { code: 'OK', name: 'Oklahoma', tier: 1, last_scraped_at: null, well_count: 0, doc_count: 0 },
  { code: 'CO', name: 'Colorado', tier: 1, last_scraped_at: null, well_count: 0, doc_count: 0 },
  { code: 'WY', name: 'Wyoming', tier: 2, last_scraped_at: null, well_count: 0, doc_count: 0 },
  { code: 'LA', name: 'Louisiana', tier: 2, last_scraped_at: null, well_count: 0, doc_count: 0 },
  { code: 'PA', name: 'Pennsylvania', tier: 2, last_scraped_at: null, well_count: 0, doc_count: 0 },
  { code: 'CA', name: 'California', tier: 2, last_scraped_at: null, well_count: 0, doc_count: 0 },
  { code: 'AK', name: 'Alaska', tier: 2, last_scraped_at: null, well_count: 0, doc_count: 0 },
];

interface StateScrapeGridProps {
  onScrapeState: (stateCode: string) => void;
  onScrapeAll: () => void;
  activeJobs: Record<string, string>; // stateCode -> jobId
  stateStats?: Record<string, { well_count: number; doc_count: number; last_scraped_at: string | null }>;
}

export function StateScrapeGrid({ onScrapeState, onScrapeAll, activeJobs, stateStats }: StateScrapeGridProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">States</h2>
        <Button onClick={onScrapeAll} disabled={Object.keys(activeJobs).length > 0}>
          <PlayCircle className="h-4 w-4 mr-2" />
          Scrape All States
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {STATES.map((state) => {
          const stats = stateStats?.[state.code];
          const isActive = state.code in activeJobs;

          return (
            <Card key={state.code} className={isActive ? 'border-primary' : ''}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{state.code}</CardTitle>
                  <Badge variant={state.tier === 1 ? 'default' : 'secondary'}>
                    Tier {state.tier}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">{state.name}</p>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground space-y-1 mb-3">
                  <p>{stats?.well_count ?? 0} wells</p>
                  <p>{stats?.doc_count ?? 0} documents</p>
                  <p>
                    {stats?.last_scraped_at
                      ? `Last: ${new Date(stats.last_scraped_at).toLocaleDateString()}`
                      : 'Never scraped'}
                  </p>
                </div>
                <Button
                  size="sm"
                  className="w-full"
                  onClick={() => onScrapeState(state.code)}
                  disabled={isActive}
                >
                  {isActive ? (
                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Running</>
                  ) : (
                    <><PlayCircle className="h-4 w-4 mr-2" /> Scrape</>
                  )}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
```

### Step 4: Create Scrape Progress Component

A detailed real-time progress display for an active scrape job. Shows a progress bar, current stage, document counts, elapsed time, and a scrolling error log.

```typescript
// frontend/src/components/scrape/scrape-progress.tsx
'use client';

import { useScrapeProgress } from '@/hooks/use-scrape-progress';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { CheckCircle, XCircle, Loader2, Clock, AlertTriangle } from 'lucide-react';
import { useEffect, useState } from 'react';

interface ScrapeProgressProps {
  jobId: string;
  stateCode: string;
  onComplete?: () => void;
}

export function ScrapeProgress({ jobId, stateCode, onComplete }: ScrapeProgressProps) {
  const { data: progress, isConnected, error } = useScrapeProgress(jobId);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [startTime] = useState(Date.now());

  // Elapsed time timer
  useEffect(() => {
    if (!isConnected && progress?.status !== 'running') return;
    const interval = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [isConnected, progress?.status, startTime]);

  // Notify parent when job completes
  useEffect(() => {
    if (progress?.status === 'completed' || progress?.status === 'failed') {
      onComplete?.();
    }
  }, [progress?.status, onComplete]);

  const formatElapsed = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const statusIcon = {
    pending: <Clock className="h-4 w-4 text-muted-foreground" />,
    running: <Loader2 className="h-4 w-4 animate-spin text-primary" />,
    completed: <CheckCircle className="h-4 w-4 text-green-500" />,
    failed: <XCircle className="h-4 w-4 text-red-500" />,
    cancelled: <XCircle className="h-4 w-4 text-muted-foreground" />,
  };

  return (
    <Card className="mt-4">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {statusIcon[progress?.status ?? 'pending']}
            <CardTitle className="text-base">
              Scraping {stateCode}
            </CardTitle>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="h-3 w-3" />
            {formatElapsed(elapsedSeconds)}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Progress bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-sm">
            <span>{progress?.current_step ?? 'Initializing...'}</span>
            <span>{progress?.progress_pct ?? 0}%</span>
          </div>
          <Progress value={progress?.progress_pct ?? 0} />
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-2 text-center text-sm">
          <div>
            <p className="text-lg font-bold">{progress?.docs_found ?? 0}</p>
            <p className="text-xs text-muted-foreground">Found</p>
          </div>
          <div>
            <p className="text-lg font-bold">{progress?.docs_downloaded ?? 0}</p>
            <p className="text-xs text-muted-foreground">Downloaded</p>
          </div>
          <div>
            <p className="text-lg font-bold">{progress?.docs_processed ?? 0}</p>
            <p className="text-xs text-muted-foreground">Processed</p>
          </div>
        </div>

        {/* Error log (if any) */}
        {progress?.errors && progress.errors.length > 0 && (
          <>
            <Separator />
            <div>
              <div className="flex items-center gap-1 text-sm text-yellow-600 mb-1">
                <AlertTriangle className="h-3 w-3" />
                {progress.errors.length} error(s)
              </div>
              <ScrollArea className="h-32">
                {progress.errors.map((err, i) => (
                  <p key={i} className="text-xs text-muted-foreground py-1 border-b last:border-0">
                    {err.message}
                  </p>
                ))}
              </ScrollArea>
            </div>
          </>
        )}

        {/* Connection error */}
        {error && (
          <p className="text-sm text-red-500">{error}</p>
        )}
      </CardContent>
    </Card>
  );
}
```

### Step 5: Create Scrape History Component

A table of past scrape jobs fetched from `GET /api/v1/scrape/jobs`, showing status, state, duration, document counts, and timestamps.

```typescript
// frontend/src/components/scrape/scrape-history.tsx
'use client';

import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { CheckCircle, XCircle, Clock, Loader2 } from 'lucide-react';
import type { ScrapeJob } from '@/lib/types';

export function ScrapeHistory() {
  const { data: jobs } = useSWR<ScrapeJob[]>(
    '/api/v1/scrape/jobs?page_size=20',
    fetcher,
    { refreshInterval: 5000 }, // Refresh every 5 seconds while jobs may be running
  );

  const statusBadge = (status: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
      completed: 'default',
      running: 'secondary',
      failed: 'destructive',
      pending: 'outline',
      cancelled: 'outline',
    };
    return <Badge variant={variants[status] || 'outline'}>{status}</Badge>;
  };

  return (
    <div className="mt-8">
      <h2 className="text-xl font-bold mb-4">Scrape History</h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>State</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Documents</TableHead>
            <TableHead>Started</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Errors</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs?.map((job) => (
            <TableRow key={job.id}>
              <TableCell className="font-medium">{job.state_code}</TableCell>
              <TableCell>{statusBadge(job.status)}</TableCell>
              <TableCell>
                {job.docs_found} found / {job.docs_processed} processed
              </TableCell>
              <TableCell>
                {new Date(job.started_at).toLocaleString()}
              </TableCell>
              <TableCell>
                {job.completed_at
                  ? formatDuration(job.started_at, job.completed_at)
                  : 'In progress'}
              </TableCell>
              <TableCell>
                {job.errors?.length > 0 ? (
                  <Badge variant="destructive">{job.errors.length}</Badge>
                ) : (
                  <span className="text-muted-foreground">0</span>
                )}
              </TableCell>
            </TableRow>
          ))}
          {(!jobs || jobs.length === 0) && (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                No scrape jobs yet. Click a state button above to start.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

function formatDuration(start: string, end: string): string {
  const seconds = Math.floor((new Date(end).getTime() - new Date(start).getTime()) / 1000);
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}
```

### Step 6: Build the Scrape Page

The main scrape management page that orchestrates the state grid, active progress displays, and history table.

```typescript
// frontend/src/app/(dashboard)/scrape/page.tsx
'use client';

import { useState, useCallback } from 'react';
import useSWR, { mutate } from 'swr';
import { api, fetcher } from '@/lib/api';
import { StateScrapeGrid } from '@/components/scrape/state-scrape-grid';
import { ScrapeProgress } from '@/components/scrape/scrape-progress';
import { ScrapeHistory } from '@/components/scrape/scrape-history';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/components/ui/use-toast';

export default function ScrapePage() {
  const { toast } = useToast();
  // Track active jobs: stateCode -> jobId
  const [activeJobs, setActiveJobs] = useState<Record<string, string>>({});

  // Fetch state-level stats for the grid
  const { data: stateStats } = useSWR('/api/v1/stats', fetcher);

  const handleScrapeState = useCallback(async (stateCode: string) => {
    try {
      const response = await api.post<{ id: string }>('/scrape', {
        state_code: stateCode,
      });
      setActiveJobs(prev => ({ ...prev, [stateCode]: response.id }));
      toast({
        title: `Scrape started`,
        description: `Started scraping ${stateCode}`,
      });
    } catch (err) {
      toast({
        title: 'Scrape failed to start',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  }, [toast]);

  const handleScrapeAll = useCallback(async () => {
    const states = ['TX', 'NM', 'ND', 'OK', 'CO', 'WY', 'LA', 'PA', 'CA', 'AK'];
    for (const state of states) {
      await handleScrapeState(state);
    }
  }, [handleScrapeState]);

  const handleJobComplete = useCallback((stateCode: string) => {
    setActiveJobs(prev => {
      const next = { ...prev };
      delete next[stateCode];
      return next;
    });
    // Refresh stats and history
    mutate('/api/v1/stats');
    mutate('/api/v1/scrape/jobs?page_size=20');
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Scrape Management</h1>

      <StateScrapeGrid
        onScrapeState={handleScrapeState}
        onScrapeAll={handleScrapeAll}
        activeJobs={activeJobs}
        stateStats={stateStats?.by_state}
      />

      {/* Active progress displays */}
      {Object.entries(activeJobs).map(([stateCode, jobId]) => (
        <ScrapeProgress
          key={jobId}
          jobId={jobId}
          stateCode={stateCode}
          onComplete={() => handleJobComplete(stateCode)}
        />
      ))}

      <Separator />

      <ScrapeHistory />
    </div>
  );
}
```

### Step 7: Add Toast Notifications

Ensure the toast provider is set up in the layout for scrape start/complete/error notifications. If not already present from Task 5.1, add the Toaster component to the dashboard layout.

```typescript
// Add to frontend/src/app/(dashboard)/layout.tsx:
import { Toaster } from '@/components/ui/toaster';
// ... inside the layout JSX:
<Toaster />
```

## Files to Create

- `frontend/src/hooks/use-sse.ts` - Generic SSE hook with EventSource management
- `frontend/src/hooks/use-scrape-progress.ts` - Scrape-specific SSE progress hook
- `frontend/src/app/(dashboard)/scrape/page.tsx` - Scrape management page
- `frontend/src/components/scrape/state-scrape-grid.tsx` - Grid of state cards with scrape buttons
- `frontend/src/components/scrape/scrape-progress.tsx` - Real-time progress display with bar and stats
- `frontend/src/components/scrape/scrape-history.tsx` - Table of past scrape jobs

## Files to Modify

- `frontend/src/app/(dashboard)/layout.tsx` - Add `<Toaster />` for toast notifications (if not already present)

## Contracts

### Provides (for downstream tasks)

- **Scrape page**: Route `/scrape` with state grid, active progress, and history
- **SSE hook**: `useSSE<T>(url, options)` -- generic, reusable for any SSE endpoint
- **Scrape progress hook**: `useScrapeProgress(jobId)` -- returns `{ data: ScrapeJob, isConnected, error }`
- **Progress component**: `<ScrapeProgress jobId={id} stateCode={code} onComplete={fn} />` -- self-contained real-time progress display
- **State grid component**: `<StateScrapeGrid onScrapeState={fn} onScrapeAll={fn} activeJobs={map} />`

### Consumes (from upstream tasks)

- Task 5.1: Layout shell, API client (`api.post`), type definitions (`ScrapeJob`, `ScrapeJobStatus`), shadcn/ui components (Button, Card, Progress, Badge, Table, ScrollArea, Separator, Toast)
- Task 3.2: `POST /api/v1/scrape` (trigger, returns `{ id: string }`), `GET /api/v1/scrape/jobs` (history list), `GET /api/v1/scrape/jobs/{id}/events` (SSE stream with `progress` and `complete` events)

## Acceptance Criteria

- [ ] State grid shows all 10 states with Scrape buttons, organized by tier
- [ ] Each state card shows well count, document count, and last scrape date
- [ ] Clicking "Scrape [State]" triggers `POST /api/v1/scrape` and button changes to "Running" with spinner
- [ ] SSE progress bar updates in real-time showing percentage, current stage, and counts
- [ ] Documents found/downloaded/processed counters update live
- [ ] Elapsed time ticks every second during active scrape
- [ ] Error log appears and scrolls when errors are reported
- [ ] When job completes, progress card shows green checkmark
- [ ] When job fails, progress card shows red X with error details
- [ ] "Scrape All" button triggers scrapes for all 10 states sequentially
- [ ] Scrape buttons are disabled while a job is running for that state
- [ ] Scrape history table shows past jobs with status badges, timestamps, durations
- [ ] History table refreshes periodically to show newly completed jobs
- [ ] Toast notifications appear on scrape start, completion, and failure
- [ ] SSE connects directly to FastAPI (not through Next.js rewrite)
- [ ] SSE connection is properly cleaned up on component unmount
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `frontend/src/__tests__/hooks/use-sse.test.ts`
- Test cases:
  - [ ] `useSSE` returns null data when URL is null
  - [ ] `useSSE` sets isConnected to true on EventSource open
  - [ ] `useSSE` parses JSON data from progress events
  - [ ] `useSSE` closes EventSource on unmount (cleanup)
  - [ ] `useSSE` sets error on EventSource error

- Test file: `frontend/src/__tests__/components/scrape-progress.test.tsx`
- Test cases:
  - [ ] `ScrapeProgress` renders progress bar with correct percentage
  - [ ] `ScrapeProgress` displays document counters
  - [ ] `ScrapeProgress` calls `onComplete` when status changes to completed
  - [ ] `ScrapeProgress` shows error log when errors are present

### API/Script Testing

- `POST /api/v1/scrape` with `{ "state_code": "PA" }` -- expect `{ "id": "<uuid>" }` response
- `GET /api/v1/scrape/jobs` -- expect array of scrape jobs
- Open `http://localhost:8000/api/v1/scrape/jobs/{id}/events` in browser -- expect SSE stream

### Browser Testing (Playwright MCP)

- Start: `cd frontend && npm run dev` (ensure backend is running)
- Navigate to: `http://localhost:3000/scrape`
- Actions:
  - Verify state grid renders with all 10 states (TX, NM, ND, OK, CO, WY, LA, PA, CA, AK)
  - Verify each state card shows well count and last scrape date
  - Click "Scrape PA" button
  - Verify button changes to "Running" with spinning icon
  - Verify progress bar appears below the grid
  - Verify percentage updates (may need to wait or use mock)
  - Verify documents found/downloaded/processed counters update
  - Verify elapsed time ticks
  - Wait for completion or timeout
  - Verify completed job appears in scrape history table
  - Verify history shows status badge, timestamp, and duration
- Verify: No console errors, SSE connection opens to FastAPI directly
- User-emulating flow:
  1. User navigates to Scrape page from sidebar
  2. Sees grid of 10 state cards
  3. Notices PA has been scraped before (if applicable)
  4. Clicks "Scrape CO" button
  5. Watches progress bar fill up in real-time
  6. Sees "12 documents found, 8 processed" updating live
  7. Job completes -- green checkmark appears
  8. Scrolls down to see the job in history table
  9. Clicks "Scrape All" to run all states
- Screenshot: State grid, active progress bar mid-scrape, completed job in history

### Build/Lint/Type Checks

- [ ] `npm run build` succeeds
- [ ] `npx tsc --noEmit` passes
- [ ] No TypeScript errors in SSE hooks or scrape components

## Skills to Read

- `nextjs-dashboard` - SSE EventSource pattern, SSE bypass for Next.js rewrite proxy, progress display components
- `fastapi-backend` - Scrape trigger endpoint, SSE event format, job status lifecycle
- `og-scraper-architecture` - Service architecture, scrape job model, supported states

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` - Section 1.3 (Real-Time Progress Updates: SSE), Section 5 (Scraping Control Panel)

## Git

- Branch: `feat/5.4-scrape-progress`
- Commit message prefix: `Task 5.4:`
