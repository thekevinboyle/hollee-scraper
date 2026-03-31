"use client";

import { useEffect, useState, useCallback } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Fix default marker icons for webpack/next.js
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)
  ._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

const API_BASE = "http://localhost:8000";

interface WellPin {
  id: string;
  api_number: string;
  well_name: string;
  operator_name: string | null;
  latitude: number;
  longitude: number;
  well_status: string | null;
  well_type: string | null;
}

interface Bounds {
  min_lat: number;
  max_lat: number;
  min_lng: number;
  max_lng: number;
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
  const [wells, setWells] = useState<WellPin[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchWells = useCallback(async (bounds: Bounds) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        min_lat: String(bounds.min_lat),
        max_lat: String(bounds.max_lat),
        min_lng: String(bounds.min_lng),
        max_lng: String(bounds.max_lng),
        limit: "1000",
      });
      const res = await fetch(
        `${API_BASE}/api/v1/map/wells?${params}`
      );
      if (res.ok) {
        const data = await res.json();
        setWells(Array.isArray(data) ? data : []);
      }
    } catch {
      // Backend not available
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load — fetch wells for the default US viewport
  useEffect(() => {
    fetchWells({ min_lat: 24, max_lat: 50, min_lng: -130, max_lng: -65 });
  }, [fetchWells]);

  return (
    <div className="relative">
      {loading && (
        <div className="absolute top-2 right-2 z-[1000] bg-white/80 px-3 py-1 rounded text-sm text-muted-foreground">
          Loading wells...
        </div>
      )}
      <div className="absolute top-2 left-12 z-[1000] bg-white/90 px-3 py-1 rounded text-sm font-medium">
        {wells.length} wells
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
          <Marker key={well.id} position={[well.latitude, well.longitude]}>
            <Popup>
              <div className="text-sm">
                <strong>{well.well_name || "Unnamed Well"}</strong>
                <br />
                <span className="font-mono text-xs">{well.api_number}</span>
                <br />
                {well.operator_name && (
                  <>
                    {well.operator_name}
                    <br />
                  </>
                )}
                Status: {well.well_status || "unknown"}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
