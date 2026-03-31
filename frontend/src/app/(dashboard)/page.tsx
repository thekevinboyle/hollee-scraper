"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText, MapPin, AlertCircle, BarChart3 } from "lucide-react";

interface DashboardStats {
  total_wells: number;
  total_documents: number;
  total_extracted: number;
  review_queue_pending: number;
  avg_confidence: number | null;
  documents_by_state: Record<string, number>;
  documents_by_type: Record<string, number>;
  wells_by_state: Record<string, number>;
  wells_by_status: Record<string, number>;
  recent_scrape_jobs: Array<{
    id: string;
    state_code: string;
    status: string;
    documents_found: number;
    documents_processed: number;
    created_at: string;
  }>;
}

export default function DashboardPage() {
  const { data: stats } = useSWR<DashboardStats>("/api/v1/stats/", fetcher, {
    refreshInterval: 15000,
  });

  const statCards = [
    {
      title: "Total Wells",
      icon: MapPin,
      value: stats?.total_wells ?? "--",
    },
    {
      title: "Total Documents",
      icon: FileText,
      value: stats?.total_documents ?? "--",
    },
    {
      title: "Pending Review",
      icon: AlertCircle,
      value: stats?.review_queue_pending ?? "--",
    },
    {
      title: "Avg Confidence",
      icon: BarChart3,
      value:
        stats?.avg_confidence != null
          ? `${(stats.avg_confidence * 100).toFixed(0)}%`
          : "--",
    },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
        {statCards.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {stat.title}
              </CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Wells by State */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Wells by State</CardTitle>
          </CardHeader>
          <CardContent>
            {stats?.wells_by_state &&
            Object.keys(stats.wells_by_state).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(stats.wells_by_state)
                  .sort(([, a], [, b]) => b - a)
                  .map(([state, count]) => (
                    <div
                      key={state}
                      className="flex justify-between items-center"
                    >
                      <span className="font-mono text-sm font-bold">
                        {state}
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {count.toLocaleString()} wells
                      </span>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No data yet — run a scrape to populate
              </p>
            )}
          </CardContent>
        </Card>

        {/* Documents by Type */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              Documents by Type
            </CardTitle>
          </CardHeader>
          <CardContent>
            {stats?.documents_by_type &&
            Object.keys(stats.documents_by_type).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(stats.documents_by_type)
                  .sort(([, a], [, b]) => b - a)
                  .map(([type, count]) => (
                    <div
                      key={type}
                      className="flex justify-between items-center"
                    >
                      <Badge variant="outline">
                        {type.replace(/_/g, " ")}
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        {count}
                      </span>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No documents yet
              </p>
            )}
          </CardContent>
        </Card>

        {/* Recent Scrape Jobs */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              Recent Scrape Jobs
            </CardTitle>
          </CardHeader>
          <CardContent>
            {stats?.recent_scrape_jobs &&
            stats.recent_scrape_jobs.length > 0 ? (
              <div className="space-y-2">
                {stats.recent_scrape_jobs.map((job) => (
                  <div
                    key={job.id}
                    className="flex justify-between items-center text-sm"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold">
                        {job.state_code}
                      </span>
                      <Badge
                        variant={
                          job.status === "completed"
                            ? "default"
                            : job.status === "failed"
                              ? "destructive"
                              : "secondary"
                        }
                      >
                        {job.status}
                      </Badge>
                    </div>
                    <span className="text-muted-foreground">
                      {job.documents_found} found &middot;{" "}
                      {new Date(job.created_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No scrape jobs yet
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
