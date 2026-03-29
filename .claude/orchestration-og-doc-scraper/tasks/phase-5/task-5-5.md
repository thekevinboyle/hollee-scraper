# Task 5.5: Review Queue & Document Viewer

## Objective

Implement the review queue page with a prioritized list of documents needing human verification, a side-by-side review interface (original PDF on the left via react-pdf, editable extracted fields on the right with confidence color-coding), and approve/correct/reject action buttons that update the backend. This is the core data quality interface per DISCOVERY D10 and D15.

## Context

Documents with confidence scores below the auto-accept threshold (0.85) are routed to the review queue (DISCOVERY D10, D23). The review queue is the primary quality control mechanism -- users compare the original PDF against extracted data and either approve, correct, or reject. Corrections are tracked in the `data_corrections` table for audit. This task builds the frontend interface for that workflow, consuming review endpoints from Task 3.3. It also introduces react-pdf for inline document viewing, which requires dynamic import with `ssr: false` (same as Leaflet).

## Dependencies

- Task 5.1 - Frontend foundation (layout, API client, types)
- Task 3.3 - Review queue API endpoints (`GET /api/v1/review`, `GET /api/v1/review/{id}`, `PATCH /api/v1/review/{id}`)

## Blocked By

- 5.1, 3.3

## Research Findings

Key findings from research files relevant to this task:

- From `confidence-scoring` skill: Three-tier confidence scoring -- OCR (Tier 1), field-level (Tier 2), document-level (Tier 3). Auto-accept >= 0.85, review queue 0.50-0.84, reject < 0.50. Critical fields (API number, production values) below their reject threshold force entire document to review regardless of overall score.
- From `confidence-scoring` skill: Field-level thresholds are stricter for critical fields -- API number auto-accept >= 0.95, operator >= 0.90, production values >= 0.90, coordinates >= 0.95.
- From `confidence-scoring` skill: Review queue sorted by highest confidence first (easiest/quickest to review). User actions: Approve (accept as-is), Correct (edit values), Reject (discard data but keep file).
- From `nextjs-dashboard` skill: react-pdf requires dynamic import with `ssr: false` and explicit PDF.js worker configuration using the `URL` constructor pattern. Must import annotation and text layer CSS.
- From `dashboard-map-implementation.md` Section 4: Side-by-side layout -- left panel for PDF viewer with zoom/scroll, right panel for extracted fields with inline editing. Low-confidence fields highlighted in yellow, edited fields in blue.
- From `dashboard-map-implementation.md` Section 3.3: PDF served from FastAPI via `GET /api/v1/documents/{id}/file`.
- From `og-scraper-architecture` skill: Review endpoint `PATCH /api/v1/review/{id}` accepts `{ action: "approve" | "reject" | "correct", corrections?: Record<string, unknown> }`.

## Implementation Plan

### Step 1: Create Document Viewer Component

Build a react-pdf based PDF viewer with page navigation, zoom controls, and loading state. This must be a client component with dynamic import.

```typescript
// frontend/src/components/review/document-viewer.tsx
'use client';

import { useState, useCallback } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, RotateCw } from 'lucide-react';

// Configure PDF.js worker -- MUST be done before rendering any Document
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

interface DocumentViewerProps {
  fileUrl: string; // e.g., "/api/v1/documents/{id}/file"
}

export function DocumentViewer({ fileUrl }: DocumentViewerProps) {
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1.0);

  const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    setPageNumber(1);
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Controls bar */}
      <div className="flex items-center justify-between p-2 border-b bg-muted/50">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setPageNumber(p => Math.max(1, p - 1))}
            disabled={pageNumber <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm min-w-[80px] text-center">
            Page {pageNumber} of {numPages}
          </span>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setPageNumber(p => Math.min(numPages, p + 1))}
            disabled={pageNumber >= numPages}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setScale(s => Math.max(0.5, s - 0.25))}
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="text-sm min-w-[50px] text-center">
            {Math.round(scale * 100)}%
          </span>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setScale(s => Math.min(2.0, s + 0.25))}
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* PDF renderer */}
      <div className="flex-1 overflow-auto p-4 flex justify-center">
        <Document
          file={fileUrl}
          onLoadSuccess={onDocumentLoadSuccess}
          loading={<Skeleton className="w-[600px] h-[800px]" />}
          error={
            <div className="text-center text-red-500 py-8">
              Failed to load document. The file may be missing or corrupted.
            </div>
          }
        >
          <Page
            pageNumber={pageNumber}
            scale={scale}
            loading={<Skeleton className="w-[600px] h-[800px]" />}
          />
        </Document>
      </div>
    </div>
  );
}
```

Create a dynamic import wrapper since react-pdf requires browser APIs:

```typescript
// frontend/src/components/review/document-viewer-dynamic.tsx
import dynamic from 'next/dynamic';
import { Skeleton } from '@/components/ui/skeleton';

export const DocumentViewerDynamic = dynamic(
  () => import('./document-viewer').then(mod => ({ default: mod.DocumentViewer })),
  {
    ssr: false,
    loading: () => <Skeleton className="h-full w-full" />,
  },
);
```

### Step 2: Create Extracted Fields Form

An editable form showing all extracted fields from a document. Each field displays its confidence score with color-coding (green >= 0.85, yellow 0.50-0.84, red < 0.50). Fields are editable for corrections.

```typescript
// frontend/src/components/review/extracted-fields-form.tsx
'use client';

import { useState, useCallback } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { ExtractedData } from '@/lib/types';

interface ExtractedFieldsFormProps {
  extractedData: ExtractedData;
  onFieldChange: (fieldPath: string, newValue: string) => void;
  editedFields: Record<string, string>;
}

// Confidence thresholds from the confidence-scoring skill
const CONFIDENCE_AUTO_ACCEPT = 0.85;
const CONFIDENCE_REVIEW = 0.50;

function confidenceColor(score: number): string {
  if (score >= CONFIDENCE_AUTO_ACCEPT) return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
  if (score >= CONFIDENCE_REVIEW) return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
  return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
}

function confidenceBadgeVariant(score: number): 'default' | 'secondary' | 'destructive' {
  if (score >= CONFIDENCE_AUTO_ACCEPT) return 'default';
  if (score >= CONFIDENCE_REVIEW) return 'secondary';
  return 'destructive';
}

// Human-readable field names
const FIELD_LABELS: Record<string, string> = {
  api_number: 'API Number',
  operator_name: 'Operator',
  well_name: 'Well Name',
  reporting_period: 'Reporting Period',
  oil_bbls: 'Oil (BBL)',
  gas_mcf: 'Gas (MCF)',
  water_bbls: 'Water (BBL)',
  days_produced: 'Days Produced',
  well_status: 'Well Status',
  county: 'County',
  state: 'State',
  permit_number: 'Permit Number',
  document_type: 'Document Type',
  completion_date: 'Completion Date',
  spud_date: 'Spud Date',
  total_depth: 'Total Depth',
  latitude: 'Latitude',
  longitude: 'Longitude',
};

export function ExtractedFieldsForm({
  extractedData,
  onFieldChange,
  editedFields,
}: ExtractedFieldsFormProps) {
  const data = extractedData.data as Record<string, string>;
  const confidences = extractedData.field_confidence;

  // Sort fields: low confidence first (most need review)
  const sortedFields = Object.entries(data).sort(([a], [b]) => {
    const confA = confidences[a] ?? 1;
    const confB = confidences[b] ?? 1;
    return confA - confB;
  });

  return (
    <TooltipProvider>
      <div className="space-y-3">
        {sortedFields.map(([fieldKey, fieldValue]) => {
          const confidence = confidences[fieldKey] ?? 1;
          const isEdited = fieldKey in editedFields;
          const displayValue = isEdited ? editedFields[fieldKey] : String(fieldValue ?? '');
          const label = FIELD_LABELS[fieldKey] || fieldKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

          return (
            <div
              key={fieldKey}
              className={`flex items-center gap-3 p-2 rounded-md ${
                isEdited
                  ? 'bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800'
                  : confidence < CONFIDENCE_REVIEW
                    ? 'bg-red-50 dark:bg-red-950'
                    : confidence < CONFIDENCE_AUTO_ACCEPT
                      ? 'bg-yellow-50 dark:bg-yellow-950'
                      : ''
              }`}
            >
              <Label className="w-36 text-sm shrink-0">{label}</Label>
              <Input
                value={displayValue}
                onChange={(e) => onFieldChange(fieldKey, e.target.value)}
                className={`flex-1 ${isEdited ? 'border-blue-400' : ''}`}
              />
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge
                    variant={confidenceBadgeVariant(confidence)}
                    className="shrink-0 cursor-help"
                  >
                    {(confidence * 100).toFixed(0)}%
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Confidence: {(confidence * 100).toFixed(1)}%</p>
                  <p>Method: {extractedData.extractor_used}</p>
                </TooltipContent>
              </Tooltip>
            </div>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
```

### Step 3: Create Review Actions Component

Approve, Correct, and Reject buttons with confirmation dialogs for destructive actions (reject).

```typescript
// frontend/src/components/review/review-actions.tsx
'use client';

import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import { CheckCircle, XCircle, Save, Loader2 } from 'lucide-react';
import { useState } from 'react';

interface ReviewActionsProps {
  hasEdits: boolean;
  isSubmitting: boolean;
  onApprove: () => void;
  onCorrect: () => void;
  onReject: () => void;
}

export function ReviewActions({
  hasEdits,
  isSubmitting,
  onApprove,
  onCorrect,
  onReject,
}: ReviewActionsProps) {
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);

  return (
    <div className="flex items-center gap-2 p-4 border-t bg-muted/50">
      {hasEdits ? (
        <Button
          onClick={onCorrect}
          disabled={isSubmitting}
          className="flex-1"
        >
          {isSubmitting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
          Save Corrections & Approve
        </Button>
      ) : (
        <Button
          onClick={onApprove}
          disabled={isSubmitting}
          className="flex-1"
          variant="default"
        >
          {isSubmitting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle className="h-4 w-4 mr-2" />}
          Approve As-Is
        </Button>
      )}

      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogTrigger asChild>
          <Button variant="destructive" disabled={isSubmitting}>
            <XCircle className="h-4 w-4 mr-2" />
            Reject
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Document</DialogTitle>
            <DialogDescription>
              This will discard all extracted data for this document. The original file will be preserved for reference. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                onReject();
                setRejectDialogOpen(false);
              }}
            >
              Confirm Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
```

### Step 4: Create Review List Component

The prioritized list of items needing review, sorted by confidence (highest first per the confidence-scoring skill -- easiest to review first). Each item shows a summary card with API number, document type, confidence score, and reason for flagging.

```typescript
// frontend/src/components/review/review-list.tsx
'use client';

import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import type { ReviewItem } from '@/lib/types';

interface ReviewListProps {
  selectedId: string | null;
  onSelectItem: (item: ReviewItem) => void;
}

export function ReviewList({ selectedId, onSelectItem }: ReviewListProps) {
  const { data, isLoading } = useSWR<{ total: number; results: ReviewItem[] }>(
    '/api/v1/review?status=pending&sort_by=confidence_desc&page_size=50',
    fetcher,
    { refreshInterval: 10000 }, // Refresh list periodically
  );

  if (isLoading) {
    return (
      <div className="space-y-2 p-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  if (!data || data.results.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        <p>No items pending review</p>
      </div>
    );
  }

  return (
    <div className="p-2">
      <div className="text-sm text-muted-foreground mb-2">
        {data.total} items pending review
      </div>
      <ScrollArea className="h-[calc(100vh-12rem)]">
        <div className="space-y-2">
          {data.results.map((item) => {
            const confidence = item.document.confidence_score;
            return (
              <Card
                key={item.id}
                className={`cursor-pointer transition-colors hover:bg-accent ${
                  selectedId === item.id ? 'border-primary bg-accent' : ''
                }`}
                onClick={() => onSelectItem(item)}
              >
                <CardContent className="p-3">
                  <div className="flex items-center justify-between mb-1">
                    <Badge variant="outline" className="text-xs">
                      {item.document.doc_type.replace(/_/g, ' ')}
                    </Badge>
                    <Badge
                      variant={confidence >= 0.5 ? 'secondary' : 'destructive'}
                    >
                      {(confidence * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <p className="text-sm font-medium font-mono">
                    {(item.extracted_data.data as any)?.api_number || 'No API #'}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {item.reason}
                  </p>
                  <Progress value={confidence * 100} className="mt-2 h-1" />
                </CardContent>
              </Card>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
```

### Step 5: Create Review Detail Component

The main side-by-side review interface that combines the PDF viewer and extracted fields form.

```typescript
// frontend/src/components/review/review-detail.tsx
'use client';

import { useState, useCallback } from 'react';
import useSWR, { mutate } from 'swr';
import { api, fetcher } from '@/lib/api';
import { DocumentViewerDynamic } from './document-viewer-dynamic';
import { ExtractedFieldsForm } from './extracted-fields-form';
import { ReviewActions } from './review-actions';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/components/ui/use-toast';
import type { ReviewItem } from '@/lib/types';

interface ReviewDetailProps {
  item: ReviewItem;
  onActionComplete: () => void;
}

export function ReviewDetail({ item, onActionComplete }: ReviewDetailProps) {
  const { toast } = useToast();
  const [editedFields, setEditedFields] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleFieldChange = useCallback((fieldPath: string, newValue: string) => {
    setEditedFields(prev => ({ ...prev, [fieldPath]: newValue }));
  }, []);

  const handleApprove = useCallback(async () => {
    setIsSubmitting(true);
    try {
      await api.patch(`/review/${item.id}`, {
        action: 'approve',
      });
      toast({ title: 'Document approved', description: 'Data accepted as-is.' });
      // Refresh the review list
      mutate((key: string) => typeof key === 'string' && key.startsWith('/api/v1/review'));
      setEditedFields({});
      onActionComplete();
    } catch (err) {
      toast({
        title: 'Approval failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [item.id, toast, onActionComplete]);

  const handleCorrect = useCallback(async () => {
    setIsSubmitting(true);
    try {
      await api.patch(`/review/${item.id}`, {
        action: 'correct',
        corrections: editedFields,
      });
      toast({ title: 'Corrections saved', description: 'Document approved with corrections.' });
      mutate((key: string) => typeof key === 'string' && key.startsWith('/api/v1/review'));
      setEditedFields({});
      onActionComplete();
    } catch (err) {
      toast({
        title: 'Correction failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [item.id, editedFields, toast, onActionComplete]);

  const handleReject = useCallback(async () => {
    setIsSubmitting(true);
    try {
      await api.patch(`/review/${item.id}`, {
        action: 'reject',
      });
      toast({ title: 'Document rejected', description: 'Extracted data discarded. Original file preserved.' });
      mutate((key: string) => typeof key === 'string' && key.startsWith('/api/v1/review'));
      setEditedFields({});
      onActionComplete();
    } catch (err) {
      toast({
        title: 'Rejection failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [item.id, toast, onActionComplete]);

  const confidence = item.document.confidence_score;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div>
          <h2 className="text-lg font-bold">
            {item.document.doc_type.replace(/_/g, ' ')}
          </h2>
          <p className="text-sm text-muted-foreground font-mono">
            {(item.extracted_data.data as any)?.api_number || 'Unknown'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Confidence:</span>
          <Badge variant={confidence >= 0.5 ? 'secondary' : 'destructive'}>
            {(confidence * 100).toFixed(1)}%
          </Badge>
        </div>
      </div>

      {/* Side-by-side: PDF left, fields right */}
      <div className="flex-1 grid grid-cols-2 min-h-0">
        {/* Left: PDF viewer */}
        <div className="border-r overflow-hidden">
          <DocumentViewerDynamic
            fileUrl={`/api/v1/documents/${item.document_id}/file`}
          />
        </div>

        {/* Right: Extracted fields */}
        <div className="overflow-auto p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium">Extracted Data</h3>
            {Object.keys(editedFields).length > 0 && (
              <Badge variant="outline" className="bg-blue-50 dark:bg-blue-950">
                {Object.keys(editedFields).length} field(s) edited
              </Badge>
            )}
          </div>
          <ExtractedFieldsForm
            extractedData={item.extracted_data}
            onFieldChange={handleFieldChange}
            editedFields={editedFields}
          />
        </div>
      </div>

      {/* Action bar at bottom */}
      <ReviewActions
        hasEdits={Object.keys(editedFields).length > 0}
        isSubmitting={isSubmitting}
        onApprove={handleApprove}
        onCorrect={handleCorrect}
        onReject={handleReject}
      />
    </div>
  );
}
```

### Step 6: Build the Review Queue Page

The top-level review page with a left sidebar list of review items and a main area for the detail view.

```typescript
// frontend/src/app/(dashboard)/review/page.tsx
'use client';

import { useState, useCallback } from 'react';
import { ReviewList } from '@/components/review/review-list';
import { ReviewDetail } from '@/components/review/review-detail';
import type { ReviewItem } from '@/lib/types';

export default function ReviewPage() {
  const [selectedItem, setSelectedItem] = useState<ReviewItem | null>(null);

  const handleActionComplete = useCallback(() => {
    // After approve/correct/reject, select the next item or clear
    setSelectedItem(null);
  }, []);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] -m-6">
      {/* Left: Review list (narrow) */}
      <div className="w-80 border-r bg-background shrink-0">
        <div className="p-4 border-b">
          <h1 className="text-lg font-bold">Review Queue</h1>
        </div>
        <ReviewList
          selectedId={selectedItem?.id ?? null}
          onSelectItem={setSelectedItem}
        />
      </div>

      {/* Right: Review detail (fills remaining space) */}
      <div className="flex-1 min-w-0">
        {selectedItem ? (
          <ReviewDetail
            item={selectedItem}
            onActionComplete={handleActionComplete}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center">
              <p className="text-lg">Select an item to review</p>
              <p className="text-sm mt-1">Click a document from the list on the left</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

### Step 7: Handle Edge Cases

1. **Empty review queue**: Show a success state ("All caught up!") when no items are pending
2. **PDF load failure**: Show error message with link to download the original file
3. **Missing fields**: Fields that are absent from the extracted data should show as empty inputs with a 0% confidence badge
4. **Very long field values**: Use textarea for fields longer than 100 characters
5. **Keyboard shortcuts**: Consider adding `Ctrl+Enter` to approve and `Escape` to close
6. **Auto-advance**: After approving/rejecting, automatically select the next item in the list

## Files to Create

- `frontend/src/components/review/document-viewer.tsx` - react-pdf PDF viewer with page navigation and zoom
- `frontend/src/components/review/document-viewer-dynamic.tsx` - Dynamic import wrapper for SSR safety
- `frontend/src/components/review/extracted-fields-form.tsx` - Editable fields with confidence color-coding
- `frontend/src/components/review/review-actions.tsx` - Approve/Correct/Reject buttons with reject confirmation dialog
- `frontend/src/components/review/review-list.tsx` - Scrollable list of review items with summary cards
- `frontend/src/components/review/review-detail.tsx` - Side-by-side PDF + fields review interface
- `frontend/src/app/(dashboard)/review/page.tsx` - Review queue page with list + detail layout

## Files to Modify

- None expected (all components are new)

## Contracts

### Provides (for downstream tasks)

- **Review page**: Route `/review` with list + detail layout
- **Document viewer**: `<DocumentViewerDynamic fileUrl={url} />` -- reusable PDF viewer (can be used elsewhere in the app)
- **Extracted fields form**: `<ExtractedFieldsForm extractedData={data} onFieldChange={fn} editedFields={map} />` -- reusable editable field display
- **Review actions**: `<ReviewActions onApprove={fn} onCorrect={fn} onReject={fn} hasEdits={bool} isSubmitting={bool} />`

### Consumes (from upstream tasks)

- Task 5.1: Layout shell, API client (`api.patch`), type definitions (`ReviewItem`, `ExtractedData`, `Document`), shadcn/ui components (Card, Badge, Progress, Input, Label, Button, Dialog, ScrollArea, Tooltip, Skeleton, Separator, Toast)
- Task 3.3: `GET /api/v1/review?status=pending&sort_by=confidence_desc` (list), `GET /api/v1/review/{id}` (detail), `PATCH /api/v1/review/{id}` (approve/correct/reject)
- Task 3.1: `GET /api/v1/documents/{id}/file` (PDF binary for viewer)

## Acceptance Criteria

- [ ] Review queue page renders with a list of pending review items on the left
- [ ] Items are sorted by confidence (highest first -- easiest to review)
- [ ] Each list item shows document type, API number, confidence score, and reason for flagging
- [ ] Clicking an item opens the side-by-side view with PDF on left and fields on right
- [ ] PDF viewer renders the document with page navigation (prev/next) and zoom controls
- [ ] Extracted fields display with confidence badges color-coded: green (>= 85%), yellow (50-84%), red (< 50%)
- [ ] Fields are sorted low-confidence first within the detail view
- [ ] Fields are editable -- typing in an input marks it as "edited" (blue highlight)
- [ ] Edited fields count badge shows number of changes
- [ ] "Approve As-Is" button sends `PATCH /api/v1/review/{id}` with `action: "approve"`
- [ ] "Save Corrections & Approve" button appears when fields are edited, sends corrections
- [ ] "Reject" button shows confirmation dialog, then sends `action: "reject"`
- [ ] After any action, item is removed from the list and selection clears
- [ ] Toast notification appears on successful approve/correct/reject
- [ ] Toast notification appears on API error
- [ ] Empty state shown when no items pending review
- [ ] PDF load error handled gracefully with error message
- [ ] No SSR errors (react-pdf loaded client-side only via dynamic import)
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `frontend/src/__tests__/components/review/extracted-fields-form.test.tsx`
- Test cases:
  - [ ] Renders all fields from extracted data
  - [ ] Fields sorted by confidence (lowest first)
  - [ ] Low-confidence fields have yellow/red background
  - [ ] Editing a field calls onFieldChange with correct key and value
  - [ ] Edited fields show blue highlight
  - [ ] Confidence badges show correct percentage and color

- Test file: `frontend/src/__tests__/components/review/review-actions.test.tsx`
- Test cases:
  - [ ] Shows "Approve As-Is" when no edits
  - [ ] Shows "Save Corrections & Approve" when edits exist
  - [ ] Reject button opens confirmation dialog
  - [ ] Confirming reject calls onReject
  - [ ] Canceling reject does not call onReject
  - [ ] Buttons disabled when isSubmitting is true

### API/Script Testing

- `GET /api/v1/review?status=pending` -- expect list of review items with nested document and extracted_data
- `GET /api/v1/documents/{id}/file` -- expect PDF binary response with content-type `application/pdf`
- `PATCH /api/v1/review/{id}` with `{ "action": "approve" }` -- expect 200
- `PATCH /api/v1/review/{id}` with `{ "action": "correct", "corrections": { "oil_bbls": "1500" } }` -- expect 200

### Browser Testing (Playwright MCP)

- Start: `cd frontend && npm run dev` (ensure backend is running with review queue data and document files)
- Navigate to: `http://localhost:3000/review`
- Actions:
  - Verify review list loads with pending items
  - Verify items show confidence badges and document type
  - Click the first item in the list
  - Verify PDF renders in the left panel (not a blank area or error)
  - Verify extracted fields render in the right panel with confidence badges
  - Verify low-confidence fields have colored backgrounds
  - Navigate PDF pages using prev/next buttons
  - Zoom in/out using zoom controls
  - Edit a field value (type a new value)
  - Verify field turns blue (edited indicator)
  - Verify "Save Corrections & Approve" button appears
  - Click "Save Corrections & Approve"
  - Verify toast notification appears
  - Verify item disappears from the list
  - Click another item, click "Reject"
  - Verify confirmation dialog appears
  - Click "Confirm Reject"
  - Verify item disappears from the list
  - Click another item, click "Approve As-Is" (no edits)
  - Verify item approved and removed
- Verify: No console errors, PDF renders correctly, no SSR errors
- User-emulating flow:
  1. User navigates to Review Queue from sidebar
  2. Sees list of 15 documents needing review
  3. Clicks the top item (highest confidence = easiest)
  4. PDF loads on the left -- it is a production report
  5. Right side shows extracted fields: API Number (95%), Oil BBL (72%), Gas MCF (45%)
  6. Gas MCF field is highlighted red -- user looks at PDF and sees the value
  7. User types the correct gas value in the field
  8. Field turns blue, "Save Corrections & Approve" appears
  9. User clicks the button -- toast confirms success
  10. Next item automatically... user selects a new item from the list
  11. This one looks fine -- user clicks "Approve As-Is"
  12. Moves to the next item
- Test assets: Ensure at least one PDF exists in the backend's data directory that can be served via the file endpoint. If no real data, create a test PDF.
- Screenshot: Review page with list visible, PDF rendering, fields with confidence badges, an edited field highlighted blue

### Build/Lint/Type Checks

- [ ] `npm run build` succeeds (no SSR errors from react-pdf)
- [ ] `npx tsc --noEmit` passes
- [ ] No TypeScript errors in review components

## Skills to Read

- `nextjs-dashboard` - react-pdf setup, dynamic import pattern, PDF.js worker configuration, review queue interface pattern
- `confidence-scoring` - Threshold values (0.85 auto-accept, 0.50 review, 0.50 reject), field-level thresholds, color coding, review workflow (approve/correct/reject), corrections tracking

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` - Section 3.3 (Document Preview), Section 4 (Review Queue UI) -- side-by-side layout, review workflow, field editing
- `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` - Section 5 (Confidence Scoring) for threshold details

## Git

- Branch: `feat/5.5-review-queue`
- Commit message prefix: `Task 5.5:`
