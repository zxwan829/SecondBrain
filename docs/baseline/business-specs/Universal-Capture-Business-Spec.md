# Universal Capture Business Specification

- Version: 1.1
- Status: canonical
- Date: 2026-10-10
- Source of Truth: SecondBrain V1 business contract; Hermes is runtime.

## 1. Purpose

Universal Capture accepts processable external or user-provided content, preserves a Raw asset, creates a Review candidate, and waits for Human Approval before Promote. It never writes formal Knowledge, auto-Promotes, or deletes original evidence.

## 2. V1 Supported Inputs

V1 MUST inputs: plain text, Markdown, TXT/readable text, Capture Context, URL/Web, PDF, Image/Screenshot, and Audio/Voice. Raw text may be saved as Markdown. **This specification defines the required scope, not live implementation status**; each input's production, partial-processing, OCR/STT and user acceptance evidence is tracked in [`00-CURRENT.md`](../00-CURRENT.md) and the dated Environment/Progress records. Partial implementation does not remove any V1 MUST requirement.

DEFERRED / POST-V1: DOC/DOCX, PPT/PPTX, XLS/XLSX, video, generic binary attachments, semantic deduplication, embeddings, RAG, Vector DB, QMD semantic capture, automatic knowledge graph, and transactional multi-file rollback.

## 3. Raw Contract

Raw target: `/knowledge-assets/00-Inbox`. Preserve the input, use a safe filename, never overwrite existing files, use a collision suffix, and return the actual final path. For URL/Web, preserve the original URL and capture timestamp; for PDF preserve the original PDF; for images preserve the original image; for audio preserve the original audio. Derived extraction/OCR/transcript never replaces original evidence.

## 4. Review Contract

Review target: `/secondbrain-write/10-Review`. Create an independent Review corresponding to the Capture, do not modify Raw, and do not write formal Knowledge. Use stable metadata.

## 5. Required Metadata

Use the existing Review schema without parallel metadata systems. Required fields follow the production Skill Review schema: `type`, `status`, `source_type`, `captured_at`, `original_asset`, `capture_context`, `tags`, and `review_status`. No parallel metadata is introduced; fields that are not applicable must remain explicitly empty or be documented by the input contract.

## 6. Tags and Relationships

Tags are SHOULD: empty or small is acceptable and tag quality does not fail Capture. Relationships/Wikilinks are SHOULD/OPTIONAL only when explicitly requested or when a clear, safe relationship is already available. Association failure never fails core Capture. Do not force full-library search.

## 7. Deduplication

V1 MUST provide filename collision protection. Filename collision protection is not semantic deduplication. Semantic, embedding, vector, QMD, and RAG deduplication are deferred.

## 8. Text Fast Path

This Fast Path applies only to plain text, Markdown, TXT/readable text, and Capture Context. Normal text Capture target is `skill_view x1` and `write_file x2`: load the Skill, write Raw, then write Review. By default do not call terminal, process_manage, code_execution, browser, web, computer_use, connections, skill_manage, search_files, or read_file. Exceptions require a real input need and an approved future contract.

URL/Web, PDF, Image/Screenshot, and Audio/Voice are also V1 MUST inputs under Sections 2, 13, and 15. They use the deterministic preserve-and-process paths defined for those input types; they are not covered by this text-only two-write Fast Path. Production implementation status remains recorded in `00-CURRENT.md`.

## 9. Success Verification

Model self-report is not success. Full Success requires Raw exists, Review exists, expected paths are valid, metadata is valid, and no Knowledge write occurred. User feedback must reflect verified artifacts/state.

## 10. Partial Failure

No cross-file transaction rollback is implemented in V1. Raw PASS plus Review FAIL is `PARTIAL SUCCESS / REVIEW FAILED`; Raw FAIL is Capture FAIL. Preserve successful safe artifacts, report the failed step, and permit safe retry. Never delete a successful Raw to simulate a transaction.

## 11. Retry and Idempotency

V1 provides SAFE RETRY, not strict transactional idempotency. Retries never overwrite Raw or Review; collisions use safe suffixes and may create new candidates. Content-hash idempotency is deferred.

## 12. Human Approval

Raw plus Review requires no Human Approval because it is low-risk staging. Review to Knowledge and Promote require Human Approval. Delete, overwrite, and permission changes require explicit approval.

## 13. V1 MUST

Text/Markdown/readable text, URL/Web, PDF, Image/Screenshot, and Audio/Voice inputs; Raw and Review creation; stable metadata; source traceability; applicable original_asset; filename collision protection; safe retry; accurate partial-failure reporting; real artifact verification; no automatic Knowledge write or Promote; Fast Path for text; concise success/failure response. Attachment input types remain MUST even though their production implementation is outstanding.

## 14. V1 SHOULD

Lightweight tags and explicit/simple relationships or Wikilinks. Their failure must not fail core Capture.

## 15. V1.1 Scope Expansion — 2026-10-10

URL/Web, PDF, Image/Screenshot, and Audio/Voice moved from DEFERRED to V1 MUST. They enter one lifecycle: Input → Detect Type → Preserve Raw → deterministic Extract/Fetch/OCR/Transcribe → Normalize → Universal Capture → Review → Human Approval → Knowledge. Text Fast Path remains unchanged; non-text may add deterministic processing. Extraction failure preserves Raw and returns PARTIAL SUCCESS. WeChat and Web App are V1 input channels that converge into this single pipeline; production integration remains separately unverified.

Required normalized representation may include title, source_type, captured_at, original_asset, source URL, extracted_text/transcript, capture_context, metadata, tags, and processing_status, reusing the existing Review schema. Security requirements include Private exclusion, controlled writes, SSRF protection for URL fetch, confined parser temporary files, and no path escape from KnowledgeAssets.

## 16. Deferred / Post-V1

Office documents (DOC/DOCX, PPT/PPTX, XLS/XLSX), video, generic binary attachment ingestion, semantic deduplication, embeddings, RAG, Vector DB, QMD semantic capture, automatic knowledge graph, mandatory related-note discovery, complex automatic tagging, and transactional multi-file rollback. URL/Web, PDF, Image/Screenshot, and Audio/Voice are V1 MUST per Section 15, not deferred.
