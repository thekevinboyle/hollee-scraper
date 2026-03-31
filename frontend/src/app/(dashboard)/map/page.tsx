"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";

const MapView = dynamic(() => import("@/components/map/map-view"), {
  ssr: false,
  loading: () => <Skeleton className="h-[600px] w-full rounded-lg" />,
});

export default function MapPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Well Map</h1>
      <MapView />
    </div>
  );
}
