# Task 5.1: Frontend Foundation & Layout

## Objective

Set up the Next.js frontend project with shadcn/ui, Tailwind CSS, dark mode support, API proxy to FastAPI, and the base dashboard layout (sidebar navigation, header, and main content area). This task produces the shell that all other Phase 5 tasks build upon.

## Context

This is the first task in Phase 5 (Frontend Dashboard). The Next.js project skeleton was created in Task 1.1 (scaffolding), but it only has the bare `create-next-app` output. This task turns that skeleton into a functional dashboard shell with navigation, theming, and backend connectivity. All subsequent frontend tasks (5.2-5.5) depend on this layout and API client.

## Dependencies

- Task 1.1 - Project scaffolding (frontend directory, `package.json`, `Dockerfile`)

## Blocked By

- 1.1

## Research Findings

Key findings from research files relevant to this task:

- From `dashboard-map-implementation.md`: URL rewriting via `next.config.ts` is the recommended pattern for connecting Next.js to FastAPI. All API calls appear same-origin, eliminating CORS issues. In Docker Compose, the destination URL changes to `http://backend:8000/api/:path*`.
- From `dashboard-map-implementation.md`: SSE endpoints must bypass the Next.js rewrite proxy because rewrites may buffer the stream. The API client must support both proxied REST calls and direct SSE connections.
- From `nextjs-dashboard` skill: Dark mode uses `next-themes` with shadcn/ui CSS variables. ThemeProvider wraps the entire app with `attribute="class"` and `defaultTheme="system"`.
- From `nextjs-dashboard` skill: shadcn/ui Sidebar component provides fixed sidebar + main content layout out of the box.
- From `og-scraper-architecture` skill: Frontend runs on port 3000, backend on port 8000. No authentication required (DISCOVERY D7).

## Implementation Plan

### Step 1: Install Dependencies

Install all Node dependencies required for the full Phase 5 (not just this task). This avoids repeated installs across tasks.

```bash
cd frontend

# Install shadcn/ui (interactive init — select defaults, New York style, slate color)
npx shadcn@latest init

# Install shadcn/ui components needed across all Phase 5 tasks
npx shadcn@latest add button card input label badge tabs
npx shadcn@latest add table data-table dialog dropdown-menu
npx shadcn@latest add progress collapsible separator
npx shadcn@latest add select command popover calendar
npx shadcn@latest add sidebar sheet toast
npx shadcn@latest add skeleton scroll-area tooltip avatar

# Install map dependencies (for Task 5.3, but install now)
npm install leaflet react-leaflet supercluster use-supercluster
npm install -D @types/leaflet @types/supercluster

# Install PDF viewer (for Task 5.5, but install now)
npm install react-pdf

# Install data fetching
npm install swr

# Install dark mode
npm install next-themes

# Install icons
npm install lucide-react
```

### Step 2: Configure API Proxy

Create or update `frontend/next.config.ts` with URL rewriting rules that proxy `/api/*` requests to the FastAPI backend. Use an environment variable for the backend URL so it works in both local dev and Docker Compose.

```typescript
// frontend/next.config.ts
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/:path*`,
      },
    ];
  },
  // react-pdf requires this for the worker file
  webpack: (config) => {
    config.resolve.alias.canvas = false;
    return config;
  },
};

export default nextConfig;
```

Add to `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SSE_URL=http://localhost:8000
```

Add to `frontend/.env.docker`:
```
NEXT_PUBLIC_API_URL=http://backend:8000
NEXT_PUBLIC_SSE_URL=http://localhost:8000
```

Note: `NEXT_PUBLIC_SSE_URL` always points to `localhost:8000` because SSE connections are made from the browser (client-side), which cannot resolve Docker service names.

### Step 3: Create Theme Provider & Root Layout

Set up dark mode with `next-themes` and the root layout with `ThemeProvider`.

```typescript
// frontend/src/components/theme-provider.tsx
'use client';

import * as React from 'react';
import { ThemeProvider as NextThemesProvider } from 'next-themes';

export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
```

```typescript
// frontend/src/app/layout.tsx
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { ThemeProvider } from '@/components/theme-provider';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'O&G Document Scraper',
  description: 'Oil & Gas regulatory document scraping and analysis dashboard',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
```

### Step 4: Create API Client

Build a typed fetch wrapper in `frontend/src/lib/api.ts` that all components use for backend communication. This centralizes error handling, base URL resolution, and response typing.

```typescript
// frontend/src/lib/api.ts

const API_BASE = '/api/v1';

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body?: unknown,
  ) {
    super(`API Error ${status}: ${statusText}`);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, res.statusText, body);
  }

  return res.json();
}

export const api = {
  get: <T>(path: string, params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params)}` : '';
    return request<T>(`${path}${query}`);
  },

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),
};

// SWR fetcher for use with useSWR
export const fetcher = <T>(url: string): Promise<T> =>
  fetch(url).then((res) => {
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return res.json();
  });
```

### Step 5: Create TypeScript Types

Define shared TypeScript interfaces that mirror the FastAPI Pydantic response schemas. These are used across all Phase 5 components.

```typescript
// frontend/src/lib/types.ts

export interface Well {
  id: string;
  api_number: string;
  well_name: string;
  operator_name: string;
  state_code: string;
  county: string;
  latitude: number;
  longitude: number;
  status: WellStatus;
  doc_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type WellStatus =
  | 'active' | 'inactive' | 'plugged' | 'permitted'
  | 'drilling' | 'completed' | 'shut_in' | 'temporarily_abandoned' | 'unknown';

export interface Document {
  id: string;
  well_id: string;
  doc_type: DocumentType;
  status: DocumentStatus;
  file_path: string;
  file_hash: string;
  confidence_score: number;
  ocr_confidence: number | null;
  source_url: string;
  scraped_at: string;
  created_at: string;
}

export type DocumentType =
  | 'well_permit' | 'completion_report' | 'production_report'
  | 'spacing_order' | 'pooling_order' | 'plugging_report'
  | 'inspection_record' | 'incident_report' | 'other';

export type DocumentStatus =
  | 'discovered' | 'downloading' | 'downloaded'
  | 'classifying' | 'classified' | 'extracting' | 'extracted'
  | 'normalized' | 'stored' | 'flagged_for_review'
  | 'download_failed' | 'classification_failed' | 'extraction_failed';

export interface ExtractedData {
  id: string;
  document_id: string;
  data: Record<string, unknown>;
  field_confidence: Record<string, number>;
  data_type: string;
  extractor_used: string;
}

export interface ReviewItem {
  id: string;
  document_id: string;
  document: Document;
  extracted_data: ExtractedData;
  status: ReviewStatus;
  reason: string;
  corrections: Record<string, unknown> | null;
  created_at: string;
}

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'corrected';

export interface ScrapeJob {
  id: string;
  state_code: string;
  status: ScrapeJobStatus;
  docs_found: number;
  docs_downloaded: number;
  docs_processed: number;
  current_step: string;
  errors: Array<{ message: string; timestamp: string }>;
  progress_pct: number;
  started_at: string;
  completed_at: string | null;
}

export type ScrapeJobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  results: T[];
}

export interface DashboardStats {
  total_wells: number;
  total_documents: number;
  total_extracted: number;
  pending_review: number;
  avg_confidence: number;
  by_state: Record<string, { wells: number; documents: number }>;
  by_type: Record<string, number>;
}
```

### Step 6: Create Sidebar Navigation

Build the sidebar using shadcn/ui Sidebar component with navigation links to all dashboard sections.

```typescript
// frontend/src/components/layout/sidebar.tsx
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Search,
  Map,
  PlayCircle,
  ClipboardCheck,
  FileText,
  Settings,
} from 'lucide-react';
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
} from '@/components/ui/sidebar';

const navItems = [
  { title: 'Dashboard', href: '/', icon: LayoutDashboard },
  { title: 'Wells', href: '/wells', icon: Search },
  { title: 'Documents', href: '/documents', icon: FileText },
  { title: 'Map', href: '/map', icon: Map },
  { title: 'Scrape', href: '/scrape', icon: PlayCircle },
  { title: 'Review Queue', href: '/review', icon: ClipboardCheck },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="flex items-center gap-2 px-4 py-2">
          <span className="font-bold text-lg">O&G Scraper</span>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton asChild isActive={pathname === item.href}>
                    <Link href={item.href}>
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
```

### Step 7: Create Header with Theme Toggle

```typescript
// frontend/src/components/layout/header.tsx
'use client';

import { Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { Button } from '@/components/ui/button';
import { SidebarTrigger } from '@/components/ui/sidebar';

export function Header() {
  const { theme, setTheme } = useTheme();

  return (
    <header className="flex h-14 items-center gap-4 border-b bg-background px-6">
      <SidebarTrigger />
      <div className="flex-1" />
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      >
        <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
        <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        <span className="sr-only">Toggle theme</span>
      </Button>
    </header>
  );
}
```

### Step 8: Create Dashboard Layout with SidebarProvider

Wire the sidebar, header, and main content area together using shadcn/ui SidebarProvider.

```typescript
// frontend/src/app/(dashboard)/layout.tsx
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar';
import { AppSidebar } from '@/components/layout/sidebar';
import { Header } from '@/components/layout/header';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <Header />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
```

Use a route group `(dashboard)` so the sidebar layout applies to all pages. Move all page routes under `src/app/(dashboard)/`.

### Step 9: Create Dashboard Home Page

The home page shows summary statistics fetched from `GET /api/v1/stats`.

```typescript
// frontend/src/app/(dashboard)/page.tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default async function DashboardPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Wells</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">--</div>
          </CardContent>
        </Card>
        {/* Repeat for Total Documents, Pending Review, Avg Confidence */}
      </div>
    </div>
  );
}
```

For the initial task, the stats can show placeholder values ("--"). Once the backend is running with data, they will be fetched dynamically using SWR. Create a client component wrapper for that:

```typescript
// frontend/src/components/dashboard/stats-cards.tsx
'use client';

import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import type { DashboardStats } from '@/lib/types';
// ... render cards with live data
```

### Step 10: Verify Build & Dev Server

1. Run `npm run dev` and confirm the app starts on port 3000
2. Navigate to `http://localhost:3000` and verify the layout renders
3. Verify sidebar navigation links route correctly
4. Verify dark mode toggle works
5. Verify API proxy by checking `/api/v1/health` (if backend is running)

## Files to Create

- `frontend/src/components/theme-provider.tsx` - next-themes ThemeProvider wrapper
- `frontend/src/components/layout/sidebar.tsx` - App sidebar with navigation links
- `frontend/src/components/layout/header.tsx` - Header with theme toggle
- `frontend/src/app/(dashboard)/layout.tsx` - Dashboard layout with SidebarProvider
- `frontend/src/app/(dashboard)/page.tsx` - Dashboard home page with stat cards
- `frontend/src/components/dashboard/stats-cards.tsx` - Client component for live stats
- `frontend/src/lib/api.ts` - Typed API client and SWR fetcher
- `frontend/src/lib/types.ts` - Shared TypeScript interfaces
- `frontend/.env.local` - Local environment variables
- `frontend/.env.docker` - Docker environment variables

## Files to Modify

- `frontend/next.config.ts` - Add API proxy rewrite rules and webpack canvas alias
- `frontend/src/app/layout.tsx` - Wrap with ThemeProvider, add Inter font
- `frontend/src/app/globals.css` - Ensure shadcn/ui CSS variables are present
- `frontend/package.json` - Dependencies added via npm install

## Contracts

### Provides (for downstream tasks)

- **Layout shell**: `(dashboard)/layout.tsx` with sidebar + header + main content area. All page components render inside `<main>`.
- **API client**: `@/lib/api` exports `api.get<T>()`, `api.post<T>()`, `api.patch<T>()`, and `fetcher` for SWR.
- **Type definitions**: `@/lib/types` exports `Well`, `Document`, `ExtractedData`, `ReviewItem`, `ScrapeJob`, `PaginatedResponse<T>`, `DashboardStats`.
- **Theme provider**: Dark mode available via `useTheme()` from `next-themes`.
- **Sidebar navigation**: Links to `/wells`, `/documents`, `/map`, `/scrape`, `/review`.
- **Environment variables**: `NEXT_PUBLIC_API_URL` for rewrite proxy, `NEXT_PUBLIC_SSE_URL` for direct SSE connections.

### Consumes (from upstream tasks)

- Task 1.1: `frontend/` directory with `package.json` and initial Next.js project

## Acceptance Criteria

- [ ] `npm run dev` starts frontend on port 3000 without errors
- [ ] Layout renders with sidebar navigation containing 6 nav items
- [ ] All sidebar links navigate to correct routes without full page reload
- [ ] Dark mode toggle switches between light and dark themes
- [ ] API proxy correctly forwards `/api/v1/health` to `http://localhost:8000/api/v1/health` (when backend is running)
- [ ] shadcn/ui components render correctly (Button, Card, Sidebar, etc.)
- [ ] `npm run build` succeeds without TypeScript or lint errors
- [ ] All TypeScript types compile without errors

## Testing Protocol

### Unit/Integration Tests

- Test file: `frontend/src/__tests__/lib/api.test.ts`
- Test cases:
  - [ ] `api.get` constructs correct URL with query params
  - [ ] `api.post` sends JSON body with correct Content-Type header
  - [ ] `ApiError` is thrown for non-2xx responses
  - [ ] `fetcher` function resolves with JSON for 200 responses

### Browser Testing (Playwright MCP)

- Start: `cd frontend && npm run dev`
- Navigate to: `http://localhost:3000`
- Actions:
  - Verify sidebar renders with all 6 navigation items
  - Click each sidebar link, verify URL changes
  - Click dark mode toggle, verify theme switches
  - Resize viewport to mobile width, verify sidebar collapses
- Verify:
  - No console errors on any page
  - Layout is visually correct (sidebar on left, header on top, content area fills remaining space)
- Screenshot: Dashboard home page in both light and dark mode

### Build/Lint/Type Checks

- [ ] `npm run build` succeeds
- [ ] `npx tsc --noEmit` passes
- [ ] `npx eslint src/` passes (if ESLint is configured)

## Skills to Read

- `nextjs-dashboard` - Component patterns, shadcn/ui setup, dark mode, API proxy configuration, common pitfalls
- `og-scraper-architecture` - Project structure, service ports, frontend directory layout

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` - Section 1 (Next.js + FastAPI Integration), Section 6 (UI Component Library)

## Git

- Branch: `feat/5.1-frontend-foundation`
- Commit message prefix: `Task 5.1:`
