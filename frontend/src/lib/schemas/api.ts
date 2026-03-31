import { z } from "zod";

// ============================================================
// Pagination
// ============================================================

export function paginatedSchema<T extends z.ZodTypeAny>(itemSchema: T) {
  return z.object({
    items: z.array(itemSchema),
    total: z.number(),
    page: z.number(),
    page_size: z.number(),
    total_pages: z.number(),
  });
}

// ============================================================
// Wells
// ============================================================

export const wellSummarySchema = z.object({
  id: z.string().uuid(),
  api_number: z.string(),
  well_name: z.string().nullable().default(""),
  operator_name: z.string().nullable().default(null),
  state_code: z.string(),
  county: z.string().nullable().default(null),
  well_status: z.string().default("unknown"),
  well_type: z.string().nullable().default(null),
  latitude: z.number().nullable().default(null),
  longitude: z.number().nullable().default(null),
  document_count: z.number().default(0),
});

export const wellDetailSchema = wellSummarySchema.extend({
  api_10: z.string().nullable().default(null),
  well_number: z.string().nullable().default(null),
  basin: z.string().nullable().default(null),
  field_name: z.string().nullable().default(null),
  lease_name: z.string().nullable().default(null),
  spud_date: z.string().nullable().default(null),
  completion_date: z.string().nullable().default(null),
  total_depth: z.number().nullable().default(null),
  true_vertical_depth: z.number().nullable().default(null),
  lateral_length: z.number().nullable().default(null),
  metadata: z.record(z.string(), z.unknown()).default({}),
  alternate_ids: z.record(z.string(), z.string()).default({}),
  documents: z
    .array(
      z.object({
        id: z.string().uuid(),
        doc_type: z.string().nullable(),
        status: z.string(),
        confidence_score: z.number().nullable(),
        source_url: z.string(),
      })
    )
    .default([]),
  created_at: z.string().nullable().default(null),
  updated_at: z.string().nullable().default(null),
});

export type WellSummary = z.infer<typeof wellSummarySchema>;
export type WellDetail = z.infer<typeof wellDetailSchema>;

// ============================================================
// Documents
// ============================================================

export const documentSummarySchema = z.object({
  id: z.string().uuid(),
  well_id: z.string().uuid().nullable().default(null),
  state_code: z.string(),
  doc_type: z.string().nullable().default(null),
  document_date: z.string().nullable().default(null),
  confidence_score: z.number().nullable().default(null),
  file_format: z.string().nullable().default(null),
  source_url: z.string(),
  scraped_at: z.string().nullable().default(null),
});

export type DocumentSummary = z.infer<typeof documentSummarySchema>;

// ============================================================
// Scrape Jobs
// ============================================================

export const scrapeJobSchema = z.object({
  id: z.string().uuid(),
  state_code: z.string().nullable(),
  status: z.string(),
  job_type: z.string(),
  documents_found: z.number().default(0),
  documents_downloaded: z.number().default(0),
  documents_processed: z.number().default(0),
  documents_failed: z.number().default(0),
  started_at: z.string().nullable().default(null),
  finished_at: z.string().nullable().default(null),
  created_at: z.string(),
  errors: z.array(z.unknown()).default([]),
  total_documents: z.number().default(0),
});

export type ScrapeJob = z.infer<typeof scrapeJobSchema>;

// ============================================================
// Map
// ============================================================

export const wellMapPointSchema = z.object({
  id: z.string().uuid(),
  api_number: z.string(),
  well_name: z.string().nullable().default(null),
  operator_name: z.string().nullable().default(null),
  latitude: z.number(),
  longitude: z.number(),
  well_status: z.string().nullable().default(null),
  well_type: z.string().nullable().default(null),
});

export type WellMapPoint = z.infer<typeof wellMapPointSchema>;

// ============================================================
// Dashboard Stats
// ============================================================

export const dashboardStatsSchema = z.object({
  total_wells: z.number(),
  total_documents: z.number(),
  total_extracted: z.number(),
  review_queue_pending: z.number(),
  avg_confidence: z.number().nullable(),
  documents_by_state: z.record(z.string(), z.number()),
  documents_by_type: z.record(z.string(), z.number()),
  wells_by_state: z.record(z.string(), z.number()),
  wells_by_status: z.record(z.string(), z.number()),
  recent_scrape_jobs: z.array(
    z.object({
      id: z.string(),
      state_code: z.string().nullable(),
      status: z.string(),
      documents_found: z.number(),
      documents_processed: z.number(),
      created_at: z.string(),
    })
  ),
});

export type DashboardStats = z.infer<typeof dashboardStatsSchema>;

// ============================================================
// Review
// ============================================================

export const reviewItemSchema = z.object({
  id: z.string().uuid(),
  document_id: z.string().uuid(),
  extracted_data_id: z.string().uuid().nullable().default(null),
  status: z.string(),
  reason: z.string().nullable().default(null),
  document_confidence: z.number().nullable().default(null),
  well_api_number: z.string().nullable().default(null),
  state_code: z.string().nullable().default(null),
  doc_type: z.string().nullable().default(null),
  well_name: z.string().nullable().default(null),
  operator_name: z.string().nullable().default(null),
  created_at: z.string().nullable().default(null),
});

export type ReviewItem = z.infer<typeof reviewItemSchema>;
