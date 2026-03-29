# Dashboard & Interactive Map Implementation Research
## Oil & Gas Document Scraper

**Research Date**: 2026-03-27
**Scope**: Next.js + FastAPI integration, interactive well map, search/browse UI, review queue, scraping control panel, component library, Docker Compose deployment

---

## Table of Contents

1. [Next.js + FastAPI Integration](#1-nextjs--fastapi-integration)
2. [Interactive Map Implementation](#2-interactive-map-implementation)
3. [Search & Browse Interface](#3-search--browse-interface)
4. [Review Queue UI](#4-review-queue-ui)
5. [Scraping Control Panel](#5-scraping-control-panel)
6. [UI Component Library](#6-ui-component-library)
7. [Docker Compose for Local Deployment](#7-docker-compose-for-local-deployment)
8. [Recommendations Summary](#8-recommendations-summary)

---

## 1. Next.js + FastAPI Integration

### 1.1 Architecture Pattern: URL Rewriting Proxy

The recommended pattern for connecting a Next.js frontend to a FastAPI backend is **URL rewriting** via `next.config.js`. This avoids CORS issues entirely because all API calls appear to originate from the same domain as the frontend.

**next.config.js configuration:**
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

**How it works:**
- Next.js frontend runs on `localhost:3000`
- FastAPI backend runs on `localhost:8000`
- Frontend calls `/api/wells` which Next.js rewrites to `http://localhost:8000/api/wells`
- The rewrite is server-side, so the browser never sees the backend URL
- No CORS configuration needed on FastAPI

**In Docker Compose**, the destination URL changes to the service hostname:
```javascript
destination: 'http://backend:8000/api/:path*'  // Docker service name
```

**Limitations:**
- Rewrites are not a full HTTP proxy -- they only rewrite URL paths
- Streaming responses (SSE) may need special handling
- For SSE endpoints, the frontend may need to connect directly to the FastAPI URL

### 1.2 Type-Safe API Client Generation

FastAPI auto-generates an OpenAPI schema at `/openapi.json`. This can be used to auto-generate a TypeScript client for the frontend, ensuring end-to-end type safety.

**Recommended tool: `openapi-typescript-codegen` or `orval`**

```bash
# Generate TypeScript client from FastAPI's OpenAPI schema
npx openapi-typescript-codegen --input http://localhost:8000/openapi.json --output ./src/api-client
```

**Benefits:**
- TypeScript types auto-generated from Pydantic models
- API changes cause immediate TypeScript compilation errors
- No manual type duplication between Python and TypeScript
- Can be run as a build step or npm script

**Alternative: `orval`** -- generates React Query hooks directly from OpenAPI specs, which pairs well with TanStack Query for data fetching.

### 1.3 Real-Time Progress Updates: SSE (Recommended)

For showing real-time scraping progress, **Server-Sent Events (SSE)** is the best fit. It is simpler than WebSockets, requires no additional libraries on the client, and is well-suited for one-way server-to-client updates.

**Why SSE over WebSocket or Polling:**

| Approach   | Complexity | Bidirectional | Browser Support | Best For                     |
|------------|-----------|---------------|-----------------|------------------------------|
| SSE        | Low       | No (server->client) | Native (EventSource) | Progress bars, logs, status |
| WebSocket  | Medium    | Yes           | Native          | Chat, real-time collaboration |
| Polling    | Low       | No            | N/A             | Simple status checks          |

SSE is the right choice because scraping progress is a one-way stream (server pushes updates to client). No client-to-server messages are needed during streaming.

**FastAPI SSE endpoint:**
```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

app = FastAPI()

@app.get("/api/scrape/{state}/progress")
async def scrape_progress(state: str):
    async def event_generator():
        # Poll job status from task queue (or in-memory state)
        while True:
            status = await get_scrape_status(state)
            yield {
                "event": "progress",
                "data": json.dumps({
                    "state": state,
                    "status": status.status,        # running, completed, failed
                    "docs_found": status.docs_found,
                    "docs_downloaded": status.docs_downloaded,
                    "docs_processed": status.docs_processed,
                    "current_step": status.current_step,
                    "errors": status.errors,
                    "progress_pct": status.progress_pct,
                })
            }
            if status.status in ("completed", "failed"):
                break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
```

**Next.js client consumption:**
```typescript
'use client';
import { useEffect, useState } from 'react';

function useScrapeProgress(state: string) {
  const [progress, setProgress] = useState(null);

  useEffect(() => {
    // Connect directly to FastAPI for SSE (bypass Next.js rewrite)
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

**Production considerations for SSE:**
- Set `Cache-Control: no-cache` headers
- Set `X-Accel-Buffering: no` to prevent proxy/nginx buffering
- Send heartbeat events every ~15 seconds to avoid idle timeouts
- Use `sse-starlette` package for structured event sending from FastAPI
- SSE endpoints should connect directly to FastAPI (not through Next.js rewrite) since rewriting may buffer the stream

### 1.4 Data Fetching Pattern

For non-streaming API calls (search, browse, CRUD), use standard fetch with the rewrite proxy:

```typescript
// In a Server Component (preferred for initial data)
async function WellsPage({ searchParams }) {
  const res = await fetch(`${process.env.API_URL}/api/wells?state=${searchParams.state}`, {
    cache: 'no-store',  // Always fresh data for an internal tool
  });
  const wells = await res.json();
  return <WellsTable data={wells} />;
}

// In a Client Component (for interactive queries)
'use client';
import useSWR from 'swr';

function useWells(filters) {
  return useSWR(`/api/wells?${new URLSearchParams(filters)}`, fetcher);
}
```

**Server Components** should call FastAPI directly using the internal Docker hostname (`http://backend:8000`). **Client Components** should call through the rewrite proxy (`/api/...`).

---

## 2. Interactive Map Implementation

### 2.1 Library Selection

#### Candidates Evaluated

| Library         | Rendering | License        | Cost  | Large Datasets | Bundle Size |
|----------------|-----------|----------------|-------|----------------|-------------|
| Leaflet + react-leaflet | DOM/Canvas | BSD-2 | Free  | Good with clustering | ~42KB (Leaflet) |
| MapLibre GL JS | WebGL     | BSD-3          | Free  | Excellent      | ~250KB      |
| Mapbox GL JS   | WebGL     | Proprietary (v2+) | Paid (after free tier) | Excellent | ~250KB |
| deck.gl        | WebGL     | MIT            | Free  | Best (millions) | Heavy       |

#### Recommendation: Leaflet + react-leaflet (PRIMARY) with MapLibre as UPGRADE PATH

**Why Leaflet for this project:**

1. **Completely free** -- No API tokens, no usage limits, no vendor lock-in. Critical for a local-only tool.
2. **Sufficient performance** -- With Supercluster clustering, Leaflet handles 10,000-50,000 markers efficiently. The project's 10 states will likely produce well counts in this range.
3. **Simpler setup** -- DOM-based rendering is easier to debug and customize. No WebGL compatibility concerns.
4. **Mature ecosystem** -- react-leaflet is well-maintained, with extensive plugins for clustering, custom popups, and layer controls.
5. **Smaller bundle** -- 42KB vs 250KB for MapLibre/Mapbox GL. Matters less for local deployment but still beneficial.

**When to upgrade to MapLibre GL JS:**
- If well count exceeds 100,000 and clustering is insufficient
- If vector tile rendering is needed (satellite imagery, terrain)
- MapLibre is the free, open-source fork of Mapbox GL JS (BSD-3 license), works with react-map-gl, and requires no API token

**Why NOT Mapbox GL JS:**
- Requires a paid Mapbox account for production use since v2 (December 2020)
- Proprietary license conflicts with local-only, no-cost deployment
- MapLibre provides identical WebGL performance without the cost

**Why NOT deck.gl:**
- Overkill for 10K-50K pins. Designed for millions of data points.
- Much heavier bundle and steeper learning curve.
- Better suited for visualization-heavy applications (heat maps, flow maps) rather than click-to-detail pin maps.

### 2.2 Free Tile Providers

| Provider          | Style                | URL Template                                              | Restrictions        |
|-------------------|----------------------|-----------------------------------------------------------|---------------------|
| OpenStreetMap     | Standard             | `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`      | Fair use policy     |
| CartoDB Positron  | Light, minimal       | `https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png` | Free for non-commercial |
| CartoDB Dark Matter | Dark theme          | `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`  | Free for non-commercial |
| OpenTopoMap       | Topographic          | `https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png`        | Free                |
| Stadia (Stamen)   | Watercolor, Toner, Terrain | Requires registration (free tier)                   | Registration required |

**Recommended for this project:**
- **Primary**: CartoDB Positron (light) -- clean, minimal, excellent for data overlays. Well pins stand out clearly.
- **Dark mode**: CartoDB Dark Matter -- pairs with dashboard dark mode.
- **Fallback**: OpenStreetMap standard -- no registration, always available.
- **Note**: For a local internal tool, fair use policies are non-issues. These tile providers are designed for exactly this kind of usage.

### 2.3 Rendering 10,000+ Well Pins: Supercluster Clustering

The key performance challenge is rendering thousands of well markers without freezing the browser. The solution is **Supercluster** -- a high-performance clustering library.

**Performance benchmarks:**
- Supercluster: 100K markers clustered in 1-2 seconds
- Leaflet.markercluster (DOM-based): ~30 seconds for same dataset
- Supercluster with 500K markers: 1-2 seconds

**Recommended approach: `use-supercluster` hook with react-leaflet**

```typescript
'use client';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import useSupercluster from 'use-supercluster';
import { useState, useRef } from 'react';

interface Well {
  id: string;
  api_number: string;
  well_name: string;
  operator: string;
  state: string;
  lat: number;
  lon: number;
  status: string;
  doc_count: number;
}

function WellMap({ wells }: { wells: Well[] }) {
  const [bounds, setBounds] = useState(null);
  const [zoom, setZoom] = useState(5);
  const mapRef = useRef();

  // Convert wells to GeoJSON points for Supercluster
  const points = wells.map(well => ({
    type: 'Feature' as const,
    properties: {
      cluster: false,
      wellId: well.id,
      apiNumber: well.api_number,
      wellName: well.well_name,
      operator: well.operator,
      state: well.state,
      status: well.status,
      docCount: well.doc_count,
    },
    geometry: {
      type: 'Point' as const,
      coordinates: [well.lon, well.lat],
    },
  }));

  // Supercluster hook handles all clustering logic
  const { clusters, supercluster } = useSupercluster({
    points,
    bounds,
    zoom,
    options: { radius: 75, maxZoom: 17 },
  });

  return (
    <MapContainer
      center={[39.8283, -98.5795]}  // Center of US
      zoom={5}
      style={{ height: '100%', width: '100%' }}
      ref={mapRef}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; OpenStreetMap contributors &copy; CARTO'
      />
      <MapEvents onBoundsChange={setBounds} onZoomChange={setZoom} />

      {clusters.map(cluster => {
        const [lng, lat] = cluster.geometry.coordinates;
        const { cluster: isCluster, point_count } = cluster.properties;

        if (isCluster) {
          return (
            <Marker
              key={`cluster-${cluster.id}`}
              position={[lat, lng]}
              icon={makeClusterIcon(point_count)}
              eventHandlers={{
                click: () => {
                  const expansionZoom = supercluster.getClusterExpansionZoom(cluster.id);
                  mapRef.current?.setView([lat, lng], expansionZoom);
                },
              }}
            />
          );
        }

        return (
          <Marker key={cluster.properties.wellId} position={[lat, lng]}>
            <Popup>
              <WellPopupContent well={cluster.properties} />
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
```

**Alternative: Server-side clustering for very large datasets (100K+)**

If client-side clustering becomes a bottleneck (all marker data must be loaded to the client), implement server-side clustering:

```python
# FastAPI endpoint returns pre-clustered data for current viewport
@app.get("/api/wells/clustered")
async def get_clustered_wells(
    bbox: str,       # "minLng,minLat,maxLng,maxLat"
    zoom: int,
    state: str = None,
    operator: str = None,
):
    # Use supercluster Python port or PostGIS ST_ClusterDBSCAN
    # Return only clusters/points visible in the current viewport
    ...
```

### 2.4 Next.js SSR Fix for react-leaflet

Leaflet relies on `window` and `document` which do not exist during server-side rendering. The fix is a two-layer dynamic import pattern:

**Step 1: Create the map component as a client component:**
```typescript
// components/WellMap.tsx
'use client';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
// ... full map implementation
```

**Step 2: Dynamically import with SSR disabled in the page:**
```typescript
// app/map/page.tsx
import dynamic from 'next/dynamic';

const WellMap = dynamic(() => import('@/components/WellMap'), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-muted animate-pulse" />,
});

export default function MapPage() {
  return (
    <div className="h-screen">
      <WellMap />
    </div>
  );
}
```

**Step 3: Fix Leaflet default marker icons (broken in bundlers):**
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

### 2.5 Click-to-Detail Popup/Panel

Two interaction patterns for showing well details:

**Pattern A: Popup (simple, default)**
- Leaflet `<Popup>` component renders inside the map
- Good for quick-glance information (well name, API number, status)
- Limited space for detailed information

**Pattern B: Side Panel (recommended for this project)**
- Clicking a marker opens a slide-out panel alongside the map
- Panel shows full well details, associated documents, production data
- More space for document lists and tabular data
- Does not obscure the map

```typescript
// Recommended: Side panel pattern
function MapWithDetailPanel() {
  const [selectedWell, setSelectedWell] = useState<Well | null>(null);

  return (
    <div className="flex h-screen">
      {/* Map takes remaining space */}
      <div className="flex-1">
        <WellMap onWellClick={setSelectedWell} />
      </div>

      {/* Detail panel slides in from right */}
      {selectedWell && (
        <div className="w-96 border-l overflow-y-auto">
          <WellDetailPanel
            well={selectedWell}
            onClose={() => setSelectedWell(null)}
          />
        </div>
      )}
    </div>
  );
}

function WellDetailPanel({ well, onClose }) {
  return (
    <div className="p-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-bold">{well.well_name}</h2>
        <button onClick={onClose}>X</button>
      </div>
      <dl>
        <dt>API Number</dt><dd>{well.api_number}</dd>
        <dt>Operator</dt><dd>{well.operator}</dd>
        <dt>State</dt><dd>{well.state}</dd>
        <dt>Status</dt><dd>{well.status}</dd>
        <dt>Coordinates</dt><dd>{well.lat}, {well.lon}</dd>
      </dl>
      {/* Tabs for documents, production data, etc. */}
      <Tabs>
        <Tab label="Documents"><WellDocuments wellId={well.id} /></Tab>
        <Tab label="Production"><WellProduction wellId={well.id} /></Tab>
        <Tab label="Permits"><WellPermits wellId={well.id} /></Tab>
      </Tabs>
    </div>
  );
}
```

### 2.6 Map Filtering

Filtering wells on the map by state, operator, type, and date range. The filtering happens on the data before it reaches Supercluster.

**Client-side filtering (for < 50K wells):**
```typescript
function useFilteredWells(wells: Well[], filters: WellFilters) {
  return useMemo(() => {
    return wells.filter(well => {
      if (filters.state && well.state !== filters.state) return false;
      if (filters.operator && well.operator !== filters.operator) return false;
      if (filters.status && well.status !== filters.status) return false;
      if (filters.dateFrom && well.last_activity < filters.dateFrom) return false;
      if (filters.dateTo && well.last_activity > filters.dateTo) return false;
      return true;
    });
  }, [wells, filters]);
}
```

**Server-side filtering (for > 50K wells):**
```python
@app.get("/api/wells")
async def get_wells(
    state: str | None = None,
    operator: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    bbox: str | None = None,  # Viewport bounding box
):
    query = select(Well)
    if state:
        query = query.where(Well.state_code == state)
    if operator:
        query = query.where(Well.operator.has(name=operator))
    if bbox:
        min_lng, min_lat, max_lng, max_lat = map(float, bbox.split(','))
        query = query.where(
            Well.longitude.between(min_lng, max_lng),
            Well.latitude.between(min_lat, max_lat),
        )
    # ... additional filters
    return await db.execute(query)
```

### 2.7 Coordinate Handling

Well locations come from state regulatory databases with varying coordinate formats:

**Common formats encountered:**
- Decimal degrees: `32.4487, -100.4504` (most common, preferred)
- Degrees-minutes-seconds: `32 26' 55.32" N, 100 27' 1.44" W`
- State Plane Coordinates (NAD27/NAD83): converted during extraction
- Township/Range/Section (PLSS): requires geocoding lookup

**Strategy:**
- Store coordinates as `DECIMAL(10, 7)` for latitude and longitude in PostgreSQL
- Normalize all input formats to decimal degrees during the extraction pipeline
- Add a PostGIS extension if spatial queries become complex (e.g., "find wells within 5 miles")
- For the initial implementation, standard `BETWEEN` queries on lat/lon columns suffice for bounding box filters

---

## 3. Search & Browse Interface

### 3.1 Full-Text Search UI

The search interface sits at the top of the dashboard and queries PostgreSQL full-text search (tsvector/tsquery) via FastAPI.

**Search UI components:**
```
+------------------------------------------------------------------+
| [Search: operator name, API number, well name...]  [Search btn]  |
+------------------------------------------------------------------+
| Filters:                                                         |
| [State: All v] [Operator: All v] [Doc Type: All v]              |
| [Date From: ___] [Date To: ___] [Status: All v]                 |
+------------------------------------------------------------------+
| Results (2,847 documents)                      [Export CSV] [PDF] |
| +--------------------------------------------------------------+ |
| | API Number  | Well Name   | Operator | Type | Date   | Score | |
| | 42-001-3456 | Permian #7  | Devon    | Prod | 2026-01| 0.95  | |
| | 42-001-3457 | Permian #8  | Devon    | Perm | 2026-02| 0.87  | |
| | ...                                                           | |
| +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

**FastAPI search endpoint:**
```python
@app.get("/api/search")
async def search_documents(
    q: str | None = None,           # Full-text search query
    state: str | None = None,
    operator: str | None = None,
    doc_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    confidence_min: float | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "relevance",     # relevance, date, confidence
):
    query = select(Document).join(Well, isouter=True)

    if q:
        # PostgreSQL full-text search with ranking
        search_query = func.plainto_tsquery('english', q)
        query = query.where(Document.search_vector.op('@@')(search_query))
        query = query.order_by(
            func.ts_rank(Document.search_vector, search_query).desc()
        )

    # Apply filters...
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    results = await db.execute(query.offset((page-1)*page_size).limit(page_size))

    return {
        "total": total,
        "page": page,
        "results": results.all(),
    }
```

### 3.2 Data Table Component

**Recommendation: shadcn/ui Data Table (built on TanStack Table)**

TanStack Table is the de facto standard for data-heavy React applications. The shadcn/ui wrapper provides pre-styled, accessible table components using Tailwind CSS.

**Key capabilities:**
- Server-side pagination, sorting, and filtering (essential for large datasets)
- Column resizing and reordering
- Row selection for bulk actions
- Virtual scrolling for 10,000+ row performance
- Built-in TypeScript support
- Customizable cell renderers (badges for status, progress bars for confidence)

**Implementation pattern:**
```typescript
'use client';
import { DataTable } from '@/components/ui/data-table';
import { columns } from './columns';
import { useDocumentSearch } from '@/hooks/use-document-search';

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

**Column definitions with custom renderers:**
```typescript
export const columns: ColumnDef<Document>[] = [
  {
    accessorKey: 'api_number',
    header: 'API Number',
    cell: ({ row }) => (
      <Link href={`/wells/${row.original.well_id}`}>
        {row.getValue('api_number')}
      </Link>
    ),
  },
  {
    accessorKey: 'doc_type',
    header: 'Type',
    cell: ({ row }) => <Badge variant="outline">{row.getValue('doc_type')}</Badge>,
  },
  {
    accessorKey: 'confidence_score',
    header: 'Confidence',
    cell: ({ row }) => {
      const score = row.getValue('confidence_score') as number;
      return (
        <div className="flex items-center gap-2">
          <Progress value={score * 100} className="w-16" />
          <span>{(score * 100).toFixed(0)}%</span>
        </div>
      );
    },
  },
  {
    accessorKey: 'scraped_at',
    header: 'Date',
    cell: ({ row }) => formatDate(row.getValue('scraped_at')),
  },
  {
    id: 'actions',
    cell: ({ row }) => (
      <DropdownMenu>
        <DropdownMenuItem>View Document</DropdownMenuItem>
        <DropdownMenuItem>View Extracted Data</DropdownMenuItem>
        <DropdownMenuItem>Download Original</DropdownMenuItem>
      </DropdownMenu>
    ),
  },
];
```

**Why NOT AG Grid:**
- AG Grid Community is powerful but has a large bundle size (~1MB)
- The enterprise features (Excel export, row grouping) require a paid license
- shadcn/ui + TanStack Table provides everything needed for this project with much smaller footprint
- AG Grid is better suited for spreadsheet-like applications; this project needs a standard data table

### 3.3 Document Preview (PDF Viewer)

**Recommendation: `react-pdf` (wrapper around Mozilla's PDF.js)**

```bash
npm install react-pdf
```

**Key setup for Next.js:**
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

function DocumentPreview({ fileUrl }: { fileUrl: string }) {
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);

  return (
    <div>
      <Document
        file={fileUrl}
        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
      >
        <Page pageNumber={pageNumber} />
      </Document>
      <div className="flex items-center gap-2 mt-2">
        <Button onClick={() => setPageNumber(p => Math.max(1, p - 1))}>Prev</Button>
        <span>Page {pageNumber} of {numPages}</span>
        <Button onClick={() => setPageNumber(p => Math.min(numPages, p + 1))}>Next</Button>
      </div>
    </div>
  );
}
```

**Next.js considerations:**
- Must use dynamic import with `ssr: false` (PDF.js requires browser APIs)
- Worker file must be properly configured -- use the URL constructor pattern above
- For Next.js 15+, no additional `next.config.js` changes needed
- Serve documents via FastAPI: `GET /api/documents/{id}/file` returns the PDF binary

**File browser for originals:**

The file organization (`data/{state}/{operator}/{doc_type}/{filename}`) maps to a simple tree browser:

```typescript
function FileBrowser() {
  const [path, setPath] = useState('/');
  const { data: listing } = useSWR(`/api/files?path=${path}`);

  return (
    <div>
      <Breadcrumb path={path} onNavigate={setPath} />
      <div className="grid gap-2">
        {listing?.folders.map(folder => (
          <div key={folder} onClick={() => setPath(`${path}${folder}/`)} className="cursor-pointer">
            <FolderIcon /> {folder}
          </div>
        ))}
        {listing?.files.map(file => (
          <div key={file.name} className="flex justify-between">
            <span><FileIcon /> {file.name}</span>
            <div>
              <Button size="sm" onClick={() => previewFile(file)}>Preview</Button>
              <Button size="sm" variant="outline" onClick={() => downloadFile(file)}>Download</Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## 4. Review Queue UI

### 4.1 "Needs Review" Tab

Documents with confidence scores below the threshold land in the review queue. The UI presents these in a prioritized list.

**FastAPI endpoint:**
```python
@app.get("/api/review-queue")
async def get_review_queue(
    state: str | None = None,
    doc_type: str | None = None,
    sort_by: str = "confidence_asc",  # Lowest confidence first
    page: int = 1,
    page_size: int = 20,
):
    query = (
        select(Document)
        .join(ExtractedData)
        .where(Document.confidence_score < CONFIDENCE_THRESHOLD)
        .where(Document.review_status == 'pending')
    )
    # Sort by confidence (lowest first = most in need of review)
    if sort_by == "confidence_asc":
        query = query.order_by(Document.confidence_score.asc())
    ...
```

**Queue list view:**
```
+------------------------------------------------------------------+
| Review Queue (127 pending)                                        |
+------------------------------------------------------------------+
| Filter: [State: All v] [Type: All v]  Sort: [Lowest Confidence v] |
+------------------------------------------------------------------+
| [ ] | API 42-001-3456 | Production Report | TX | Conf: 47%       |
|     | Operator: Devon Energy | Scraped: 2026-03-25                |
|     | Issues: OCR quality low, missing fields                     |
+------------------------------------------------------------------+
| [ ] | API 30-015-2345 | Well Permit       | NM | Conf: 52%       |
|     | Operator: ConocoPhillips | Scraped: 2026-03-24              |
|     | Issues: Date format ambiguous                                |
+------------------------------------------------------------------+
```

### 4.2 Side-by-Side Review Interface

The core review workflow: original document on the left, extracted data on the right. This is the most critical UI component for data quality.

**Layout:**
```
+------------------------------------------------------------------+
| Review: Production Report - Permian #7 (API 42-001-34567890)      |
| Status: Pending | Confidence: 47% | Scraped: 2026-03-25          |
+-------------------------------+----------------------------------+
|                               |                                  |
|   ORIGINAL DOCUMENT           |   EXTRACTED DATA                 |
|                               |                                  |
|   +-------------------------+ |   Operator: [Devon Energy    ] * |
|   |                         | |   API Number: [42-001-3456  ]   |
|   |   (PDF Viewer)          | |   Report Date: [2026-01     ] * |
|   |                         | |   Production (Oil): [1,247  ] * |
|   |   react-pdf embedded    | |   Production (Gas): [  ???  ] ! |
|   |   with zoom/scroll      | |   Well Status: [Active      ]   |
|   |                         | |   County: [Midland           ]  |
|   +-------------------------+ |                                  |
|   Page 1 of 3  [<] [>]       |   * = low confidence field       |
|                               |   ! = missing/unreadable         |
|                               |                                  |
|                               |   [Approve] [Reject] [Save]     |
+-------------------------------+----------------------------------+
```

**Implementation:**
```typescript
'use client';

function ReviewInterface({ documentId }: { documentId: string }) {
  const { data: doc } = useSWR(`/api/documents/${documentId}`);
  const { data: extracted } = useSWR(`/api/documents/${documentId}/extracted`);
  const [editedFields, setEditedFields] = useState({});

  const handleFieldEdit = (fieldPath: string, newValue: any) => {
    setEditedFields(prev => ({ ...prev, [fieldPath]: newValue }));
  };

  const handleApprove = async () => {
    await fetch(`/api/review/${documentId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ corrections: editedFields }),
    });
  };

  const handleReject = async () => {
    await fetch(`/api/review/${documentId}/reject`, { method: 'POST' });
  };

  return (
    <div className="grid grid-cols-2 h-screen">
      {/* Left: Original Document */}
      <div className="border-r overflow-auto p-4">
        <DocumentPreview fileUrl={`/api/documents/${documentId}/file`} />
      </div>

      {/* Right: Extracted Data with inline editing */}
      <div className="overflow-auto p-4">
        <h2 className="text-lg font-bold mb-4">Extracted Data</h2>

        {extracted && Object.entries(extracted.data).map(([key, value]) => {
          const confidence = extracted.confidence?.[key] ?? 1;
          const isLowConfidence = confidence < CONFIDENCE_THRESHOLD;
          const isEdited = key in editedFields;

          return (
            <div key={key} className="flex items-center gap-2 mb-2">
              <Label className="w-40 text-sm">{formatFieldName(key)}</Label>
              <Input
                value={editedFields[key] ?? value}
                onChange={(e) => handleFieldEdit(key, e.target.value)}
                className={cn(
                  isLowConfidence && 'border-yellow-500 bg-yellow-50',
                  isEdited && 'border-blue-500',
                )}
              />
              {isLowConfidence && (
                <Badge variant="warning">{(confidence * 100).toFixed(0)}%</Badge>
              )}
              {isEdited && <Badge variant="info">Edited</Badge>}
            </div>
          );
        })}

        <div className="flex gap-2 mt-6">
          <Button onClick={handleApprove} variant="default">
            Approve {Object.keys(editedFields).length > 0 && '& Save Corrections'}
          </Button>
          <Button onClick={handleReject} variant="destructive">Reject</Button>
          <Button onClick={() => setEditedFields({})} variant="outline">Reset</Button>
        </div>
      </div>
    </div>
  );
}
```

### 4.3 Backend Workflow

```python
@app.post("/api/review/{document_id}/approve")
async def approve_document(document_id: str, body: ApproveRequest):
    doc = await get_document(document_id)

    # Save corrections to data_corrections table
    for field_path, new_value in body.corrections.items():
        old_value = get_nested(doc.extracted_data.data, field_path)
        await db.execute(insert(DataCorrection).values(
            extracted_data_id=doc.extracted_data.id,
            field_path=field_path,
            old_value=old_value,
            new_value=new_value,
            corrected_at=datetime.utcnow(),
        ))
        # Update the extracted data with the correction
        set_nested(doc.extracted_data.data, field_path, new_value)

    doc.review_status = 'approved'
    doc.confidence_score = 1.0  # Human-verified
    await db.commit()

@app.post("/api/review/{document_id}/reject")
async def reject_document(document_id: str):
    doc = await get_document(document_id)
    doc.review_status = 'rejected'
    await db.commit()
```

---

## 5. Scraping Control Panel

### 5.1 Per-State Scrape Controls

**Layout:**
```
+------------------------------------------------------------------+
| Scraping Control Panel                                            |
+------------------------------------------------------------------+
| TIER 1 STATES                                                    |
| +--------------------------------------------------------------+ |
| | Texas (TX)          | Last: 2026-03-20 | 12,456 docs         | |
| | [Scrape TX] [View Jobs]    Status: Idle                       | |
| +--------------------------------------------------------------+ |
| | New Mexico (NM)     | Last: 2026-03-18 | 8,234 docs          | |
| | [Scrape NM] [View Jobs]    Status: Idle                       | |
| +--------------------------------------------------------------+ |
| | North Dakota (ND)   | Last: Never      | 0 docs               | |
| | [Scrape ND] [View Jobs]    Status: Idle                       | |
| +--------------------------------------------------------------+ |
| ...                                                              |
|                                                                  |
| [Scrape All States]                                              |
+------------------------------------------------------------------+
```

### 5.2 Active Job Progress

When a scrape is running, the state card expands to show real-time progress via SSE:

```
+--------------------------------------------------------------+
| Texas (TX)          | Started: 2026-03-27 14:23               |
| Status: RUNNING                                               |
|                                                               |
| Phase: Downloading documents                                  |
| [========================================--------]  78%       |
|                                                               |
| Documents found:       1,247                                  |
| Documents downloaded:    973                                  |
| Documents processed:     856                                  |
| Documents failed:         12                                  |
| New documents:           423                                  |
| Duplicates skipped:      550                                  |
|                                                               |
| Current: Downloading production-report-42-001-3456.pdf        |
|                                                               |
| Errors (12):                                     [Show All v] |
|  - Timeout: rrc.texas.gov/well/42-001-9999 (retrying...)     |
|  - 404: rrc.texas.gov/permit/expired-link                     |
|                                                               |
| [Cancel Job]                                                  |
+--------------------------------------------------------------+
```

**Implementation:**
```typescript
'use client';
import { useScrapeProgress } from '@/hooks/use-scrape-progress';

function StateCard({ state }: { state: StateInfo }) {
  const [isRunning, setIsRunning] = useState(false);
  const progress = useScrapeProgress(isRunning ? state.code : null);

  const startScrape = async () => {
    await fetch(`/api/scrape/${state.code}`, { method: 'POST' });
    setIsRunning(true);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between">
          <CardTitle>{state.name} ({state.code})</CardTitle>
          <Badge>{progress?.status ?? 'Idle'}</Badge>
        </div>
        <CardDescription>
          Last scraped: {state.last_scraped ?? 'Never'} | {state.doc_count} documents
        </CardDescription>
      </CardHeader>

      {progress && progress.status === 'running' && (
        <CardContent>
          <div className="space-y-3">
            <div>
              <div className="text-sm text-muted-foreground mb-1">
                {progress.current_step}
              </div>
              <Progress value={progress.progress_pct} />
            </div>

            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>Found: {progress.docs_found}</div>
              <div>Downloaded: {progress.docs_downloaded}</div>
              <div>Processed: {progress.docs_processed}</div>
              <div>Failed: {progress.errors?.length ?? 0}</div>
            </div>

            {progress.errors?.length > 0 && (
              <Collapsible>
                <CollapsibleTrigger>
                  Errors ({progress.errors.length})
                </CollapsibleTrigger>
                <CollapsibleContent>
                  {progress.errors.map((err, i) => (
                    <div key={i} className="text-sm text-destructive">{err}</div>
                  ))}
                </CollapsibleContent>
              </Collapsible>
            )}
          </div>
        </CardContent>
      )}

      <CardFooter>
        {!isRunning ? (
          <Button onClick={startScrape}>Scrape {state.code}</Button>
        ) : (
          <Button variant="destructive" onClick={cancelScrape}>Cancel</Button>
        )}
      </CardFooter>
    </Card>
  );
}
```

### 5.3 Job History Dashboard

```python
@app.get("/api/scrape/jobs")
async def get_scrape_jobs(
    state: str | None = None,
    status: str | None = None,  # running, completed, failed, cancelled
    page: int = 1,
):
    query = select(ScrapeRun).order_by(ScrapeRun.started_at.desc())
    if state:
        query = query.where(ScrapeRun.state_code == state)
    if status:
        query = query.where(ScrapeRun.status == status)
    return await paginate(query, page)
```

---

## 6. UI Component Library

### 6.1 Comparison for Internal Tool Use

| Criteria               | shadcn/ui              | Mantine             | Radix UI             |
|------------------------|------------------------|---------------------|----------------------|
| **Architecture**       | Copy components into repo | npm package          | Unstyled primitives  |
| **Styling**            | Tailwind CSS           | CSS-in-JS / modules | BYO (no styles)      |
| **Setup time**         | 30-60 min              | 10-15 min           | Varies               |
| **Data table**         | Via TanStack Table     | Built-in            | None                 |
| **Form handling**      | Via React Hook Form    | Built-in useForm    | None                 |
| **Dark mode**          | Built-in theming       | Built-in            | BYO                  |
| **Bundle size**        | Only what you use      | ~200KB              | Tiny per primitive   |
| **Customizability**    | Full (own the code)    | Theme system         | Full (unstyled)      |
| **Docs quality**       | Good, expects Tailwind knowledge | Excellent, interactive | Good      |
| **GitHub Stars**       | 83K                    | 28K                 | 17K                  |
| **npm weekly downloads** | 200K+                | 490K+               | 130K+                |

### 6.2 Recommendation: shadcn/ui

**Why shadcn/ui for this project:**

1. **Tailwind CSS alignment** -- If the project uses Tailwind (standard for modern Next.js), shadcn/ui is the natural fit. Components are pre-styled with Tailwind utilities.

2. **Full ownership** -- Components are copied into the project, not imported from node_modules. This means zero risk of breaking changes from library updates, and full ability to customize every detail.

3. **TanStack Table integration** -- shadcn/ui provides a well-documented Data Table component built on TanStack Table, which is exactly what the search/browse interface needs.

4. **Growing ecosystem** -- Large community producing extensions, templates, and blocks (pre-built sections like sidebars, dashboards, charts).

5. **Minimal overhead** -- Only include the components you use. No runtime CSS-in-JS overhead.

6. **Dark mode built-in** -- CSS variable theming with `next-themes` makes dark mode trivial.

**When Mantine would be better:**
- If the team is unfamiliar with Tailwind CSS
- If maximum speed-to-first-prototype matters more than long-term customizability
- If built-in form handling and complex inputs (date ranges, multi-selects) are a priority

**For this project's context** (1-2 users, functional > pretty, internal tool, Next.js with Tailwind), shadcn/ui is the better choice because it produces a clean, modern UI with full customizability, and the ecosystem has extensive dashboard templates to start from.

### 6.3 Key shadcn/ui Components for This Project

```bash
# Install the components needed for the dashboard
npx shadcn@latest init
npx shadcn@latest add button card input label badge tabs
npx shadcn@latest add table data-table dialog dropdown-menu
npx shadcn@latest add progress collapsible separator
npx shadcn@latest add select command popover calendar
npx shadcn@latest add sidebar sheet toast
```

**Component mapping to features:**

| Feature               | shadcn/ui Components                                     |
|-----------------------|----------------------------------------------------------|
| Navigation            | Sidebar, Tabs                                            |
| Search bar            | Command (combobox), Input, Select, Calendar (date range) |
| Data table            | DataTable, Table, Badge, DropdownMenu                    |
| Map side panel        | Sheet (slide-over), Card, Tabs                           |
| Review queue          | Card, Input, Badge, Button, Progress                     |
| Scrape controls       | Card, Button, Progress, Collapsible, Badge               |
| Document preview      | Dialog (modal), or embedded in layout                    |
| Notifications         | Toast                                                    |

### 6.4 Dark Mode

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

With shadcn/ui, dark mode is handled by CSS variables. All components automatically support both themes. Toggle with a button:

```typescript
import { useTheme } from 'next-themes';
const { theme, setTheme } = useTheme();
<Button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>Toggle</Button>
```

### 6.5 Dashboard Layout

For a primarily desktop application used by 1-2 people, a fixed sidebar + main content area is the standard pattern:

```
+--------+----------------------------------------------------+
| Logo   |  [Search bar...........]  [Dark Mode] [Settings]   |
|--------|----------------------------------------------------+
| Nav    |                                                    |
|        |  Main Content Area                                 |
| Search |                                                    |
| Map    |  (Data table / Map / Review interface)             |
| Review |                                                    |
| Scrape |                                                    |
| Files  |                                                    |
|        |                                                    |
+--------+----------------------------------------------------+
```

shadcn/ui provides a pre-built `Sidebar` component that handles collapse, responsive behavior, and keyboard shortcuts.

---

## 7. Docker Compose for Local Deployment

### 7.1 Service Architecture

```
                    +-----------+
                    |  Browser  |
                    +-----+-----+
                          |
                    +-----v-----+
                    | Next.js   |  Port 3000
                    | Frontend  |  (rewrites /api/* to backend)
                    +-----+-----+
                          |
                    +-----v-----+
                    | FastAPI   |  Port 8000
                    | Backend   |  (REST API + SSE)
                    +-----+-----+
                          |
              +-----------+-----------+
              |                       |
        +-----v-----+         +------v------+
        | PostgreSQL |         | File Volume |
        | Database   |         | /data       |
        | Port 5432  |         | (documents) |
        +------------+         +-------------+
```

### 7.2 docker-compose.yml (Development)

```yaml
version: '3.8'

services:
  # --- Frontend ---
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app
      - /app/node_modules          # Prevent node_modules override
      - /app/.next                 # Prevent .next override
    environment:
      - WATCHPACK_POLLING=true     # Enable file watching in Docker
      - API_URL=http://backend:8000  # Internal URL for Server Components
    depends_on:
      - backend
    networks:
      - app-network

  # --- Backend ---
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - document-storage:/data     # Shared document storage
    environment:
      - DATABASE_URL=postgresql+asyncpg://oguser:ogpass@db:5432/ogdocs
      - DOCUMENT_STORAGE_PATH=/data/documents
      - PYTHONDONTWRITEBYTECODE=1
    depends_on:
      db:
        condition: service_healthy
    networks:
      - app-network

  # --- Database ---
  db:
    image: postgres:17
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=oguser
      - POSTGRES_PASSWORD=ogpass
      - POSTGRES_DB=ogdocs
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./backend/sql/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U oguser -d ogdocs"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - app-network

volumes:
  postgres-data:
    driver: local
  document-storage:
    driver: local

networks:
  app-network:
    driver: bridge
```

### 7.3 Dockerfiles

**Frontend Dockerfile.dev:**
```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
```

**Backend Dockerfile.dev:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for Playwright, PaddleOCR, etc.
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# --reload enables hot reload for development
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### 7.4 docker-compose.prod.yml (Production Override)

```yaml
version: '3.8'

services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod
    environment:
      - NODE_ENV=production
    volumes: []  # No volume mounts in production

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.prod
    volumes:
      - document-storage:/data     # Keep document storage volume
    environment:
      - PYTHONDONTWRITEBYTECODE=1
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Frontend Dockerfile.prod:**
```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
```

**Backend Dockerfile.prod:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 7.5 Hot Reload Configuration

**Next.js hot reload in Docker:**
- `WATCHPACK_POLLING=true` enables file watching via polling (required because Docker filesystem events do not propagate across the Docker boundary to the host)
- Volume mounts: `./frontend:/app` maps host source to container
- Exclude `node_modules` and `.next` via anonymous volumes to prevent overriding container-installed packages

**FastAPI hot reload in Docker:**
- `uvicorn --reload` watches for `.py` file changes and restarts the server
- Volume mount: `./backend:/app` maps host source to container
- Uvicorn's file watcher uses polling automatically in Docker

### 7.6 Running the Stack

```bash
# Development (with hot reload)
docker compose up

# Development (rebuild after dependency changes)
docker compose up --build

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# View logs
docker compose logs -f backend
docker compose logs -f frontend

# Database shell
docker compose exec db psql -U oguser -d ogdocs

# Run database migrations
docker compose exec backend alembic upgrade head
```

---

## 8. Recommendations Summary

### Technology Choices

| Component            | Recommendation                    | Rationale                                                          |
|----------------------|-----------------------------------|--------------------------------------------------------------------|
| **Frontend framework** | Next.js 15 (App Router)          | Per project requirements. Server Components for initial loads, Client Components for interactivity. |
| **UI library**       | shadcn/ui + Tailwind CSS          | Modern, full ownership, excellent dark mode, TanStack Table integration. |
| **Map library**      | Leaflet + react-leaflet           | Free, no API token, sufficient performance with clustering. MapLibre GL JS as upgrade path. |
| **Map tiles**        | CartoDB Positron (light) / Dark Matter (dark) | Free, clean, minimal -- ideal for data overlay maps. |
| **Marker clustering** | Supercluster (via use-supercluster hook) | Handles 100K+ markers in 1-2 seconds. Client-side for < 50K, server-side for larger. |
| **Data table**       | TanStack Table (via shadcn DataTable) | Server-side pagination/sort/filter, virtual scrolling, fully typed. |
| **PDF viewer**       | react-pdf (PDF.js wrapper)        | Free, lightweight, sufficient for document preview in review queue. |
| **API integration**  | Next.js rewrites + OpenAPI codegen | Proxy avoids CORS; auto-generated TypeScript client ensures type safety. |
| **Real-time updates** | Server-Sent Events (SSE)         | Simple, one-way, native browser support. Perfect for scrape progress. |
| **Backend API**      | FastAPI with sse-starlette        | Already decided. SSE support via sse-starlette package. |
| **Containerization** | Docker Compose                    | 3-service stack: frontend, backend, PostgreSQL. Named volumes for data persistence. |

### Key Architecture Decisions

1. **SSE for progress, not WebSockets** -- Scraping progress is one-way server-to-client. SSE is simpler, requires no extra client libraries, and reconnects automatically.

2. **Side panel for map details, not popups** -- Clicking a well pin opens a side panel (not a map popup) to provide enough space for document lists, production data, and tabular information.

3. **Client-side clustering with Supercluster** -- For the expected scale (10K-50K wells across 10 states), client-side clustering is sufficient. Server-side clustering is the upgrade path if data grows beyond 100K wells.

4. **Dynamic imports for Leaflet** -- Leaflet requires `window`/`document`, so it must be dynamically imported with `ssr: false` in Next.js App Router. This is a well-documented pattern.

5. **shadcn/ui over Mantine** -- Despite Mantine's faster setup for dashboards, shadcn/ui's full code ownership, Tailwind alignment, and extensive community make it the better long-term choice for a project that needs customization.

6. **react-pdf for document preview** -- Lightweight, free, and sufficient for the side-by-side review workflow. No need for paid PDF viewer SDKs for an internal tool.

7. **Separate dev and prod Docker configs** -- Development uses volume mounts and hot reload; production uses multi-stage builds and multiple Uvicorn workers.

### Project Structure

```
og-scraper/
  frontend/                     # Next.js application
    src/
      app/                      # App Router pages
        (dashboard)/
          page.tsx              # Dashboard home / search
          map/page.tsx          # Interactive well map
          review/page.tsx       # Review queue
          scrape/page.tsx       # Scraping control panel
          files/page.tsx        # File browser
          wells/[id]/page.tsx   # Well detail page
        layout.tsx              # Root layout with sidebar
      components/
        ui/                     # shadcn/ui components
        map/                    # Map-related components
          WellMap.tsx           # Main map (client component)
          MapFilters.tsx        # Filter controls
          WellDetailPanel.tsx   # Side panel for well details
        review/                 # Review queue components
          ReviewInterface.tsx   # Side-by-side review
          ReviewQueue.tsx       # Queue list
        scrape/                 # Scraping UI components
          StateCard.tsx         # Per-state scrape control
          ProgressDisplay.tsx   # Real-time progress
        search/                 # Search components
          SearchBar.tsx
          DocumentTable.tsx
          DocumentPreview.tsx
      hooks/
        use-scrape-progress.ts  # SSE hook for scrape progress
        use-document-search.ts  # Search with filters
        use-wells.ts            # Well data fetching
      api-client/               # Auto-generated from OpenAPI
    Dockerfile.dev
    Dockerfile.prod
    next.config.js

  backend/                      # FastAPI application
    app/
      main.py                   # FastAPI app entry
      api/                      # API route handlers
        wells.py
        documents.py
        search.py
        scrape.py
        review.py
        files.py
      models/                   # SQLAlchemy models
      schemas/                  # Pydantic schemas
      services/                 # Business logic
      scrapers/                 # Scrapy + Playwright scrapers
    Dockerfile.dev
    Dockerfile.prod
    requirements.txt

  docker-compose.yml            # Development config
  docker-compose.prod.yml       # Production overrides
```

---

## Sources

### Next.js + FastAPI Integration
- [Next.js FastAPI Template (Vinta Software)](https://www.vintasoftware.com/blog/next-js-fastapi-template)
- [Vinta Software Template - GitHub](https://github.com/vintasoftware/nextjs-fastapi-template)
- [Streaming APIs with FastAPI and Next.js](https://sahansera.dev/streaming-apis-python-nextjs-part2/)
- [Next.js rewrites documentation](https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites)
- [Full-Stack Type Safety with FastAPI and Next.js](https://abhayramesh.com/blog/type-safe-fullstack)
- [Vinta Software Type Safety Blog](https://www.vintasoftware.com/blog/type-safety-fastapi-nextjs-architecture)
- [Orval - OpenAPI TypeScript Client Generator](https://orval.dev/)

### Real-Time Updates (SSE)
- [FastAPI SSE Tutorial](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- [SSE in Next.js - Pedro Alonso](https://www.pedroalonso.net/blog/sse-nextjs-real-time-notifications/)
- [Streaming in Next.js 15: WebSockets vs SSE (HackerNoon)](https://hackernoon.com/streaming-in-nextjs-15-websockets-vs-server-sent-events)
- [FastAPI Streaming Responses](https://medium.com/@bhagyarana80/fastapi-streaming-responses-real-time-without-websockets-bc6b071f5d9e)

### Map Implementation
- [Cluster Thousands of Markers with Leaflet](https://www.samikuikka.com/en/blog/how-to-cluster-thousand-of-markers-with-leaflet/)
- [Leaflet Marker Clustering with Supercluster](https://www.leighhalliday.com/leaflet-clustering)
- [use-supercluster - GitHub](https://github.com/leighhalliday/use-supercluster)
- [react-leaflet-cluster - npm](https://www.npmjs.com/package/react-leaflet-cluster)
- [MapLibre GL JS - GitHub](https://github.com/maplibre/maplibre-gl-js)
- [Mapbox GL JS vs Leaflet vs MapLibre (PkgPulse)](https://www.pkgpulse.com/blog/mapbox-vs-leaflet-vs-maplibre-interactive-maps-2026)
- [MapLibre GL JS vs Leaflet (Jawg Blog)](https://blog.jawg.io/maplibre-gl-vs-leaflet-choosing-the-right-tool-for-your-interactive-map/)
- [Leaflet Provider Demo](https://leaflet-extras.github.io/leaflet-providers/preview/)
- [react-leaflet Popup Documentation](https://react-leaflet.js.org/docs/example-popup-marker/)
- [React Leaflet on Next.js 15 (App Router)](https://xxlsteve.net/blog/react-leaflet-on-next-15/)
- [Making React-Leaflet work with Next.js](https://placekit.io/blog/articles/making-react-leaflet-work-with-nextjs-493i)
- [Handle Millions of Points with Leaflet](https://alfiankan.medium.com/handle-millions-of-location-points-with-leaflet-without-breaking-the-browser-f69709a50861)

### UI Components
- [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/radix/data-table)
- [Building Dynamic Tables with Shadcn and TanStack](https://devpalma.com/en/posts/shadcn-tables)
- [Modern Dashboard with Next.js 15, TanStack Table, and shadcn/ui](https://medium.com/@oruchan.asar/building-a-modern-dashboard-with-next-js-15-redux-toolkit-tanstack-table-and-shadcn-ui-5fa1bfa5f2b7)
- [React UI Libraries 2025 Comparison (Makers' Den)](https://makersden.io/blog/react-ui-libs-2025-comparing-shadcn-radix-mantine-mui-chakra)
- [Mantine vs shadcn/ui Comparison 2026](https://saasindie.com/blog/mantine-vs-shadcn-ui-comparison)
- [Build a Dashboard with shadcn/ui Guide](https://designrevision.com/blog/shadcn-dashboard-tutorial)

### PDF Viewer
- [react-pdf - npm](https://www.npmjs.com/package/react-pdf)
- [react-pdf - GitHub](https://github.com/wojtekmaj/react-pdf)
- [Next.js PDF Viewer with React-PDF (Nutrient)](https://www.nutrient.io/blog/how-to-build-a-nextjs-pdf-viewer/)

### Docker Compose
- [Full Stack Next.js, FastAPI, PostgreSQL with Docker](https://www.travisluong.com/how-to-develop-a-full-stack-next-js-fastapi-postgresql-app-using-docker/)
- [FastAPI in Docker (Official Docs)](https://fastapi.tiangolo.com/deployment/docker/)
- [Next.js Docker Hot Reload (Eli Front)](https://medium.com/@elifront/best-next-js-docker-compose-hot-reload-production-ready-docker-setup-28a9125ba1dc)
- [Enabling Hot Reloading for Next.js in Docker](https://dev.to/yuvraajsj18/enabling-hot-reloading-for-nextjs-in-docker-4k39)
- [Docker Hot Reloading for Node.js, Python, Go](https://oneuptime.com/blog/post/2026-01-06-docker-hot-reloading/view)
- [fastapi-nextjs GitHub Template](https://github.com/Nneji123/fastapi-nextjs)
