"use client";

import { useEffect, useState, useCallback } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Fix default marker icons for webpack/next.js
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

interface WellPin {
  id: string;
  api_number: string;
  well_name: string;
  operator_name: string;
  state_code: string;
  latitude: number;
  longitude: number;
  status: string;
}

function MapEvents({ onBoundsChange }: { onBoundsChange: (bbox: string) => void }) {
  useMapEvents({
    moveend: (e) => {
      const bounds = e.target.getBounds();
      const bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
      onBoundsChange(bbox);
    },
  });
  return null;
}

export default function MapView() {
  const [wells, setWells] = useState<WellPin[]>([]);
  const [bbox, setBbox] = useState("-130,24,-65,50");

  const fetchWells = useCallback(async (bounds: string) => {
    try {
      const res = await fetch(`/api/v1/map/wells?bbox=${bounds}&limit=1000`);
      if (res.ok) {
        const data = await res.json();
        setWells(Array.isArray(data) ? data : data.features?.map((f: { properties: WellPin; geometry: { coordinates: number[] } }) => ({
          ...f.properties,
          longitude: f.geometry.coordinates[0],
          latitude: f.geometry.coordinates[1],
        })) ?? []);
      }
    } catch {
      // Backend not available yet
    }
  }, []);

  useEffect(() => {
    fetchWells(bbox);
  }, [bbox, fetchWells]);

  return (
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
      <MapEvents onBoundsChange={(b) => setBbox(b)} />
      {wells.map((well) => (
        <Marker key={well.id} position={[well.latitude, well.longitude]}>
          <Popup>
            <div className="text-sm">
              <strong>{well.well_name}</strong>
              <br />
              <span className="font-mono text-xs">{well.api_number}</span>
              <br />
              {well.operator_name} | {well.state_code}
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
