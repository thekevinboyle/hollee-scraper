"use client";

import { useState } from "react";
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
  well_name: string;
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
  metadata: Record<string, unknown>;
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
  status: string
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "active":
      return "default";
    case "plugged":
      return "destructive";
    case "drilling":
    case "completed":
      return "secondary";
    default:
      return "outline";
  }
}

export default function WellsPage() {
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
  const [page, setPage] = useState(1);
  const [selectedApi, setSelectedApi] = useState<string | null>(null);
  const debouncedSearch = useDebounce(search);

  const params = new URLSearchParams({
    page: String(page),
    page_size: "25",
  });
  if (debouncedSearch) params.set("q", debouncedSearch);
  if (state) params.set("state", state);

  const { data, isLoading } = useSWR<PaginatedWells>(
    `/api/v1/wells?${params}`,
    fetcher
  );

  // Fetch well detail when side panel is open
  const { data: wellDetail } = useSWR<WellDetail>(
    selectedApi ? `/api/v1/wells/${selectedApi}` : null,
    fetcher
  );

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Wells</h1>
      <div className="flex gap-4 mb-4">
        <Input
          placeholder="Search wells..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="max-w-sm"
        />
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
                <TableHead>API Number</TableHead>
                <TableHead>Well Name</TableHead>
                <TableHead>Operator</TableHead>
                <TableHead>State</TableHead>
                <TableHead>County</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Docs</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.map((well) => (
                <TableRow
                  key={well.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => setSelectedApi(well.api_number)}
                >
                  <TableCell className="font-mono text-sm">
                    {well.api_number}
                  </TableCell>
                  <TableCell>{well.well_name || "--"}</TableCell>
                  <TableCell>{well.operator_name || "--"}</TableCell>
                  <TableCell className="font-bold">
                    {well.state_code}
                  </TableCell>
                  <TableCell>{well.county || "--"}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(well.well_status)}>
                      {well.well_status}
                    </Badge>
                  </TableCell>
                  <TableCell>{well.document_count}</TableCell>
                </TableRow>
              ))}
              {data?.items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="text-center text-muted-foreground py-8"
                  >
                    No wells found
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <div className="flex justify-between items-center mt-4">
            <span className="text-sm text-muted-foreground">
              {data?.total ?? 0} wells total
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

      <Sheet open={!!selectedApi} onOpenChange={() => setSelectedApi(null)}>
        <SheetContent className="w-[400px] sm:w-[540px] overflow-y-auto">
          {wellDetail ? (
            <>
              <SheetHeader>
                <SheetTitle>
                  {wellDetail.well_name || wellDetail.api_number}
                </SheetTitle>
              </SheetHeader>

              <div className="mt-6 space-y-4">
                {/* Well Info */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Well Information</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">API Number</span>
                      <span className="font-mono">
                        {wellDetail.api_number}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Operator</span>
                      <span>{wellDetail.operator_name || "--"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">State</span>
                      <span className="font-bold">
                        {wellDetail.state_code}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">County</span>
                      <span>{wellDetail.county || "--"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Status</span>
                      <Badge variant={statusVariant(wellDetail.well_status)}>
                        {wellDetail.well_status}
                      </Badge>
                    </div>
                    {wellDetail.latitude && wellDetail.longitude && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Location</span>
                        <span className="font-mono text-xs">
                          {wellDetail.latitude.toFixed(6)},{" "}
                          {wellDetail.longitude.toFixed(6)}
                        </span>
                      </div>
                    )}
                    {wellDetail.total_depth && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">
                          Total Depth
                        </span>
                        <span>
                          {wellDetail.total_depth.toLocaleString()} ft
                        </span>
                      </div>
                    )}
                    {wellDetail.spud_date && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Spud Date</span>
                        <span>{wellDetail.spud_date}</span>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Documents */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">
                      Documents ({wellDetail.documents?.length ?? 0})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {wellDetail.documents && wellDetail.documents.length > 0 ? (
                      <div className="space-y-2">
                        {wellDetail.documents.map((doc) => (
                          <div
                            key={doc.id}
                            className="flex items-center justify-between p-2 rounded border text-sm"
                          >
                            <div>
                              <Badge variant="outline" className="text-xs">
                                {(doc.doc_type || "unknown").replace(/_/g, " ")}
                              </Badge>
                              <span className="ml-2 text-xs text-muted-foreground">
                                {doc.status}
                              </span>
                            </div>
                            {doc.confidence_score != null && (
                              <span className="text-xs font-medium">
                                {(doc.confidence_score * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No documents linked
                      </p>
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
