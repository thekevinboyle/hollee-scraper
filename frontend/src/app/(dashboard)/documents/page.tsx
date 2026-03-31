"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
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
import { Skeleton } from "@/components/ui/skeleton";

interface DocSummary {
  id: string;
  well_id: string | null;
  state_code: string;
  doc_type: string | null;
  document_date: string | null;
  confidence_score: number | null;
  file_format: string | null;
  source_url: string;
  scraped_at: string | null;
}

interface PaginatedDocs {
  items: DocSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

function confidenceColor(score: number) {
  if (score >= 0.85)
    return "bg-green-500/10 text-green-700 border-green-200";
  if (score >= 0.5)
    return "bg-yellow-500/10 text-yellow-700 border-yellow-200";
  return "bg-red-500/10 text-red-700 border-red-200";
}

const ALL_STATES = ["TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"];
const DOC_TYPES = [
  "well_permit",
  "completion_report",
  "production_report",
  "spacing_order",
  "plugging_report",
  "inspection_record",
  "incident_report",
];
const CONFIDENCE_RANGES = [
  { label: "All", min: "", max: "" },
  { label: "High (≥85%)", min: "0.85", max: "" },
  { label: "Medium (50-84%)", min: "0.50", max: "0.84" },
  { label: "Low (<50%)", min: "", max: "0.49" },
];

export default function DocumentsPage() {
  const [stateFilter, setStateFilter] = useState("");
  const [docType, setDocType] = useState("");
  const [confRange, setConfRange] = useState(0);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("scraped_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const params = new URLSearchParams({
    page: String(page),
    page_size: "25",
    sort_by: sortBy,
    sort_dir: sortDir,
  });
  if (stateFilter) params.set("state", stateFilter);
  if (docType) params.set("doc_type", docType);
  const range = CONFIDENCE_RANGES[confRange];
  if (range.min) params.set("min_confidence", range.min);
  if (range.max) params.set("max_confidence", range.max);

  const { data, isLoading } = useSWR<PaginatedDocs>(
    `/api/v1/documents?${params}`,
    fetcher
  );

  function toggleSort(col: string) {
    if (sortBy === col) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(col);
      setSortDir("desc");
    }
    setPage(1);
  }

  const hasFilters = stateFilter || docType || confRange > 0;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Documents</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={stateFilter}
          onChange={(e) => {
            setStateFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-md border px-3 py-2 text-sm"
        >
          <option value="">All States</option>
          {ALL_STATES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={docType}
          onChange={(e) => {
            setDocType(e.target.value);
            setPage(1);
          }}
          className="rounded-md border px-3 py-2 text-sm"
        >
          <option value="">All Types</option>
          {DOC_TYPES.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select
          value={confRange}
          onChange={(e) => {
            setConfRange(Number(e.target.value));
            setPage(1);
          }}
          className="rounded-md border px-3 py-2 text-sm"
        >
          {CONFIDENCE_RANGES.map((r, i) => (
            <option key={i} value={i}>
              {r.label}
            </option>
          ))}
        </select>
        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setStateFilter("");
              setDocType("");
              setConfRange(0);
              setPage(1);
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
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
                  <TableHead
                    key={col.key}
                    className="cursor-pointer select-none hover:text-foreground"
                    onClick={() => toggleSort(col.key)}
                  >
                    {col.label}
                    {sortBy === col.key && (
                      <span className="ml-1">
                        {sortDir === "asc" ? "↑" : "↓"}
                      </span>
                    )}
                  </TableHead>
                ))}
                <TableHead>Format</TableHead>
                <TableHead>Source</TableHead>
                <TableHead
                  className="cursor-pointer select-none hover:text-foreground"
                  onClick={() => toggleSort("scraped_at")}
                >
                  Scraped
                  {sortBy === "scraped_at" && (
                    <span className="ml-1">
                      {sortDir === "asc" ? "↑" : "↓"}
                    </span>
                  )}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell>
                    <Badge variant="outline">
                      {(doc.doc_type || "unknown").replace(/_/g, " ")}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-bold">{doc.state_code}</TableCell>
                  <TableCell>
                    {doc.confidence_score != null ? (
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${confidenceColor(doc.confidence_score)}`}
                      >
                        {(doc.confidence_score * 100).toFixed(0)}%
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">--</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs">
                    {doc.file_format || "--"}
                  </TableCell>
                  <TableCell className="max-w-[250px] truncate text-xs">
                    {doc.source_url.startsWith("http") ? (
                      <a
                        href={doc.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline"
                        title={doc.source_url}
                      >
                        {new URL(doc.source_url).hostname}
                        {new URL(doc.source_url).pathname.length > 1
                          ? new URL(doc.source_url).pathname.slice(0, 30) + "..."
                          : ""}
                      </a>
                    ) : (
                      <span className="text-muted-foreground">{doc.source_url}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs">
                    {doc.scraped_at
                      ? new Date(doc.scraped_at).toLocaleDateString()
                      : "--"}
                  </TableCell>
                </TableRow>
              ))}
              {data?.items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-center text-muted-foreground py-8"
                  >
                    No documents found
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <div className="flex justify-between items-center mt-4">
            <span className="text-sm text-muted-foreground">
              {data?.total ?? 0} documents
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <span className="flex items-center px-2 text-sm">
                Page {page} of {data?.total_pages ?? 1}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= (data?.total_pages ?? 1)}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
