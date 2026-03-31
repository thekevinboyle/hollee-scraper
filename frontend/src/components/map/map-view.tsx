"use client";

import { useEffect, useState, useCallback } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  useMapEvents,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { WellMapPoint } from "@/lib/schemas/api";
import { STATUS_COLORS } from "@/lib/constants";
import { API_BASE_URL } from "@/lib/env";

interface Bounds {
  min_lat: number;
  max_lat: number;
  min_lng: number;
  max_lng: number;
}

function getColor(status: string | null): string {
  return STATUS_COLORS[(status || "unknown").toLowerCase()] || "#9ca3af";
}

function MapEvents({
  onBoundsChange,
}: {
  onBoundsChange: (bounds: Bounds) => void;
}) {
  useMapEvents({
    moveend: (e) => {
      const b = e.target.getBounds();
      onBoundsChange({
        min_lat: b.getSouth(),
        max_lat: b.getNorth(),
        min_lng: b.getWest(),
        max_lng: b.getEast(),
      });
    },
  });
  return null;
}

export default function MapView() {
  const [wells, setWells] = useState<WellMapPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");

  const fetchWells = useCallback(
    async (bounds: Bounds) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          min_lat: String(bounds.min_lat),
          max_lat: String(bounds.max_lat),
          min_lng: String(bounds.min_lng),
          max_lng: String(bounds.max_lng),
          limit: "2000",
        });
        if (statusFilter) params.set("well_status", statusFilter);
        const res = await fetch(`${API_BASE_URL}/api/v1/map/wells?${params}`);
        if (res.ok) {
          const data = await res.json();
          setWells(Array.isArray(data) ? data : []);
        }
      } catch {
        // Backend not available
      } finally {
        setLoading(false);
      }
    },
    [statusFilter]
  );

  useEffect(() => {
    fetchWells({ min_lat: 24, max_lat: 50, min_lng: -130, max_lng: -65 });
  }, [fetchWells]);

  return (
    <div className="relative">
      {/* Controls overlay */}
      <div className="absolute top-3 left-12 z-[1000] flex gap-2">
        <div className="bg-white/95 shadow rounded px-3 py-1.5 text-sm font-medium">
          {wells.length} wells
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-white/95 shadow rounded px-2 py-1 text-sm border-0"
        >
          <option value="">All Statuses</option>
          {Object.keys(STATUS_COLORS).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {loading && (
        <div className="absolute top-3 right-3 z-[1000] bg-white/90 shadow px-3 py-1 rounded text-sm text-muted-foreground">
          Loading...
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-6 left-3 z-[1000] bg-white/95 shadow rounded p-2">
        <p className="text-[10px] font-medium mb-1">Status</p>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
          {Object.entries(STATUS_COLORS).map(([status, color]) => (
            <div key={status} className="flex items-center gap-1">
              <div
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span className="text-[10px] capitalize">{status}</span>
            </div>
          ))}
        </div>
      </div>

      <MapContainer
        center={[39.8, -98.5]}
        zoom={4}
        className="h-full w-full rounded-lg"
        style={{ minHeight: "600px" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        />
        <MapEvents onBoundsChange={fetchWells} />
        {wells.map((well) => (
          <CircleMarker
            key={well.id}
            center={[well.latitude, well.longitude]}
            radius={6}
            pathOptions={{
              color: getColor(well.well_status),
              fillColor: getColor(well.well_status),
              fillOpacity: 0.8,
              weight: 1,
            }}
          >
            <Popup>
              <div className="text-sm min-w-[200px]">
                <div className="font-bold mb-1">
                  {well.well_name || "Unnamed Well"}
                </div>
                <table className="text-xs w-full">
                  <tbody>
                    <tr>
                      <td className="text-muted-foreground pr-2 py-0.5">
                        API
                      </td>
                      <td className="font-mono">{well.api_number}</td>
                    </tr>
                    {well.operator_name && (
                      <tr>
                        <td className="text-muted-foreground pr-2 py-0.5">
                          Operator
                        </td>
                        <td>{well.operator_name}</td>
                      </tr>
                    )}
                    <tr>
                      <td className="text-muted-foreground pr-2 py-0.5">
                        Status
                      </td>
                      <td className="capitalize">
                        <span
                          className="inline-block w-2 h-2 rounded-full mr-1"
                          style={{
                            backgroundColor: getColor(well.well_status),
                          }}
                        />
                        {well.well_status || "unknown"}
                      </td>
                    </tr>
                    <tr>
                      <td className="text-muted-foreground pr-2 py-0.5">
                        Coords
                      </td>
                      <td className="font-mono">
                        {well.latitude.toFixed(4)}, {well.longitude.toFixed(4)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
