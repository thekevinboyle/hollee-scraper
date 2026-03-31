export interface Well {
  id: string;
  api_number: string;
  well_name: string;
  operator_name: string;
  state_code: string;
  county: string;
  latitude: number;
  longitude: number;
  status: WellStatus;
  doc_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type WellStatus =
  | "active"
  | "inactive"
  | "plugged"
  | "permitted"
  | "drilling"
  | "completed"
  | "shut_in"
  | "temporarily_abandoned"
  | "unknown";

export interface Document {
  id: string;
  well_id: string;
  doc_type: DocumentType;
  status: DocumentStatus;
  file_path: string;
  file_hash: string;
  confidence_score: number;
  ocr_confidence: number | null;
  source_url: string;
  scraped_at: string;
  created_at: string;
}

export type DocumentType =
  | "well_permit"
  | "completion_report"
  | "production_report"
  | "spacing_order"
  | "pooling_order"
  | "plugging_report"
  | "inspection_record"
  | "incident_report"
  | "unknown"
  | "other";

export type DocumentStatus =
  | "discovered"
  | "downloading"
  | "downloaded"
  | "classifying"
  | "classified"
  | "extracting"
  | "extracted"
  | "normalized"
  | "stored"
  | "flagged_for_review"
  | "download_failed"
  | "classification_failed"
  | "extraction_failed";

export interface ExtractedData {
  id: string;
  document_id: string;
  data: Record<string, unknown>;
  field_confidence: Record<string, number>;
  data_type: string;
  extractor_used: string;
}

export interface ReviewItem {
  id: string;
  document_id: string;
  document: Document;
  extracted_data: ExtractedData;
  status: ReviewStatus;
  reason: string;
  corrections: Record<string, unknown> | null;
  created_at: string;
}

export type ReviewStatus = "pending" | "approved" | "rejected" | "corrected";

export interface ScrapeJob {
  id: string;
  state_code: string;
  status: ScrapeJobStatus;
  docs_found: number;
  docs_downloaded: number;
  docs_processed: number;
  current_step: string;
  errors: Array<{ message: string; timestamp: string }>;
  progress_pct: number;
  started_at: string;
  completed_at: string | null;
}

export type ScrapeJobStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DashboardStats {
  total_wells: number;
  total_documents: number;
  total_extracted: number;
  pending_review: number;
  avg_confidence: number;
  by_state: Record<string, { wells: number; documents: number }>;
  by_type: Record<string, number>;
}

export interface Operator {
  id: string;
  name: string;
  well_count: number;
  state_codes: string[];
}

export interface StateSummary {
  code: string;
  name: string;
  tier: number;
  well_count: number;
  document_count: number;
}
