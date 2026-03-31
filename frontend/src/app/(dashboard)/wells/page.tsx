"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Well, PaginatedResponse } from "@/lib/types";
import { useDebounce } from "@/hooks/use-debounce";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";

export default function WellsPage() {
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
  const [page, setPage] = useState(1);
  const [selectedWell, setSelectedWell] = useState<Well | null>(null);
  const debouncedSearch = useDebounce(search);

  const params = new URLSearchParams({ page: String(page), page_size: "25" });
  if (debouncedSearch) params.set("q", debouncedSearch);
  if (state) params.set("state", state);

  const { data, isLoading } = useSWR<PaginatedResponse<Well>>(
    `/api/v1/wells?${params}`, fetcher
  );

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Wells</h1>
      <div className="flex gap-4 mb-4">
        <Input placeholder="Search wells..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} className="max-w-sm" />
        <select value={state} onChange={(e) => { setState(e.target.value); setPage(1); }} className="rounded-md border px-3 py-2 text-sm">
          <option value="">All States</option>
          {["TX","NM","ND","OK","CO","WY","LA","PA","CA","AK"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>API Number</TableHead>
                <TableHead>Well Name</TableHead>
                <TableHead>Operator</TableHead>
                <TableHead>State</TableHead>
                <TableHead>County</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.map((well) => (
                <TableRow key={well.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setSelectedWell(well)}>
                  <TableCell className="font-mono text-sm">{well.api_number}</TableCell>
                  <TableCell>{well.well_name}</TableCell>
                  <TableCell>{well.operator_name}</TableCell>
                  <TableCell>{well.state_code}</TableCell>
                  <TableCell>{well.county}</TableCell>
                  <TableCell><Badge variant={well.status === "active" ? "default" : "secondary"}>{well.status}</Badge></TableCell>
                </TableRow>
              ))}
              {data?.items.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No wells found</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
          <div className="flex justify-between items-center mt-4">
            <span className="text-sm text-muted-foreground">{data?.total ?? 0} wells total</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span className="flex items-center px-2 text-sm">Page {page} of {data?.total_pages ?? 1}</span>
              <Button variant="outline" size="sm" disabled={page >= (data?.total_pages ?? 1)} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        </>
      )}

      <Sheet open={!!selectedWell} onOpenChange={() => setSelectedWell(null)}>
        <SheetContent className="w-[400px] sm:w-[540px]">
          {selectedWell && (
            <>
              <SheetHeader><SheetTitle>{selectedWell.well_name}</SheetTitle></SheetHeader>
              <div className="mt-4 space-y-3 text-sm">
                <div><strong>API Number:</strong> <span className="font-mono">{selectedWell.api_number}</span></div>
                <div><strong>Operator:</strong> {selectedWell.operator_name}</div>
                <div><strong>State:</strong> {selectedWell.state_code}</div>
                <div><strong>County:</strong> {selectedWell.county}</div>
                <div><strong>Status:</strong> <Badge>{selectedWell.status}</Badge></div>
                {selectedWell.latitude && selectedWell.longitude && (
                  <div><strong>Location:</strong> {selectedWell.latitude.toFixed(6)}, {selectedWell.longitude.toFixed(6)}</div>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
