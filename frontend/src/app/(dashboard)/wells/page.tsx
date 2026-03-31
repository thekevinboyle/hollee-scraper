"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { useDebounce } from "@/hooks/use-debounce";
import type { WellSummary, WellDetail } from "@/lib/schemas/api";
import { STATE_CODES, WELL_STATUSES } from "@/lib/constants";
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

  // Extract metadata and helper for safe rendering
  const metadata = wellDetail?.metadata || {};
  const m = (key: string): string | null => {
    const v = metadata[key];
    if (v === null || v === undefined || v === "") return null;
    return String(v);
  };
  const mNum = (key: string): number | null => {
    const v = metadata[key];
    if (v === null || v === undefined) return null;
    const n = Number(v);
    return isNaN(n) ? null : n;
  };
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
          {STATE_CODES.map((s) => <option key={s} value={s}>{s}</option>)}
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

                {/* Production Data (WY has cumulative production) */}
                {(mNum("cumulative_oil_bbl") || mNum("cumulative_gas_mcf") || mNum("cumulative_water_bbl")) && (
                  <Card className="border-green-200 bg-green-50/30">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Cumulative Production</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      {mNum("cumulative_oil_bbl") != null && mNum("cumulative_oil_bbl")! > 0 && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Oil</span>
                          <span className="font-bold">{mNum("cumulative_oil_bbl")!.toLocaleString()} BBL</span>
                        </div>
                      )}
                      {mNum("cumulative_gas_mcf") != null && mNum("cumulative_gas_mcf")! > 0 && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Gas</span>
                          <span className="font-bold">{mNum("cumulative_gas_mcf")!.toLocaleString()} MCF</span>
                        </div>
                      )}
                      {mNum("cumulative_water_bbl") != null && mNum("cumulative_water_bbl")! > 0 && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Water</span>
                          <span className="font-bold">{mNum("cumulative_water_bbl")!.toLocaleString()} BBL</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Geological & Depth Data */}
                {(m("bottom_formation") || mNum("max_md") || mNum("max_tvd") || mNum("ground_elevation_ft") || wellDetail.total_depth) && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Geological Data</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      {m("bottom_formation") && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Target Formation</span>
                          <span className="font-medium">{m("bottom_formation")}</span>
                        </div>
                      )}
                      {(wellDetail.total_depth || mNum("max_md")) && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Measured Depth</span>
                          <span>{(wellDetail.total_depth || mNum("max_md") || 0).toLocaleString()} ft</span>
                        </div>
                      )}
                      {mNum("max_tvd") && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">True Vertical Depth</span>
                          <span>{mNum("max_tvd")!.toLocaleString()} ft</span>
                        </div>
                      )}
                      {mNum("ground_elevation_ft") && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Ground Elevation</span>
                          <span>{mNum("ground_elevation_ft")!.toLocaleString()} ft</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Legal Location */}
                {(m("section") || m("township") || m("range")) && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Legal Location</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm">
                      <span className="font-mono">
                        {[
                          m("quarter_quarter") && `${m("quarter_quarter")}`,
                          m("section") && `Sec ${m("section")}`,
                          m("township") && `T${m("township")}`,
                          m("range") && `R${m("range")}`,
                        ].filter(Boolean).join(", ")}
                      </span>
                    </CardContent>
                  </Card>
                )}

                {/* External Links */}
                {(m("wogcc_link") || m("occ_docs_link")) && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">External Records</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {m("wogcc_link") && (
                        <a href={m("wogcc_link")!} target="_blank" rel="noopener noreferrer"
                          className="block text-sm text-blue-600 hover:underline">
                          View WOGCC Well Record →
                        </a>
                      )}
                      {m("occ_docs_link") && (
                        <a href={m("occ_docs_link")!} target="_blank" rel="noopener noreferrer"
                          className="block text-sm text-blue-600 hover:underline">
                          View OCC Well Documents →
                        </a>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Raw Source Data (collapsed) */}
                {metadataEntries.length > 0 && (
                  <details className="text-sm">
                    <summary className="cursor-pointer text-muted-foreground hover:text-foreground py-2">
                      Raw source data ({metadataEntries.length} fields)
                    </summary>
                    <div className="mt-2 max-h-60 overflow-y-auto space-y-1 border rounded p-2">
                      {metadataEntries.map(([key, value]) => (
                        <div key={key} className="flex justify-between text-xs py-1 border-b border-muted last:border-0">
                          <span className="text-muted-foreground font-mono truncate mr-2">{key}</span>
                          <span className="text-right truncate max-w-[60%]">{String(value)}</span>
                        </div>
                      ))}
                    </div>
                  </details>
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
