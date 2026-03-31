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

export default function DocumentsPage() {
  const [state, setState] = useState("");
  const [docType, setDocType] = useState("");
  const [page, setPage] = useState(1);

  const params = new URLSearchParams({
    page: String(page),
    page_size: "25",
  });
  if (state) params.set("state", state);
  if (docType) params.set("doc_type", docType);

  const { data, isLoading } = useSWR<PaginatedDocs>(
    `/api/v1/documents?${params}`,
    fetcher
  );

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Documents</h1>
      <div className="flex gap-4 mb-4">
        <select
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            setPage(1);
          }}
          className="rounded-md border px-3 py-2 text-sm"
        >
          <option value="">All States</option>
          {["TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"].map(
            (s) => (
              <option key={s} value={s}>
                {s}
              </option>
            )
          )}
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
          {[
            "well_permit",
            "completion_report",
            "production_report",
            "spacing_order",
            "plugging_report",
            "inspection_record",
            "incident_report",
          ].map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ")}
            </option>
          ))}
        </select>
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
                <TableHead>Type</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Format</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Scraped</TableHead>
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
                  <TableCell className="max-w-[200px] truncate text-xs">
                    {doc.source_url}
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
