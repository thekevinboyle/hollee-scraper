---
name: nextjs-dashboard
description: Next.js dashboard with shadcn/ui, Leaflet map, and real-time SSE monitoring. Use when implementing UI components, map features, or frontend pages.
---

# Next.js Dashboard Frontend

## What It Is

A Next.js frontend dashboard for the Oil & Gas Document Scraper system. It provides:

- **Search and browse interface** for wells, documents, and extracted data
- **Interactive map** with well-level pins using Leaflet and OpenStreetMap (fully free)
- **Real-time scrape monitoring** via Server-Sent Events (SSE)
- **Review queue** for verifying low-confidence OCR data
- **Document viewer** for inline PDF preview alongside extracted fields

The dashboard connects to a FastAPI backend via URL rewriting proxy. It is a local-only, internal tool for 1-2 users with no authentication required (see DISCOVERY D7).

## When to Use This Skill

Use this skill when:

- Implementing dashboard pages or layout changes
- Building or modifying map features (pins, clustering, click-to-detail)
- Creating or updating UI components with shadcn/ui
- Integrating frontend API calls to the FastAPI backend
- Adding real-time progress display for scrape operations
- Working on the review queue or document viewer
- Setting up Docker Compose for the frontend service

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Framework | Next.js (App Router) | TypeScript, Server + Client Components |
| UI Library | shadcn/ui | Copy-into-repo model, Tailwind CSS styling |
| Styling | Tailwind CSS | Dark mode via CSS variables + next-themes |
| Map | Leaflet + react-leaflet | OpenStreetMap tiles (free, no API key) |
| Map Clustering | Supercluster via use-supercluster | Client-side clustering for 10K-50K markers |
| Data Table | @tanstack/react-table | Via shadcn/ui DataTable wrapper |
| PDF Viewer | react-pdf | Wrapper around Mozilla PDF.js |
| Data Fetching | SWR or fetch | SWR for client components, fetch for server components |
| Real-time | EventSource API (SSE) | Native browser API, no extra library |
| Testing | Playwright + React Testing Library | E2E flows + component tests |

## Authentication and Setup

**No authentication.** This is an internal tool (DISCOVERY D7). Anyone with local access can use it.

**Setup:**

```bash
# Initialize Next.js project with TypeScript and Tailwind
npx create-next-app@latest frontend --typescript --tailwind --app --src-dir

# Install shadcn/ui
npx shadcn@latest init

# Install required shadcn/ui components
npx shadcn@latest add button card input label badge tabs
npx shadcn@latest add table data-table dialog dropdown-menu
npx shadcn@latest add progress collapsible separator
npx shadcn@latest add select command popover calendar
npx shadcn@latest add sidebar sheet toast

# Install map dependencies
npm install leaflet react-leaflet supercluster use-supercluster
npm install -D @types/leaflet @types/supercluster

# Install PDF viewer
npm install react-pdf

# Install data fetching
npm install swr
```

**next.config.js -- API proxy to FastAPI:**

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*', // FastAPI backend
      },
    ];
  },
};

module.exports = nextConfig;
```

In Docker Compose, change destination to `http://backend:8000/api/:path*`.

## Key Patterns

### 1. Search and Browse Interface

The primary workflow is a search bar with filters feeding a paginated data table.

**Search bar with filters:**
- Full-text search input (queries PostgreSQL tsvector/tsquery via FastAPI)
- Filter dropdowns: state, operator, document type, status
- Date range picker using shadcn/ui Calendar
- Results count and export options

**DataTable with @tanstack/react-table:**

```typescript
'use client';
import { DataTable } from '@/components/ui/data-table';
import { columns } from './columns';

export function DocumentBrowser() {
  const { data, isLoading, pagination, setPagination, sorting, setSorting } =
    useDocumentSearch();

  return (
    <DataTable
      columns={columns}
      data={data?.results ?? []}
      pageCount={Math.ceil((data?.total ?? 0) / pagination.pageSize)}
      pagination={pagination}
      onPaginationChange={setPagination}
      sorting={sorting}
      onSortingChange={setSorting}
      isLoading={isLoading}
    />
  );
}
```

**Column definitions support custom renderers** -- use Badge for document types, Progress bars for confidence scores, Link for API numbers, and DropdownMenu for row actions.

**Data fetching pattern:**
- Server Components: call FastAPI directly via internal URL (`http://backend:8000`) with `cache: 'no-store'`
- Client Components: call through the rewrite proxy (`/api/...`) using SWR

### 2. Interactive Map

**Leaflet + react-leaflet with OpenStreetMap tiles (free, no API key).**

```typescript
'use client';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

function WellMap({ wells, onWellClick }) {
  return (
    <MapContainer center={[39.8283, -98.5795]} zoom={5} style={{ height: '100%', width: '100%' }}>
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; OpenStreetMap contributors &copy; CARTO'
      />
      {/* Render markers via Supercluster -- see clustering pattern below */}
    </MapContainer>
  );
}
```

**Tile providers (all free):**
- Primary: CartoDB Positron (light) -- clean, minimal, well pins stand out
- Dark mode: CartoDB Dark Matter
- Fallback: OpenStreetMap standard (`https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`)

### 3. Map Clustering with Supercluster

Supercluster handles 10K-50K markers efficiently (100K markers clustered in 1-2 seconds).

```typescript
import useSupercluster from 'use-supercluster';

// Convert wells to GeoJSON points
const points = wells.map(well => ({
  type: 'Feature' as const,
  properties: { cluster: false, wellId: well.id, ...well },
  geometry: { type: 'Point' as const, coordinates: [well.lon, well.lat] },
}));

const { clusters, supercluster } = useSupercluster({
  points,
  bounds,
  zoom,
  options: { radius: 75, maxZoom: 17 },
});
```

Cluster markers expand on click via `supercluster.getClusterExpansionZoom(cluster.id)`.

For datasets exceeding 100K wells, switch to server-side clustering using PostGIS `ST_ClusterDBSCAN` or a Python supercluster port, returning only visible clusters for the current viewport.

### 4. Click-to-Detail Side Panel

Clicking a well pin opens a slide-out panel alongside the map (not a popup, not a full page).

```typescript
function MapWithDetailPanel() {
  const [selectedWell, setSelectedWell] = useState<Well | null>(null);

  return (
    <div className="flex h-screen">
      <div className="flex-1">
        <WellMap onWellClick={setSelectedWell} />
      </div>
      {selectedWell && (
        <div className="w-96 border-l overflow-y-auto">
          <WellDetailPanel well={selectedWell} onClose={() => setSelectedWell(null)} />
        </div>
      )}
    </div>
  );
}
```

The detail panel includes tabs for Documents, Production Data, and Permits associated with the well.

### 5. Scrape Trigger with Real-Time SSE Progress

**Trigger:** "Scrape [State]" or "Scrape All" buttons in the Scraping Control Panel.

**Progress via SSE (Server-Sent Events):**

```typescript
'use client';
function useScrapeProgress(state: string | null) {
  const [progress, setProgress] = useState(null);

  useEffect(() => {
    if (!state) return;
    // Connect DIRECTLY to FastAPI for SSE (bypass Next.js rewrite -- rewriting buffers the stream)
    const eventSource = new EventSource(`http://localhost:8000/api/scrape/${state}/progress`);

    eventSource.addEventListener('progress', (event) => {
      setProgress(JSON.parse(event.data));
    });

    eventSource.onerror = () => eventSource.close();
    return () => eventSource.close();
  }, [state]);

  return progress;
}
```

**Important:** SSE endpoints must connect directly to FastAPI, not through the Next.js rewrite proxy, because the rewrite may buffer the stream.

Progress data includes: status, docs_found, docs_downloaded, docs_processed, current_step, errors, progress_pct.

### 6. Review Queue

"Needs Review" tab displays documents with confidence scores below the threshold, sorted lowest-confidence first.

**Side-by-side review interface:**
- Left panel: original PDF via react-pdf with zoom/scroll
- Right panel: extracted data fields with inline editing
- Low-confidence fields highlighted in yellow with confidence percentage badge
- Edited fields highlighted in blue
- Actions: Approve (optionally with corrections), Reject, Reset

```typescript
// Approve saves corrections and sets confidence to 1.0 (human-verified)
const handleApprove = async () => {
  await fetch(`/api/review/${documentId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ corrections: editedFields }),
  });
};
```

### 7. Document Viewer

react-pdf for inline PDF preview. Must use dynamic import with `ssr: false`.

```typescript
'use client';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();
```

Documents served via FastAPI: `GET /api/documents/{id}/file` returns the PDF binary.

### 8. Dashboard Layout

Fixed sidebar + main content area using shadcn/ui Sidebar component:

```
+--------+----------------------------------------------------+
| Logo   |  [Search bar...........]  [Dark Mode] [Settings]   |
|--------|----------------------------------------------------+
| Nav    |                                                    |
|        |  Main Content Area                                 |
| Search |  (Data table / Map / Review interface)             |
| Map    |                                                    |
| Review |                                                    |
| Scrape |                                                    |
| Files  |                                                    |
+--------+----------------------------------------------------+
```

Dark mode via next-themes + shadcn/ui CSS variables:

```typescript
// app/layout.tsx
import { ThemeProvider } from 'next-themes';

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system">
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
```

## Rate Limits and Constraints

- **OpenStreetMap tiles**: Free but subject to a fair use policy. For a local tool with 1-2 users, this is a non-issue.
- **CartoDB tiles**: Free for non-commercial use. Internal tools qualify.
- **No Mapbox GL JS**: Requires a paid Mapbox account for production use since v2 (December 2020). Use Leaflet (free) or MapLibre GL JS (free, open-source fork) instead.
- **Supercluster**: Client-side limit of roughly 50K markers before considering server-side clustering.
- **react-pdf**: No limits; runs entirely client-side with PDF.js.
- **SSE connections**: Browsers limit to 6 concurrent SSE connections per domain. Sufficient for this project.

## Common Pitfalls

### Leaflet CSS must be imported explicitly
Leaflet markers and controls will render incorrectly without the CSS. Import in the map component:
```typescript
import 'leaflet/dist/leaflet.css';
```

### Leaflet does not work with SSR
Leaflet relies on `window` and `document`. Always use dynamic import with `ssr: false`:
```typescript
import dynamic from 'next/dynamic';
const WellMap = dynamic(() => import('@/components/WellMap'), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-muted animate-pulse" />,
});
```

### Leaflet default marker icons break in bundlers
Webpack/Turbopack cannot resolve Leaflet's default icon paths. Fix manually:
```typescript
import L from 'leaflet';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x.src,
  iconUrl: markerIcon.src,
  shadowUrl: markerShadow.src,
});
```

### Supercluster must be initialized on the client side only
The use-supercluster hook and point data must exist in a `'use client'` component. Do not attempt to run Supercluster in a Server Component.

### SSE must bypass Next.js rewrite proxy
The Next.js URL rewriting proxy may buffer SSE streams. Connect the EventSource directly to the FastAPI URL (`http://localhost:8000/api/scrape/{state}/progress`), not through `/api/...`.

### react-pdf requires dynamic import with ssr: false
PDF.js relies on browser APIs. Use the same dynamic import pattern as Leaflet.

### react-pdf worker must be configured explicitly
Use the URL constructor pattern to set the PDF.js worker path. Without this, PDF rendering will fail silently.

### Coordinate format normalization
Well coordinates arrive in multiple formats (decimal degrees, DMS, State Plane, Township/Range/Section). All must be normalized to decimal degrees during extraction. Store as `DECIMAL(10, 7)` in PostgreSQL.

### Map filtering happens before Supercluster
When filtering wells on the map by state/operator/type, apply filters to the data array before passing it to useSupercluster. Do not try to filter Supercluster output.

## Testing Strategy

### Playwright E2E Tests
- Search flow: enter query, apply filters, verify table results
- Map interaction: zoom, click cluster to expand, click pin to open detail panel
- Scrape trigger: click "Scrape TX", verify SSE progress display, verify completion
- Review queue: open review item, edit a field, approve, verify it leaves the queue
- Document viewer: open PDF, navigate pages, verify rendering

### React Testing Library (Component Tests)
- DataTable: renders columns, handles pagination, handles sorting
- WellMap: renders markers (mock Leaflet), handles click callbacks
- ReviewInterface: renders extracted fields, handles inline editing, submits corrections
- ScrapeProgress: displays progress bar and stats from mock SSE data
- DocumentPreview: renders PDF pages (mock react-pdf)

### Test Commands
```bash
# E2E tests
npx playwright test

# Component tests
npm run test
```

## Cost Implications

**Fully free.** Every component of the frontend stack is open source with no usage-based fees:

| Component | License | Cost |
|-----------|---------|------|
| Next.js | MIT | Free |
| shadcn/ui | MIT | Free |
| Tailwind CSS | MIT | Free |
| Leaflet | BSD-2 | Free |
| react-leaflet | MIT | Free |
| Supercluster | ISC | Free |
| OpenStreetMap tiles | ODbL | Free (fair use) |
| CartoDB tiles | CC BY 3.0 | Free (non-commercial) |
| react-pdf / PDF.js | Apache 2.0 | Free |
| @tanstack/react-table | MIT | Free |

**Upgrade path if needed:** MapLibre GL JS (BSD-3, free) replaces Leaflet for WebGL rendering and vector tiles if well count exceeds 100K. No paid services required at any scale for this project.

## References

- **Discovery document**: `.claude/orchestration-og-doc-scraper/DISCOVERY.md` -- All project decisions (D1-D26)
- **Dashboard and map research**: `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` -- Full implementation details, code examples, library comparisons
- **shadcn/ui docs**: https://ui.shadcn.com
- **react-leaflet docs**: https://react-leaflet.js.org
- **Supercluster**: https://github.com/mapbox/supercluster
- **use-supercluster**: https://github.com/leighhalliday/use-supercluster
- **react-pdf**: https://github.com/wojtekmaj/react-pdf
- **TanStack Table**: https://tanstack.com/table
