# Task 5.3: Interactive Map

## Objective

Implement the interactive well map page using Leaflet with react-leaflet, OpenStreetMap/CartoDB tiles (fully free), Supercluster for client-side clustering of 10K-50K markers, viewport-based data fetching, map filter controls, and click-to-detail interaction that opens a well detail panel alongside the map.

## Context

The interactive map is a core dashboard feature (DISCOVERY D12, D13, D25). Each well is plotted by lat/long coordinates. At low zoom levels, wells cluster to maintain performance. Clicking a pin shows well details alongside the map. The map fetches wells from the backend's bounding-box endpoint (`GET /api/v1/map/wells`) built in Phase 3 (Task 3.4). Leaflet requires special handling in Next.js because it depends on browser APIs (`window`, `document`) and cannot be server-side rendered.

## Dependencies

- Task 5.1 - Frontend foundation (layout, API client, types)
- Task 3.4 - Map API endpoint (`GET /api/v1/map/wells` with bounding box query)

## Blocked By

- 5.1, 3.4

## Research Findings

Key findings from research files relevant to this task:

- From `dashboard-map-implementation.md` Section 2.1: Leaflet + react-leaflet is the recommended library. Completely free, sufficient performance with Supercluster clustering for 10K-50K markers. MapLibre GL JS is the upgrade path if wells exceed 100K.
- From `dashboard-map-implementation.md` Section 2.3: Supercluster benchmarks -- 100K markers clustered in 1-2 seconds. Config: `{ radius: 75, maxZoom: 17 }`. Use `use-supercluster` hook.
- From `dashboard-map-implementation.md` Section 2.4: Leaflet SSR fix requires two-layer dynamic import -- create map as `'use client'` component, then `dynamic(() => import(...), { ssr: false })` in the page.
- From `nextjs-dashboard` skill: Three critical Leaflet pitfalls: (1) CSS must be imported explicitly, (2) default marker icons break in bundlers and need manual fix, (3) Supercluster must run in client component only.
- From `nextjs-dashboard` skill: Tile providers -- Primary: CartoDB Positron (light), Dark mode: CartoDB Dark Matter, Fallback: OpenStreetMap standard. All free, no API key.
- From `nextjs-dashboard` skill: Map filtering happens BEFORE Supercluster -- apply filters to data array, then pass filtered array to `useSupercluster`.
- From `dashboard-map-implementation.md` Section 2.5: Side panel pattern (recommended) -- clicking a marker opens a slide-out panel alongside the map, not a popup. More space for document lists and tabular data.

## Implementation Plan

### Step 1: Create Map Data Fetching Hook

Build a hook that fetches wells based on the current map viewport (bounding box) and zoom level. Debounce requests to avoid flooding the API during pan/zoom.

```typescript
// frontend/src/hooks/use-map-wells.ts
'use client';

import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import type { Well } from '@/lib/types';
import { useCallback, useState, useRef } from 'react';

export interface MapBounds {
  minLat: number;
  maxLat: number;
  minLng: number;
  maxLng: number;
}

export interface MapFilters {
  state?: string;
  operator?: string;
  status?: string;
}

export function useMapWells(bounds: MapBounds | null, filters: MapFilters = {}) {
  const params = new URLSearchParams();
  if (bounds) {
    params.set('min_lat', bounds.minLat.toFixed(6));
    params.set('max_lat', bounds.maxLat.toFixed(6));
    params.set('min_lng', bounds.minLng.toFixed(6));
    params.set('max_lng', bounds.maxLng.toFixed(6));
  }
  params.set('limit', '5000'); // Max wells per viewport request
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });

  const key = bounds ? `/api/v1/map/wells?${params.toString()}` : null;

  return useSWR<Well[]>(key, fetcher, {
    // Dedupe rapid viewport changes
    dedupingInterval: 500,
    keepPreviousData: true,
  });
}
```

### Step 2: Fix Leaflet Default Marker Icons

Leaflet's default marker icon paths break in Webpack/Turbopack bundlers. Create a utility that fixes this. This must run once before any markers render.

```typescript
// frontend/src/components/map/fix-leaflet-icons.ts
import L from 'leaflet';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

export function fixLeafletIcons() {
  delete (L.Icon.Default.prototype as any)._getIconUrl;
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: markerIcon2x.src,
    iconUrl: markerIcon.src,
    shadowUrl: markerShadow.src,
  });
}
```

### Step 3: Create Custom Cluster Icon Factory

Build a function that returns a Leaflet DivIcon for cluster markers, showing the point count with size/color based on count.

```typescript
// frontend/src/components/map/cluster-icon.ts
import L from 'leaflet';

export function createClusterIcon(pointCount: number): L.DivIcon {
  const size = pointCount < 100 ? 30 : pointCount < 1000 ? 40 : 50;
  const color = pointCount < 100 ? '#3b82f6' : pointCount < 1000 ? '#f59e0b' : '#ef4444';

  return L.divIcon({
    html: `<div style="
      background-color: ${color};
      color: white;
      width: ${size}px;
      height: ${size}px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: bold;
      border: 2px solid white;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    ">${pointCount}</div>`,
    className: 'cluster-icon',
    iconSize: L.point(size, size),
  });
}
```

### Step 4: Create Custom Well Pin Icon Factory

Create distinct icons for individual well markers, color-coded by well status.

```typescript
// frontend/src/components/map/well-icon.ts
import L from 'leaflet';
import type { WellStatus } from '@/lib/types';

const STATUS_COLORS: Record<WellStatus, string> = {
  active: '#22c55e',       // green
  inactive: '#6b7280',     // gray
  plugged: '#ef4444',      // red
  permitted: '#3b82f6',    // blue
  drilling: '#f59e0b',     // yellow
  completed: '#8b5cf6',    // purple
  shut_in: '#f97316',      // orange
  temporarily_abandoned: '#a855f7',
  unknown: '#9ca3af',
};

export function createWellIcon(status: WellStatus): L.DivIcon {
  const color = STATUS_COLORS[status] || STATUS_COLORS.unknown;
  return L.divIcon({
    html: `<div style="
      background-color: ${color};
      width: 12px;
      height: 12px;
      border-radius: 50%;
      border: 2px solid white;
      box-shadow: 0 1px 3px rgba(0,0,0,0.4);
    "></div>`,
    className: 'well-icon',
    iconSize: L.point(12, 12),
    iconAnchor: L.point(6, 6),
  });
}
```

### Step 5: Create MapEvents Helper Component

A react-leaflet component that listens to map move/zoom events and reports the current bounds and zoom level to the parent.

```typescript
// frontend/src/components/map/map-events.tsx
'use client';

import { useMapEvents } from 'react-leaflet';
import type { MapBounds } from '@/hooks/use-map-wells';

interface MapEventsProps {
  onBoundsChange: (bounds: MapBounds) => void;
  onZoomChange: (zoom: number) => void;
}

export function MapEvents({ onBoundsChange, onZoomChange }: MapEventsProps) {
  const map = useMapEvents({
    moveend: () => {
      const b = map.getBounds();
      onBoundsChange({
        minLat: b.getSouth(),
        maxLat: b.getNorth(),
        minLng: b.getWest(),
        maxLng: b.getEast(),
      });
      onZoomChange(map.getZoom());
    },
    zoomend: () => {
      onZoomChange(map.getZoom());
    },
  });

  return null;
}
```

### Step 6: Build the Core WellMap Component

The main map component using react-leaflet with Supercluster integration. This is a `'use client'` component that will be dynamically imported.

```typescript
// frontend/src/components/map/well-map.tsx
'use client';

import { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import useSupercluster from 'use-supercluster';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import { fixLeafletIcons } from './fix-leaflet-icons';
import { createClusterIcon } from './cluster-icon';
import { createWellIcon } from './well-icon';
import { MapEvents } from './map-events';
import type { Well, WellStatus } from '@/lib/types';
import type { MapBounds } from '@/hooks/use-map-wells';

fixLeafletIcons();

interface WellMapProps {
  wells: Well[];
  onWellClick: (well: Well) => void;
  selectedWellId?: string | null;
}

export default function WellMap({ wells, onWellClick, selectedWellId }: WellMapProps) {
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [zoom, setZoom] = useState(5);
  const mapRef = useRef<L.Map | null>(null);

  // Convert wells to GeoJSON points for Supercluster
  const points = useMemo(() =>
    wells.map(well => ({
      type: 'Feature' as const,
      properties: {
        cluster: false,
        wellId: well.id,
        apiNumber: well.api_number,
        wellName: well.well_name,
        operatorName: well.operator_name,
        stateCode: well.state_code,
        status: well.status,
        docCount: well.doc_count,
      },
      geometry: {
        type: 'Point' as const,
        coordinates: [well.longitude, well.latitude],
      },
    })),
    [wells],
  );

  const superclusterBounds: [number, number, number, number] | undefined = bounds
    ? [bounds.minLng, bounds.minLat, bounds.maxLng, bounds.maxLat]
    : undefined;

  const { clusters, supercluster } = useSupercluster({
    points,
    bounds: superclusterBounds,
    zoom,
    options: { radius: 75, maxZoom: 17 },
  });

  return (
    <MapContainer
      center={[39.8283, -98.5795]}
      zoom={5}
      style={{ height: '100%', width: '100%' }}
      ref={mapRef}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>'
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
              icon={createClusterIcon(point_count)}
              eventHandlers={{
                click: () => {
                  if (supercluster) {
                    const expansionZoom = supercluster.getClusterExpansionZoom(cluster.id);
                    mapRef.current?.setView([lat, lng], expansionZoom, { animate: true });
                  }
                },
              }}
            />
          );
        }

        const wellStatus = cluster.properties.status as WellStatus;
        return (
          <Marker
            key={cluster.properties.wellId}
            position={[lat, lng]}
            icon={createWellIcon(wellStatus)}
            eventHandlers={{
              click: () => {
                // Find the full well object and pass to parent
                const well = wells.find(w => w.id === cluster.properties.wellId);
                if (well) onWellClick(well);
              },
            }}
          >
            <Popup>
              <div className="text-sm">
                <p className="font-bold">{cluster.properties.wellName}</p>
                <p className="text-xs font-mono">{cluster.properties.apiNumber}</p>
                <p>{cluster.properties.operatorName}</p>
                <p>{cluster.properties.stateCode} | {cluster.properties.docCount} docs</p>
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
```

### Step 7: Create Map Filter Controls

A floating filter panel on the map for state, operator, and status filtering. Filters are applied to the data array BEFORE Supercluster (per the skill's guidance).

```typescript
// frontend/src/components/map/map-controls.tsx
'use client';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { X } from 'lucide-react';
import type { MapFilters } from '@/hooks/use-map-wells';

const STATES = [
  { code: 'TX', name: 'Texas' }, { code: 'NM', name: 'New Mexico' },
  { code: 'ND', name: 'North Dakota' }, { code: 'OK', name: 'Oklahoma' },
  { code: 'CO', name: 'Colorado' }, { code: 'WY', name: 'Wyoming' },
  { code: 'LA', name: 'Louisiana' }, { code: 'PA', name: 'Pennsylvania' },
  { code: 'CA', name: 'California' }, { code: 'AK', name: 'Alaska' },
];

interface MapControlsProps {
  filters: MapFilters;
  onFiltersChange: (filters: MapFilters) => void;
  wellCount: number;
}

export function MapControls({ filters, onFiltersChange, wellCount }: MapControlsProps) {
  return (
    <Card className="absolute top-4 left-14 z-[1000] w-72 shadow-lg">
      <CardContent className="p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{wellCount.toLocaleString()} wells</span>
          <Button variant="ghost" size="sm" onClick={() => onFiltersChange({})}>
            <X className="h-3 w-3 mr-1" /> Clear
          </Button>
        </div>
        <Select
          value={filters.state || ''}
          onValueChange={(value) => onFiltersChange({ ...filters, state: value || undefined })}
        >
          <SelectTrigger><SelectValue placeholder="All States" /></SelectTrigger>
          <SelectContent>
            {STATES.map(s => (
              <SelectItem key={s.code} value={s.code}>{s.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {/* Similar selects for operator and status */}
      </CardContent>
    </Card>
  );
}
```

### Step 8: Create Map Legend

A small legend showing what the pin colors mean (well status).

```typescript
// frontend/src/components/map/map-legend.tsx
// Positioned absolutely at bottom-right of the map
// Shows colored circles with status labels
```

### Step 9: Build the Map Page with Dynamic Import

The map page dynamically imports the WellMap component with `ssr: false` to avoid Leaflet SSR errors. It manages filter state, fetches wells, and renders the detail panel alongside the map.

```typescript
// frontend/src/app/(dashboard)/map/page.tsx
'use client';

import { useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { useMapWells, type MapBounds, type MapFilters } from '@/hooks/use-map-wells';
import { MapControls } from '@/components/map/map-controls';
import { MapLegend } from '@/components/map/map-legend';
import { WellDetailPanel } from '@/components/wells/well-detail-panel';
import { Skeleton } from '@/components/ui/skeleton';
import type { Well } from '@/lib/types';

// Dynamic import with SSR disabled -- Leaflet requires browser APIs
const WellMap = dynamic(() => import('@/components/map/well-map'), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full" />,
});

export default function MapPage() {
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [filters, setFilters] = useState<MapFilters>({});
  const [selectedWell, setSelectedWell] = useState<Well | null>(null);

  const { data: wells, isLoading } = useMapWells(bounds, filters);

  const handleWellClick = useCallback((well: Well) => {
    setSelectedWell(well);
  }, []);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] -m-6">
      {/* Map fills available space */}
      <div className="relative flex-1">
        <WellMap
          wells={wells ?? []}
          onWellClick={handleWellClick}
          selectedWellId={selectedWell?.id}
        />
        <MapControls
          filters={filters}
          onFiltersChange={setFilters}
          wellCount={wells?.length ?? 0}
        />
        <MapLegend />
      </div>

      {/* Detail panel slides in from right */}
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

**Important**: The map page uses negative margins (`-m-6`) to fill the full content area since the layout has padding. The map and panel take the full height minus the header.

### Step 10: Handle Viewport-Based Data Fetching

The map needs to fetch wells when the viewport changes (user pans or zooms). This is handled by the `MapEvents` component reporting bounds changes, which updates the `bounds` state in the page, which triggers `useMapWells` to fetch from the API.

The flow is:
1. Map loads with default US center view
2. `MapEvents` fires `moveend` with initial bounds
3. `setBounds` updates state
4. `useMapWells` fires `GET /api/v1/map/wells?min_lat=...&max_lat=...&min_lng=...&max_lng=...`
5. Wells are passed to `WellMap` -> Supercluster clusters them
6. User pans/zooms -> cycle repeats

SWR's `dedupingInterval: 500` prevents excessive API calls during rapid pan/zoom.

## Files to Create

- `frontend/src/app/(dashboard)/map/page.tsx` - Map page with dynamic import and detail panel
- `frontend/src/components/map/well-map.tsx` - Core Leaflet map with Supercluster (client component)
- `frontend/src/components/map/map-events.tsx` - Map event listener helper component
- `frontend/src/components/map/map-controls.tsx` - Floating filter controls over the map
- `frontend/src/components/map/map-legend.tsx` - Pin color legend
- `frontend/src/components/map/fix-leaflet-icons.ts` - Leaflet default icon fix
- `frontend/src/components/map/cluster-icon.ts` - Cluster marker icon factory
- `frontend/src/components/map/well-icon.ts` - Well pin icon factory
- `frontend/src/hooks/use-map-wells.ts` - SWR hook for viewport-based well fetching

## Files to Modify

- None (reuses `WellDetailPanel` from Task 5.2)

## Contracts

### Provides (for downstream tasks)

- **Map page**: Route `/map` with interactive well map, clustering, filters, and detail panel
- **WellMap component**: `<WellMap wells={wells} onWellClick={fn} />` -- reusable Leaflet map with Supercluster
- **Map hooks**: `useMapWells(bounds, filters)` for viewport-based data fetching
- **Map utilities**: `createClusterIcon()`, `createWellIcon()`, `fixLeafletIcons()` reusable across components

### Consumes (from upstream tasks)

- Task 5.1: Layout shell, API client, type definitions, shadcn/ui components
- Task 5.2: `WellDetailPanel` component for the slide-out detail view
- Task 3.4: `GET /api/v1/map/wells?min_lat=&max_lat=&min_lng=&max_lng=&limit=` endpoint

## Acceptance Criteria

- [ ] Map page renders with CartoDB Positron tiles without any console errors
- [ ] Well pins appear on the map when well data is returned from the API
- [ ] Supercluster clusters pins at low zoom levels (zoom 4-8)
- [ ] Individual pins are visible at high zoom levels (zoom 12+)
- [ ] Clicking a cluster marker zooms in to expand it
- [ ] Clicking an individual well pin opens a popup with well name, API number, operator
- [ ] Clicking a well pin also opens the detail side panel alongside the map
- [ ] Panning/zooming the map triggers new data fetches for the visible viewport
- [ ] Map filter controls (state, operator, status) narrow the displayed wells
- [ ] Map legend shows well status color coding
- [ ] No SSR errors (Leaflet loaded client-side only via dynamic import)
- [ ] Map fills the full content area (no scrollbars, no overflow)
- [ ] Build succeeds without errors

## Testing Protocol

### Unit/Integration Tests

- Test file: `frontend/src/__tests__/hooks/use-map-wells.test.ts`
- Test cases:
  - [ ] `useMapWells` returns null key when bounds is null (no fetch)
  - [ ] `useMapWells` constructs correct URL with bounds and filters
  - [ ] `useMapWells` includes limit=5000 in query params

- Test file: `frontend/src/__tests__/components/map/cluster-icon.test.ts`
- Test cases:
  - [ ] `createClusterIcon` returns correct size for < 100 points
  - [ ] `createClusterIcon` returns correct size for 100-999 points
  - [ ] `createClusterIcon` returns correct size for 1000+ points

### Browser Testing (Playwright MCP)

- Start: `cd frontend && npm run dev` (ensure backend is running with well data that has lat/long coordinates)
- Navigate to: `http://localhost:3000/map`
- Actions:
  - Verify map renders with tiles (not a blank container)
  - Verify well pins or clusters appear on the map
  - Zoom in to a cluster, verify it expands into smaller clusters or individual pins
  - Click an individual well pin, verify popup appears
  - Verify detail panel opens on the right side
  - Close the detail panel, verify map returns to full width
  - Select "TX" from the state filter, verify only Texas wells are displayed
  - Clear filters, verify all wells return
  - Pan the map to a new area, verify wells update for the new viewport
- Verify:
  - No `window is not defined` or `document is not defined` errors in console
  - No Leaflet CSS warnings (markers render correctly with icons)
  - Map is responsive (fills container)
- User-emulating flow:
  1. User navigates to Map page from sidebar
  2. Sees US map with clustered well markers
  3. Zooms into Texas
  4. Sees clusters break into individual pins
  5. Clicks a pin -- popup shows well name and API number
  6. Detail panel slides in showing full well info
  7. Clicks "Documents" tab in panel to see related docs
  8. Closes panel, selects "OK" from state filter
  9. Map shows only Oklahoma wells
- Screenshot: Map with clusters visible, map zoomed in with individual pins, detail panel open

### Build/Lint/Type Checks

- [ ] `npm run build` succeeds (no SSR errors from Leaflet)
- [ ] `npx tsc --noEmit` passes
- [ ] No TypeScript errors in map components

## Skills to Read

- `nextjs-dashboard` - Leaflet dynamic import pattern, Supercluster configuration, tile providers, default icon fix, SSR pitfalls, map filtering guidance
- `og-scraper-architecture` - Map API endpoint format, well location data (lat/long decimal degrees)

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` - Section 2 (Interactive Map Implementation) -- complete Leaflet setup, Supercluster config, SSR fix, click-to-detail patterns, coordinate handling, map filtering

## Git

- Branch: `feat/5.3-interactive-map`
- Commit message prefix: `Task 5.3:`
