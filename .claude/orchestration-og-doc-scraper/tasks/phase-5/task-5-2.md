# Task 5.2: Search & Browse Interface

## Objective

Implement the main wells search/browse page with a DataTable (TanStack Table via shadcn/ui), full-text search bar, filter dropdowns (state, operator, document type, date range, status), URL-synced query params, server-side pagination, and a slide-out well detail side panel. Also implement a parallel documents browse page with similar functionality.

## Context

This is the primary data exploration interface. Users land here to search for wells by API number, operator name, or free text, then drill into individual well records. The search hits PostgreSQL full-text search (tsvector/tsquery) through FastAPI endpoints built in Phase 3 (Task 3.1). This task depends on Task 5.1 for the layout shell, API client, and type definitions.

## Dependencies

- Task 5.1 - Frontend foundation (layout, API client, types)
- Task 3.1 - Backend CRUD/search API endpoints (`GET /api/v1/wells`, `GET /api/v1/wells/{api_number}`, `GET /api/v1/documents`)

## Blocked By

- 5.1, 3.1

## Research Findings

Key findings from research files relevant to this task:

- From `dashboard-map-implementation.md` Section 3: shadcn/ui Data Table (built on TanStack Table) is the recommended table component. Server-side pagination, sorting, and filtering are essential for large datasets.
- From `dashboard-map-implementation.md` Section 3.2: Column definitions support custom renderers -- Badge for document types, Progress bars for confidence scores, Link for API numbers, DropdownMenu for row actions.
- From `nextjs-dashboard` skill: Client components should call through the rewrite proxy (`/api/...`) using SWR. DataTable pagination state syncs with URL search params for bookmarkability.
- From `og-scraper-architecture` skill: API pagination pattern is `?page=1&page_size=50`. Sorting: `?sort_by=api_number&sort_dir=asc`. Full-text: `?q=permian+basin`.
- From `og-scraper-architecture` skill: Wells table columns include API number (VARCHAR 14), well_name, operator (FK), state_code, county, status (enum), latitude, longitude.

## Implementation Plan

### Step 1: Create Data Fetching Hooks

Build SWR-based hooks for wells and documents that accept filter/pagination/sort parameters and construct the correct query strings.

```typescript
// frontend/src/hooks/use-wells.ts
'use client';

import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import type { Well, PaginatedResponse } from '@/lib/types';

export interface WellFilters {
  q?: string;
  state?: string;
  operator?: string;
  status?: string;
  county?: string;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
}

export function useWells(filters: WellFilters) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== null) {
      params.set(key, String(value));
    }
  });

  const queryString = params.toString();
  const key = `/api/v1/wells${queryString ? `?${queryString}` : ''}`;

  return useSWR<PaginatedResponse<Well>>(key, fetcher);
}
```

Create a similar `useDocuments` hook:

```typescript
// frontend/src/hooks/use-documents.ts
// Same pattern, hitting GET /api/v1/documents with doc_type, date_from, date_to filters
```

Also create a hook for fetching a single well with its documents:

```typescript
// frontend/src/hooks/use-well-detail.ts
import useSWR from 'swr';
import { fetcher } from '@/lib/api';

export function useWellDetail(apiNumber: string | null) {
  return useSWR(
    apiNumber ? `/api/v1/wells/${apiNumber}` : null,
    fetcher,
  );
}
```

### Step 2: Create Well Filters Component

A filter bar above the table with dropdowns and a search input. Filter state syncs with URL search params using `useSearchParams` and `useRouter`.

```typescript
// frontend/src/components/wells/well-filters.tsx
'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Search, X } from 'lucide-react';

const STATES = [
  { code: 'TX', name: 'Texas' },
  { code: 'NM', name: 'New Mexico' },
  { code: 'ND', name: 'North Dakota' },
  { code: 'OK', name: 'Oklahoma' },
  { code: 'CO', name: 'Colorado' },
  { code: 'WY', name: 'Wyoming' },
  { code: 'LA', name: 'Louisiana' },
  { code: 'PA', name: 'Pennsylvania' },
  { code: 'CA', name: 'California' },
  { code: 'AK', name: 'Alaska' },
];

const WELL_STATUSES = [
  'active', 'inactive', 'plugged', 'permitted',
  'drilling', 'completed', 'shut_in', 'temporarily_abandoned',
];
```

The filter component should:
1. Read initial values from `useSearchParams()`
2. On change, update URL search params via `router.replace()` with `{ scroll: false }`
3. Include a "Clear Filters" button that resets all params
4. Debounce the search input (300ms) before updating the URL

### Step 3: Create DataTable Column Definitions

Define column configurations for the wells table with custom cell renderers.

```typescript
// frontend/src/app/(dashboard)/wells/columns.tsx
'use client';

import { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { MoreHorizontal, ArrowUpDown } from 'lucide-react';
import type { Well } from '@/lib/types';

export const wellColumns: ColumnDef<Well>[] = [
  {
    accessorKey: 'api_number',
    header: ({ column }) => (
      <Button
        variant="ghost"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
      >
        API Number
        <ArrowUpDown className="ml-2 h-4 w-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="font-mono text-sm">{row.getValue('api_number')}</span>
    ),
  },
  {
    accessorKey: 'well_name',
    header: 'Well Name',
  },
  {
    accessorKey: 'operator_name',
    header: 'Operator',
  },
  {
    accessorKey: 'state_code',
    header: 'State',
    cell: ({ row }) => <Badge variant="outline">{row.getValue('state_code')}</Badge>,
  },
  {
    accessorKey: 'county',
    header: 'County',
  },
  {
    accessorKey: 'status',
    header: 'Status',
    cell: ({ row }) => {
      const status = row.getValue('status') as string;
      const variant = status === 'active' ? 'default' : 'secondary';
      return <Badge variant={variant}>{status}</Badge>;
    },
  },
  {
    accessorKey: 'doc_count',
    header: 'Documents',
    cell: ({ row }) => <span className="text-center">{row.getValue('doc_count')}</span>,
  },
  {
    id: 'actions',
    cell: ({ row }) => (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-8 w-8 p-0">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem>View Details</DropdownMenuItem>
          <DropdownMenuItem>View on Map</DropdownMenuItem>
          <DropdownMenuItem>View Documents</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    ),
  },
];
```

### Step 4: Build Wells Page

The main wells page combines filters, DataTable, and pagination. It reads query params from the URL to restore filter/page state on refresh.

```typescript
// frontend/src/app/(dashboard)/wells/page.tsx
'use client';

import { useSearchParams } from 'next/navigation';
import { wellColumns } from './columns';
import { useWells } from '@/hooks/use-wells';
import { WellFilters } from '@/components/wells/well-filters';
import { WellDetailPanel } from '@/components/wells/well-detail-panel';
import { DataTable } from '@/components/ui/data-table';
import { useState } from 'react';
import type { Well } from '@/lib/types';

export default function WellsPage() {
  const searchParams = useSearchParams();
  const [selectedWell, setSelectedWell] = useState<Well | null>(null);

  const filters = {
    q: searchParams.get('q') || undefined,
    state: searchParams.get('state') || undefined,
    operator: searchParams.get('operator') || undefined,
    status: searchParams.get('status') || undefined,
    page: Number(searchParams.get('page')) || 1,
    page_size: Number(searchParams.get('page_size')) || 50,
    sort_by: searchParams.get('sort_by') || 'api_number',
    sort_dir: (searchParams.get('sort_dir') as 'asc' | 'desc') || 'asc',
  };

  const { data, isLoading } = useWells(filters);

  return (
    <div className="flex h-full">
      <div className="flex-1 space-y-4">
        <h1 className="text-2xl font-bold">Wells</h1>
        <WellFilters />
        <DataTable
          columns={wellColumns}
          data={data?.results ?? []}
          pageCount={Math.ceil((data?.total ?? 0) / (filters.page_size))}
          isLoading={isLoading}
          onRowClick={(row) => setSelectedWell(row)}
        />
        <div className="text-sm text-muted-foreground">
          {data?.total ?? 0} results
        </div>
      </div>

      {selectedWell && (
        <WellDetailPanel
          well={selectedWell}
          onClose={() => setSelectedWell(null)}
        />
      )}
    </div>
  );
}
```

### Step 5: Build Well Detail Side Panel

A slide-out panel on the right that shows full well details and tabbed sub-sections for documents, production data, and permits.

```typescript
// frontend/src/components/wells/well-detail-panel.tsx
'use client';

import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { X } from 'lucide-react';
import type { Well, Document } from '@/lib/types';

interface WellDetailPanelProps {
  well: Well;
  onClose: () => void;
}

export function WellDetailPanel({ well, onClose }: WellDetailPanelProps) {
  // Fetch full well detail with associated documents
  const { data: wellDetail } = useSWR(
    `/api/v1/wells/${well.api_number}`,
    fetcher,
  );

  return (
    <div className="w-96 border-l bg-background">
      <div className="flex items-center justify-between p-4 border-b">
        <h2 className="text-lg font-bold truncate">{well.well_name}</h2>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="h-[calc(100vh-8rem)]">
        <div className="p-4 space-y-4">
          {/* Well info fields: API Number, Operator, State, County, Status, Coordinates */}
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">API Number</dt>
            <dd className="font-mono">{well.api_number}</dd>
            <dt className="text-muted-foreground">Operator</dt>
            <dd>{well.operator_name}</dd>
            <dt className="text-muted-foreground">State</dt>
            <dd>{well.state_code}</dd>
            <dt className="text-muted-foreground">County</dt>
            <dd>{well.county}</dd>
            <dt className="text-muted-foreground">Status</dt>
            <dd><Badge>{well.status}</Badge></dd>
            <dt className="text-muted-foreground">Coordinates</dt>
            <dd className="text-xs">{well.latitude}, {well.longitude}</dd>
          </dl>

          {/* Tabbed sections */}
          <Tabs defaultValue="documents" className="mt-4">
            <TabsList className="w-full">
              <TabsTrigger value="documents" className="flex-1">Documents</TabsTrigger>
              <TabsTrigger value="production" className="flex-1">Production</TabsTrigger>
            </TabsList>
            <TabsContent value="documents">
              {/* List of documents linked to this well */}
              {/* Each item: doc_type badge, date, confidence, link to view */}
            </TabsContent>
            <TabsContent value="production">
              {/* Production data summary from extracted_data */}
            </TabsContent>
          </Tabs>
        </div>
      </ScrollArea>
    </div>
  );
}
```

### Step 6: Build Documents Browse Page

A separate page for browsing all documents across wells. Similar structure to the wells page but with document-specific columns and filters.

```typescript
// frontend/src/app/(dashboard)/documents/page.tsx
// Similar pattern to wells page but uses document columns:
// - Document ID, API Number (from well), Doc Type (badge), Status (badge),
//   Confidence (progress bar + percentage), Scraped Date, Actions
```

Document column definitions should include a confidence score renderer:

```typescript
// frontend/src/app/(dashboard)/documents/columns.tsx
{
  accessorKey: 'confidence_score',
  header: 'Confidence',
  cell: ({ row }) => {
    const score = row.getValue('confidence_score') as number;
    const color = score >= 0.85 ? 'bg-green-500' : score >= 0.50 ? 'bg-yellow-500' : 'bg-red-500';
    return (
      <div className="flex items-center gap-2">
        <Progress value={score * 100} className={`w-16 ${color}`} />
        <span className="text-xs">{(score * 100).toFixed(0)}%</span>
      </div>
    );
  },
},
```

### Step 7: Add Empty States and Loading Skeletons

For each page, handle:
- **Loading state**: Show skeleton placeholders in the table using shadcn/ui Skeleton
- **Empty state**: Show a centered message with an icon when no results match
- **Error state**: Show an error message with retry button

```typescript
// frontend/src/components/ui/empty-state.tsx
import { SearchX } from 'lucide-react';

export function EmptyState({ message = 'No results found' }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
      <SearchX className="h-12 w-12 mb-4" />
      <p className="text-lg">{message}</p>
    </div>
  );
}
```

## Files to Create

- `frontend/src/hooks/use-wells.ts` - SWR hook for wells search/filter
- `frontend/src/hooks/use-documents.ts` - SWR hook for documents search/filter
- `frontend/src/hooks/use-well-detail.ts` - SWR hook for single well with documents
- `frontend/src/app/(dashboard)/wells/page.tsx` - Wells list page
- `frontend/src/app/(dashboard)/wells/columns.tsx` - Well DataTable column definitions
- `frontend/src/components/wells/well-filters.tsx` - Filter bar with search, dropdowns, date range
- `frontend/src/components/wells/well-detail-panel.tsx` - Slide-out well detail panel with tabs
- `frontend/src/app/(dashboard)/documents/page.tsx` - Documents list page
- `frontend/src/app/(dashboard)/documents/columns.tsx` - Document DataTable column definitions
- `frontend/src/components/documents/document-filters.tsx` - Document-specific filters
- `frontend/src/components/ui/empty-state.tsx` - Reusable empty state component

## Files to Modify

- `frontend/src/components/ui/data-table.tsx` - Extend with `onRowClick` prop, loading skeleton, pagination controls synchronized with URL params

## Contracts

### Provides (for downstream tasks)

- **Wells page**: Route `/wells` with DataTable, filters, and side panel
- **Documents page**: Route `/documents` with DataTable and filters
- **Well detail panel**: `<WellDetailPanel well={well} onClose={fn} />` reusable component (also used in Task 5.3 map)
- **Data hooks**: `useWells(filters)`, `useDocuments(filters)`, `useWellDetail(apiNumber)` for shared data fetching
- **Filter components**: `<WellFilters />` and `<DocumentFilters />` with URL-synced state

### Consumes (from upstream tasks)

- Task 5.1: Layout shell, API client (`@/lib/api`), type definitions (`@/lib/types`), shadcn/ui components
- Task 3.1: `GET /api/v1/wells` (paginated, filtered, searchable), `GET /api/v1/wells/{api_number}` (detail with documents), `GET /api/v1/documents` (paginated, filtered)

## Acceptance Criteria

- [ ] Wells table displays paginated well data from the API
- [ ] Full-text search bar queries API and updates table results
- [ ] State filter dropdown narrows results to selected state
- [ ] Operator filter narrows results
- [ ] Status filter narrows results
- [ ] Filter state persists in URL query params (page refresh preserves filters)
- [ ] Clicking a well row opens the detail side panel on the right
- [ ] Side panel shows well info and tabbed documents list
- [ ] Closing the panel restores full-width table
- [ ] Pagination controls navigate between pages
- [ ] Sorting by column header sends sort params to API
- [ ] Documents page displays documents with type badges and confidence bars
- [ ] Empty state displayed when no results match
- [ ] Loading skeletons displayed while fetching data
- [ ] All pages render without console errors
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `frontend/src/__tests__/hooks/use-wells.test.ts`
- Test cases:
  - [ ] `useWells` constructs correct URL with all filter params
  - [ ] `useWells` omits empty/null filter params from URL
  - [ ] `useWellDetail` returns null key when apiNumber is null (no fetch)

- Test file: `frontend/src/__tests__/components/well-filters.test.tsx`
- Test cases:
  - [ ] Filter component renders all dropdowns
  - [ ] Changing state dropdown updates URL search params
  - [ ] Search input debounces before updating URL
  - [ ] Clear filters button removes all params

### Browser Testing (Playwright MCP)

- Start: `cd frontend && npm run dev` (ensure backend is running with seed data)
- Navigate to: `http://localhost:3000/wells`
- Actions:
  - Verify table loads with well data
  - Type "permian" in search bar, wait for debounce, verify table updates
  - Select "TX" from state filter, verify only Texas wells shown
  - Click a table row, verify side panel slides in from right
  - Verify side panel shows API number, operator, status, documents tab
  - Click X to close panel, verify it disappears
  - Click page 2 in pagination, verify URL updates and new data loads
  - Refresh page, verify filters are restored from URL
  - Navigate to `/documents`, verify documents table loads
- Verify: No console errors on either page
- User-emulating flow:
  1. User lands on `/wells`
  2. Types operator name in search bar
  3. Selects state from dropdown
  4. Scans results in table
  5. Clicks a well of interest
  6. Reviews well details in side panel
  7. Clicks "View Documents" tab in panel to see associated docs
- Screenshot: Wells page with table data, side panel open, filters applied

### Build/Lint/Type Checks

- [ ] `npm run build` succeeds
- [ ] `npx tsc --noEmit` passes
- [ ] No TypeScript errors in new files

## Skills to Read

- `nextjs-dashboard` - DataTable pattern, SWR data fetching, column definitions with custom renderers
- `og-scraper-architecture` - API query patterns, pagination format, well/document schemas

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` - Section 3 (Search & Browse Interface), Section 3.2 (Data Table Component)

## Git

- Branch: `feat/5.2-search-browse`
- Commit message prefix: `Task 5.2:`
