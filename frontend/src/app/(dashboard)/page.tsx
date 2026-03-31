"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { DashboardStats } from "@/lib/schemas/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText, MapPin, AlertCircle, BarChart3 } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const PIE_COLORS = [
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#ec4899",
  "#06b6d4",
  "#84cc16",
];

export default function DashboardPage() {
  const { data: stats } = useSWR<DashboardStats>("/api/v1/stats/", fetcher, {
    refreshInterval: 15000,
  });

  const statCards = [
    { title: "Total Wells", icon: MapPin, value: stats?.total_wells ?? "--" },
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

  const wellsByState = stats?.wells_by_state
    ? Object.entries(stats.wells_by_state)
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value)
    : [];

  const docsByType = stats?.documents_by_type
    ? Object.entries(stats.documents_by_type)
        .map(([name, value]) => ({
          name: name.replace(/_/g, " "),
          value,
        }))
        .sort((a, b) => b.value - a.value)
    : [];

  const wellsByStatus = stats?.wells_by_status
    ? Object.entries(stats.wells_by_status)
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value)
    : [];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {/* Stat Cards */}
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

      {/* Charts Row */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 mb-8">
        {/* Wells by State Bar Chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              Wells by State
            </CardTitle>
          </CardHeader>
          <CardContent>
            {wellsByState.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={wellsByState}>
                  <XAxis dataKey="name" fontSize={12} />
                  <YAxis fontSize={12} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground py-8 text-center">
                No data yet
              </p>
            )}
          </CardContent>
        </Card>

        {/* Documents by Type Pie Chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              Documents by Type
            </CardTitle>
          </CardHeader>
          <CardContent>
            {docsByType.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={docsByType}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={80}
                    dataKey="value"
                    label={({ name, value }) => `${name} (${value})`}
                    labelLine={false}
                    fontSize={10}
                  >
                    {docsByType.map((_, index) => (
                      <Cell
                        key={index}
                        fill={PIE_COLORS[index % PIE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground py-8 text-center">
                No data yet
              </p>
            )}
          </CardContent>
        </Card>

        {/* Wells by Status */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              Wells by Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            {wellsByStatus.length > 0 ? (
              <div className="space-y-3">
                {wellsByStatus.map((item) => (
                  <div key={item.name} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="capitalize">{item.name}</span>
                      <span className="font-medium">{item.value}</span>
                    </div>
                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full"
                        style={{
                          width: `${(item.value / (stats?.total_wells || 1)) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground py-8 text-center">
                No data yet
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Scrape Jobs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            Recent Scrape Jobs
          </CardTitle>
        </CardHeader>
        <CardContent>
          {stats?.recent_scrape_jobs && stats.recent_scrape_jobs.length > 0 ? (
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
            <p className="text-sm text-muted-foreground">No scrape jobs yet</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
