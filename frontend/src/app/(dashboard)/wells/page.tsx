"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { useDebounce } from "@/hooks/use-debounce";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface WellSummary {
  id: string;
  api_number: string;
  well_name: string;
  operator_name: string | null;
  state_code: string;
  county: string | null;
  well_status: string;
  well_type: string | null;
  latitude: number | null;
  longitude: number | null;
  document_count: number;
}

interface WellDetail {
  id: string;
  api_number: string;
  api_10: string | null;
  well_name: string;
  well_number: string | null;
  operator_name: string | null;
  state_code: string;
  county: string | null;
  basin: string | null;
  field_name: string | null;
  lease_name: string | null;
  well_status: string;
  well_type: string | null;
  latitude: number | null;
  longitude: number | null;
  spud_date: string | null;
  completion_date: string | null;
  total_depth: number | null;
  true_vertical_depth: number | null;
  lateral_length: number | null;
  metadata: Record<string, unknown>;
  alternate_ids: Record<string, string>;
  documents: Array<{
    id: string;
    doc_type: string;
    status: string;
    confidence_score: number | null;
    source_url: string;
  }>;
}

interface PaginatedWells {
  items: WellSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

function statusVariant(
  s: string
): "default" | "secondary" | "destructive" | "outline" {
  if (s === "active") return "default";
  if (s === "plugged") return "destructive";
  if (s === "drilling" || s === "completed") return "secondary";
  return "outline";
}

function confidenceColor(score: number) {
  if (score >= 0.85) return "text-green-700";
  if (score >= 0.5) return "text-yellow-700";
  return "text-red-700";
}

const ALL_STATES = ["TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"];
const WELL_STATUSES = ["active", "inactive", "plugged", "permitted", "drilling", "completed", "shut_in", "unknown"];

export default function WellsPage() {
  const urlParams = useSearchParams();
  const [search, setSearch] = useState(urlParams.get("q") || "");
  const [stateFilter, setStateFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [countyFilter, setCountyFilter] = useState("");
  const [operatorFilter, setOperatorFilter] = useState("");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("api_number");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [selectedApi, setSelectedApi] = useState<string | null>(null);
  const debouncedSearch = useDebounce(search);
  const debouncedCounty = useDebounce(countyFilter);
  const debouncedOperator = useDebounce(operatorFilter);

  const params = new URLSearchParams({ page: String(page), page_size: "25", sort_by: sortBy, sort_dir: sortDir });
  if (debouncedSearch) params.set("q", debouncedSearch);
  if (stateFilter) params.set("state", stateFilter);
  if (statusFilter) params.set("well_status", statusFilter);
  if (debouncedCounty) params.set("county", debouncedCounty);
  if (debouncedOperator) params.set("operator", debouncedOperator);

  const { data, isLoading } = useSWR<PaginatedWells>(`/api/v1/wells?${params}`, fetcher);
  const { data: wellDetail } = useSWR<WellDetail>(selectedApi ? `/api/v1/wells/${selectedApi}` : null, fetcher);

  function toggleSort(col: string) {
    if (sortBy === col) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(col);
      setSortDir("asc");
    }
    setPage(1);
  }

  function resetFilters() {
    setSearch("");
    setStateFilter("");
    setStatusFilter("");
    setCountyFilter("");
    setOperatorFilter("");
    setPage(1);
  }

  const hasFilters = search || stateFilter || statusFilter || countyFilter || operatorFilter;

  // Extract production-like data from metadata
  const metadata = wellDetail?.metadata || {};
  const metadataEntries = Object.entries(metadata).filter(
    ([, v]) => v !== null && v !== "" && v !== undefined
  );

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Wells</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <Input
          placeholder="Search wells..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="w-64"
        />
        <select value={stateFilter} onChange={(e) => { setStateFilter(e.target.value); setPage(1); }} className="rounded-md border px-3 py-2 text-sm">
          <option value="">All States</option>
          {ALL_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="rounded-md border px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          {WELL_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <Input
          placeholder="County..."
          value={countyFilter}
          onChange={(e) => { setCountyFilter(e.target.value); setPage(1); }}
          className="w-40"
        />
        <Input
          placeholder="Operator..."
          value={operatorFilter}
          onChange={(e) => { setOperatorFilter(e.target.value); setPage(1); }}
          className="w-48"
        />
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            Clear filters
          </Button>
        )}
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                {[
                  { key: "api_number", label: "API Number" },
                  { key: "well_name", label: "Well Name" },
                  { key: "operator_name", label: "Operator" },
                  { key: "state_code", label: "State" },
                  { key: "county", label: "County" },
                  { key: "well_status", label: "Status" },
                ].map((col) => (
                  <TableHead
                    key={col.key}
                    className="cursor-pointer select-none hover:text-foreground"
                    onClick={() => toggleSort(col.key)}
                  >
                    {col.label}
                    {sortBy === col.key && (
                      <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
                    )}
                  </TableHead>
                ))}
                <TableHead>Docs</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.map((well) => (
                <TableRow key={well.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setSelectedApi(well.api_number)}>
                  <TableCell className="font-mono text-sm">{well.api_number}</TableCell>
                  <TableCell>{well.well_name || "--"}</TableCell>
                  <TableCell>{well.operator_name || "--"}</TableCell>
                  <TableCell className="font-bold">{well.state_code}</TableCell>
                  <TableCell>{well.county || "--"}</TableCell>
                  <TableCell><Badge variant={statusVariant(well.well_status)}>{well.well_status}</Badge></TableCell>
                  <TableCell>{well.document_count}</TableCell>
                </TableRow>
              ))}
              {data?.items.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">No wells found</TableCell></TableRow>
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

      {/* Well Detail Side Panel */}
      <Sheet open={!!selectedApi} onOpenChange={() => setSelectedApi(null)}>
        <SheetContent className="w-[440px] sm:w-[580px] overflow-y-auto">
          {wellDetail ? (
            <>
              <SheetHeader>
                <SheetTitle>{wellDetail.well_name || wellDetail.api_number}</SheetTitle>
              </SheetHeader>

              <div className="mt-6 space-y-4">
                {/* Well Info */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Well Information</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {[
                      ["API Number", <span key="api" className="font-mono">{wellDetail.api_number}</span>],
                      ["Operator", wellDetail.operator_name || "--"],
                      ["State", <span key="st" className="font-bold">{wellDetail.state_code}</span>],
                      ["County", wellDetail.county || "--"],
                      ["Status", <Badge key="status" variant={statusVariant(wellDetail.well_status)}>{wellDetail.well_status}</Badge>],
                      ...(wellDetail.well_type ? [["Well Type", wellDetail.well_type]] : []),
                      ...(wellDetail.basin ? [["Basin", wellDetail.basin]] : []),
                      ...(wellDetail.field_name ? [["Field", wellDetail.field_name]] : []),
                      ...(wellDetail.lease_name ? [["Lease", wellDetail.lease_name]] : []),
                      ...(wellDetail.latitude && wellDetail.longitude ? [["Location", <span key="loc" className="font-mono text-xs">{wellDetail.latitude.toFixed(6)}, {wellDetail.longitude.toFixed(6)}</span>]] : []),
                      ...(wellDetail.total_depth ? [["Total Depth", `${wellDetail.total_depth.toLocaleString()} ft`]] : []),
                      ...(wellDetail.true_vertical_depth ? [["TVD", `${wellDetail.true_vertical_depth.toLocaleString()} ft`]] : []),
                      ...(wellDetail.lateral_length ? [["Lateral Length", `${wellDetail.lateral_length.toLocaleString()} ft`]] : []),
                      ...(wellDetail.spud_date ? [["Spud Date", wellDetail.spud_date]] : []),
                      ...(wellDetail.completion_date ? [["Completion Date", wellDetail.completion_date]] : []),
                    ].map(([label, value], i) => (
                      <div key={i} className="flex justify-between items-center">
                        <span className="text-muted-foreground">{label as string}</span>
                        <span>{value as React.ReactNode}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                {/* Source Metadata */}
                {metadataEntries.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Source Data ({metadataEntries.length} fields)</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="max-h-60 overflow-y-auto space-y-1">
                        {metadataEntries.map(([key, value]) => (
                          <div key={key} className="flex justify-between text-xs py-1 border-b border-muted last:border-0">
                            <span className="text-muted-foreground font-mono truncate mr-2">{key}</span>
                            <span className="text-right truncate max-w-[60%]">{String(value)}</span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Documents */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Documents ({wellDetail.documents?.length ?? 0})</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {wellDetail.documents && wellDetail.documents.length > 0 ? (
                      <div className="space-y-2">
                        {wellDetail.documents.map((doc) => (
                          <div key={doc.id} className="flex items-center justify-between p-2 rounded border text-sm">
                            <div>
                              <Badge variant="outline" className="text-xs">{(doc.doc_type || "unknown").replace(/_/g, " ")}</Badge>
                              <span className="ml-2 text-xs text-muted-foreground">{doc.status}</span>
                            </div>
                            {doc.confidence_score != null && (
                              <span className={`text-xs font-bold ${confidenceColor(doc.confidence_score)}`}>
                                {(doc.confidence_score * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">No documents linked</p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          ) : (
            <div className="space-y-2 mt-6">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-40 w-full" />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
