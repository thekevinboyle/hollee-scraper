"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api, fetcher } from "@/lib/api";
import type { ReviewItem, PaginatedResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";

function confBadge(score: number) {
  const pct = (score * 100).toFixed(0) + "%";
  if (score >= 0.85) return <Badge className="bg-green-500/10 text-green-700 border-green-200">{pct}</Badge>;
  if (score >= 0.5) return <Badge className="bg-yellow-500/10 text-yellow-700 border-yellow-200">{pct}</Badge>;
  return <Badge className="bg-red-500/10 text-red-700 border-red-200">{pct}</Badge>;
}

export default function ReviewPage() {
  const [selected, setSelected] = useState<ReviewItem | null>(null);
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [acting, setActing] = useState(false);

  const { data, isLoading } = useSWR<PaginatedResponse<ReviewItem>>("/api/v1/review?page_size=50", fetcher);

  async function handleAction(action: "approved" | "rejected" | "corrected") {
    if (!selected) return;
    setActing(true);
    try {
      const body: Record<string, unknown> = { status: action };
      if (action === "corrected" && Object.keys(corrections).length > 0) body.corrections = corrections;
      await api.patch(`/review/${selected.id}`, body);
      mutate("/api/v1/review?page_size=50");
      setSelected(null);
      setCorrections({});
    } finally {
      setActing(false);
    }
  }

  if (selected) {
    const fields = selected.extracted_data?.data ?? {};
    const fieldConf = selected.extracted_data?.field_confidence ?? {};
    return (
      <div>
        <Button variant="ghost" onClick={() => { setSelected(null); setCorrections({}); }} className="mb-4">Back to queue</Button>
        <div className="grid grid-cols-2 gap-6">
          <Card>
            <CardHeader><CardTitle className="text-sm">Source Document</CardTitle></CardHeader>
            <CardContent>
              {selected.document?.file_path
                ? <a href={`/api/v1/documents/${selected.document_id}/file`} target="_blank" rel="noreferrer" className="text-sm underline">View PDF</a>
                : <p className="text-sm text-muted-foreground">No file available</p>}
              <p className="text-xs mt-2">Type: {selected.document?.doc_type}</p>
              <p className="text-xs">Reason: {selected.reason}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm">Extracted Fields</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {Object.entries(fields).map(([key, value]) => (
                <div key={key} className="flex items-center gap-2">
                  <label className="text-xs font-medium w-32 shrink-0">{key}</label>
                  {confBadge(fieldConf[key] ?? 0)}
                  <Input value={corrections[key] ?? String(value ?? "")} onChange={(e) => setCorrections({ ...corrections, [key]: e.target.value })} className="text-sm h-8" />
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
        <div className="flex gap-3 mt-6">
          <Button onClick={() => handleAction("approved")} disabled={acting}>Approve</Button>
          <Button variant="secondary" onClick={() => handleAction("corrected")} disabled={acting || Object.keys(corrections).length === 0}>Correct & Approve</Button>
          <Button variant="destructive" onClick={() => handleAction("rejected")} disabled={acting}>Reject</Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Review Queue</h1>
      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Document Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((item) => (
              <TableRow key={item.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setSelected(item)}>
                <TableCell><Badge variant="outline">{item.document?.doc_type?.replace(/_/g, " ") ?? "unknown"}</Badge></TableCell>
                <TableCell>{item.status}</TableCell>
                <TableCell className="max-w-[200px] truncate text-xs">{item.reason}</TableCell>
                <TableCell>{confBadge(item.document?.confidence_score ?? 0)}</TableCell>
                <TableCell className="text-xs">{new Date(item.created_at).toLocaleDateString()}</TableCell>
              </TableRow>
            ))}
            {(!data?.items || data.items.length === 0) && (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-8">No items pending review</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
