# Universal Capture Business Specification

- Version: 1.1
- Status: canonical
- Date: 2026-10-10
- Source of Truth: SecondBrain V1 business contract; Hermes is runtime.

## 1. Purpose

Universal Capture protects original sources and applies different Knowledge entry gates: Agent/automatic content proceeds through Raw → Review → Human Approval → controlled Promote; a trusted user explicitly creating/importing into a chosen formal Knowledge target may use a separate limited Core user-write interface without repeat Review. D093 defines the approved future contract, not current production permissions.

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

Raw plus Review staging requires no Human Approval. **Agent/autonomous Review → Knowledge Promote requires explicit user approval**; a trusted user's specific create/upload/archive action authorizes only that limited destination write, subject to Core identity, target, conflict, audit and version checks. Delete, overwrite, permission changes and AI edits to existing formal Knowledge still require specific authorization and diff/version protection.

## 13. V1 MUST

Text/Markdown/readable text, URL/Web, PDF, Image/Screenshot, and Audio/Voice inputs; Raw and Review creation; stable metadata; source traceability; applicable original_asset; filename collision protection; safe retry; accurate partial-failure reporting; real artifact verification; no automatic Knowledge write or Promote; Fast Path for text; concise success/failure response. Attachment input types remain MUST even though their production implementation is outstanding.

## 14. V1 SHOULD

Lightweight tags and explicit/simple relationships or Wikilinks. Their failure must not fail core Capture.

## 15. V1.1 Scope Expansion — 2026-10-10

URL/Web, PDF, Image/Screenshot, and Audio/Voice moved from DEFERRED to V1 MUST. Agent-generated candidates retain the lifecycle Input → Detect Type → Preserve Raw → deterministic Extract/Fetch/OCR/Transcribe → Normalize → Universal Capture → Review → Human Approval → Knowledge. A trusted user explicitly selecting formal Knowledge may preserve the source and use a separate Core direct-write path without waiting for AI metadata suggestions. Text Fast Path remains unchanged; non-text may add deterministic processing. Extraction failure preserves Raw and returns PARTIAL SUCCESS. WeChat and Web App are V1 input channels that converge into this single pipeline; production integration remains separately unverified.

Required normalized representation may include title, source_type, captured_at, original_asset, source URL, extracted_text/transcript, capture_context, metadata, tags, and processing_status, reusing the existing Review schema. Security requirements include Private exclusion, controlled writes, SSRF protection for URL fetch, confined parser temporary files, and no path escape from KnowledgeAssets.

## 16. Deferred / Post-V1

Office documents (DOC/DOCX, PPT/PPTX, XLS/XLSX), video, generic binary attachment ingestion, semantic deduplication, embeddings, RAG, Vector DB, QMD semantic capture, automatic knowledge graph, mandatory related-note discovery, complex automatic tagging, and transactional multi-file rollback. URL/Web, PDF, Image/Screenshot, and Audio/Voice are V1 MUST per Section 15, not deferred.


## 17. D093 user-direct Knowledge and AI-controlled changes (2026-11-09 APPROVED, NOT IMPLEMENTED)

- **Separate trusted actions:** Core must validate the actual authenticated user's explicit target/action, or a trustworthy channel identity and consent binding. Client fields, Markdown frontmatter and Agent claims never serve as approval credentials. Keep narrow scoped Writer capabilities, path/Host/Origin checks, ETag/hash, replay/idempotency, conflict handling and audits. Do not grant Hermes generic Knowledge RW or entire-Vault RW.
- **Different entry semantics:** User-authored and explicitly imported notes/documents become eligible for formal Knowledge without an extra Review. Agent-generated content, autonomous summaries proposed for Knowledge, and AI changes to formal documents remain candidates until user review. A user explicitly accepting a final AI draft and exact save target needs only one confirmation, with AI/Run provenance retained. Rejected AI candidates remain auditable outside formal Knowledge. User edits are versioned; immutable Raw sources are never overwritten.
- **Derived data not another AI knowledge write:** Markdown/TXT may serve directly as AI-readable text. For PDF/web/image/audio/BlockSuite, retain original plus separately version-bound readable extraction as needed. OCR/transcription, deterministic extraction and rebuildable indexes do not themselves need Human Approval. AI-created suggestions affecting formal labels/metadata require the existing relevant user confirmation.
- **Failure and provenance:** Record stable source identity, hash/version, trusted operator/action, origin kind (user-authored, user-imported, AI-drafted) and AI originating Run/task. Parsing status must be queryable (indexed, processing, failed/unparsed, unsupported); a failed document remains discoverable by filename, source and date. Updated, renamed, deleted, restored and revoked documents cannot leave stale queryable content.
- **Stage gates:** WP6/#78 proves minimal user Markdown/notes direct entry, existing Agent Review/Promote and Hermes body-grounded references. Later V1 P4/P2 gates retain BlockSuite structured Markdown projection and five-part round-trip, existing V1 input extraction, statuses, source/index lifecycle. Office documents, video, archives and embeddings/vector databases remain deferred from V1 MUST and are not WP6 prerequisites.
