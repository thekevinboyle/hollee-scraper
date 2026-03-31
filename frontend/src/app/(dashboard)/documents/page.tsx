"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { DocumentSummary } from "@/lib/schemas/api";
import { STATE_CODES, DOC_TYPES, CONFIDENCE_RANGES } from "@/lib/constants";
import { API_BASE_URL } from "@/lib/env";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";

interface PaginatedDocs {
  items: DocumentSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface DocDetail {
  id: string;
  well_id: string | null;
  well_api_number: string | null;
  state_code: string;
  doc_type: string | null;
  status: string | null;
  source_url: string;
  confidence_score: number | null;
  file_format: string | null;
  scraped_at: string | null;
  extracted_data: Array<{
    id: string;
    data_type: string;
    data: Record<string, unknown>;
    field_confidence: Record<string, number>;
    confidence_score: number | null;
  }>;
}

function confidenceColor(score: number) {
  if (score >= 0.85) return "bg-green-500/10 text-green-700 border-green-200";
  if (score >= 0.5) return "bg-yellow-500/10 text-yellow-700 border-yellow-200";
  return "bg-red-500/10 text-red-700 border-red-200";
}

// Important fields to show first, in order
const PRIORITY_FIELDS = [
  "api_number", "operator_name", "well_name", "state", "county",
  "field_name", "well_status", "well_type", "total_depth_ft",
  "cumulative_oil_bbl", "cumulative_gas_mcf", "cumulative_water_bbl",
  "bottom_formation", "max_md", "max_tvd", "ground_elevation_ft",
  "latitude", "longitude", "spud_date",
];

function formatFieldName(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace("Bbl", "BBL")
    .replace("Mcf", "MCF")
    .replace("Ft", "ft")
    .replace("Tvd", "TVD")
    .replace("Api", "API")
    .replace("Md", "MD");
}

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "--";
  if (typeof value === "number") {
    if (key.includes("latitude") || key.includes("longitude")) return value.toFixed(6);
    if (key.includes("bbl") || key.includes("mcf") || key.includes("depth") || key.includes("elevation") || key.includes("md") || key.includes("tvd"))
      return value.toLocaleString();
    return String(value);
  }
  return String(value);
}

export default function DocumentsPage() {
  const [stateFilter, setStateFilter] = useState("");
  const [docType, setDocType] = useState("");
  const [confRange, setConfRange] = useState(0);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("scraped_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

  const params = new URLSearchParams({
    page: String(page), page_size: "25", sort_by: sortBy, sort_dir: sortDir,
  });
  if (stateFilter) params.set("state", stateFilter);
  if (docType) params.set("doc_type", docType);
  const range = CONFIDENCE_RANGES[confRange];
  if (range.min != null) params.set("min_confidence", String(range.min));
  if (range.max != null) params.set("max_confidence", String(range.max));

  const { data, isLoading } = useSWR<PaginatedDocs>(`/api/v1/documents?${params}`, fetcher);

  const { data: docDetail } = useSWR<DocDetail>(
    selectedDocId ? `/api/v1/documents/${selectedDocId}` : null,
    (url: string) => fetch(`${API_BASE_URL}${url}`).then(r => r.json())
  );

  function toggleSort(col: string) {
    if (sortBy === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortBy(col); setSortDir("desc"); }
    setPage(1);
  }

  const hasFilters = stateFilter || docType || confRange > 0;

  // Organize extracted data fields
  const extractedData = docDetail?.extracted_data?.[0]?.data || {};
  const fieldConfidence = docDetail?.extracted_data?.[0]?.field_confidence || {};
  const allFields = Object.entries(extractedData).filter(([, v]) => v != null && v !== "");
  const priorityFields = PRIORITY_FIELDS
    .filter((k) => extractedData[k] != null && extractedData[k] !== "")
    .map((k) => [k, extractedData[k]] as [string, unknown]);
  const otherFields = allFields.filter(([k]) => !PRIORITY_FIELDS.includes(k));

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Documents</h1>

      <div className="flex flex-wrap gap-3 mb-4">
        <select value={stateFilter} onChange={(e) => { setStateFilter(e.target.value); setPage(1); }} className="rounded-md border px-3 py-2 text-sm">
          <option value="">All States</option>
          {STATE_CODES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={docType} onChange={(e) => { setDocType(e.target.value); setPage(1); }} className="rounded-md border px-3 py-2 text-sm">
          <option value="">All Types</option>
          {DOC_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
        </select>
        <select value={confRange} onChange={(e) => { setConfRange(Number(e.target.value)); setPage(1); }} className="rounded-md border px-3 py-2 text-sm">
          {CONFIDENCE_RANGES.map((r, i) => <option key={i} value={i}>{r.label}</option>)}
        </select>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={() => { setStateFilter(""); setDocType(""); setConfRange(0); setPage(1); }}>
            Clear filters
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                {[
                  { key: "doc_type", label: "Type" },
                  { key: "state_code", label: "State" },
                  { key: "confidence_score", label: "Confidence" },
                ].map((col) => (
                  <TableHead key={col.key} className="cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort(col.key)}>
                    {col.label}{sortBy === col.key && <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>}
                  </TableHead>
                ))}
                <TableHead>Format</TableHead>
                <TableHead className="cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort("scraped_at")}>
                  Scraped{sortBy === "scraped_at" && <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.map((doc) => (
                <TableRow key={doc.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setSelectedDocId(doc.id)}>
                  <TableCell><Badge variant="outline">{(doc.doc_type || "unknown").replace(/_/g, " ")}</Badge></TableCell>
                  <TableCell className="font-bold">{doc.state_code}</TableCell>
                  <TableCell>
                    {doc.confidence_score != null ? (
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${confidenceColor(doc.confidence_score)}`}>
                        {(doc.confidence_score * 100).toFixed(0)}%
                      </span>
                    ) : <span className="text-muted-foreground text-xs">--</span>}
                  </TableCell>
                  <TableCell className="text-xs">{doc.file_format || "--"}</TableCell>
                  <TableCell className="text-xs">{doc.scraped_at ? new Date(doc.scraped_at).toLocaleDateString() : "--"}</TableCell>
                </TableRow>
              ))}
              {data?.items.length === 0 && (
                <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-8">No documents found</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
          <div className="flex justify-between items-center mt-4">
            <span className="text-sm text-muted-foreground">{data?.total ?? 0} documents</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span className="flex items-center px-2 text-sm">Page {page} of {data?.total_pages ?? 1}</span>
              <Button variant="outline" size="sm" disabled={page >= (data?.total_pages ?? 1)} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        </>
      )}

      {/* Document Detail Side Panel */}
      <Sheet open={!!selectedDocId} onOpenChange={() => setSelectedDocId(null)}>
        <SheetContent className="w-[440px] sm:w-[580px] overflow-y-auto">
          {docDetail ? (
            <>
              <SheetHeader>
                <SheetTitle>
                  <Badge variant="outline" className="mr-2">{(docDetail.doc_type || "unknown").replace(/_/g, " ")}</Badge>
                  {docDetail.well_api_number || docDetail.state_code}
                </SheetTitle>
              </SheetHeader>

              <div className="mt-6 space-y-4">
                {/* Document Info */}
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">Document Info</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {docDetail.well_api_number && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Well API</span>
                        <span className="font-mono">{docDetail.well_api_number}</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">State</span>
                      <span className="font-bold">{docDetail.state_code}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Status</span>
                      <span>{docDetail.status || "--"}</span>
                    </div>
                    {docDetail.confidence_score != null && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Confidence</span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium border ${confidenceColor(docDetail.confidence_score)}`}>
                          {(docDetail.confidence_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Extracted Data — Priority Fields */}
                {priorityFields.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-sm">Extracted Data</CardTitle></CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      {priorityFields.map(([key, value]) => (
                        <div key={key} className="flex justify-between items-center">
                          <span className="text-muted-foreground">{formatFieldName(key)}</span>
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{formatValue(key, value)}</span>
                            {fieldConfidence[key] != null && (
                              <span className="text-[10px] text-muted-foreground">{(fieldConfidence[key] * 100).toFixed(0)}%</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {/* Other extracted fields */}
                {otherFields.length > 0 && (
                  <details className="text-sm">
                    <summary className="cursor-pointer text-muted-foreground hover:text-foreground py-2">
                      Additional fields ({otherFields.length})
                    </summary>
                    <Card className="mt-2">
                      <CardContent className="pt-4 space-y-1">
                        {otherFields.map(([key, value]) => (
                          <div key={key} className="flex justify-between text-xs py-1 border-b border-muted last:border-0">
                            <span className="text-muted-foreground">{formatFieldName(key)}</span>
                            <span className="text-right truncate max-w-[55%]">{formatValue(key, value)}</span>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  </details>
                )}

                {/* Source Record Link */}
                {docDetail.source_url && (
                  <Card className="border-blue-200 bg-blue-50/30">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Source Record</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <a
                        href={docDetail.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
                      >
                        View Original Record →
                      </a>
                      <p className="text-xs text-muted-foreground">
                        {docDetail.source_url.includes("pipeline.wyo.gov") && "Opens the WOGCC well record page — includes completion reports, production history, and well logs."}
                        {docDetail.source_url.includes("occ.ok.gov") && "Opens the OCC Well Records portal — search results for permits, completions, and well files (PDFs)."}
                        {docDetail.source_url.includes("ecmc.state.co.us") && "Opens the COGCC facility detail page — includes drilling permits, completion reports, and production data."}
                        {docDetail.source_url.includes("conservation.ca.gov") && "Opens CalGEM WellSTAR — search for well records, permits, and production data."}
                      </p>
                      <p className="text-[10px] text-muted-foreground truncate" title={docDetail.source_url}>
                        {docDetail.source_url}
                      </p>
                    </CardContent>
                  </Card>
                )}
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
