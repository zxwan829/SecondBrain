import { describe, expect, it } from 'vitest';
import { parseDailyBriefResponse, parseProjectsResponse } from './projects-brief-wire';

const checkedAt = '2026-10-20T01:30:00Z';
const hash = 'a'.repeat(64);

function projectsResponse(status = 'real') {
  return {
    status,
    items: status === 'real' || status === 'partial' ? [{
      id: 'project_synth_1', title: 'Synthetic project', status: 'active', next_step: 'Review synthetic state',
      recent_activity: { kind: 'task', occurred_at: checkedAt }, linked_notes: [{ id: 'note_synth_1', version: hash }],
      updated_at: checkedAt, source_ref: { id: 'project_file_synth_1', version: hash },
    }] : [],
    pagination: { limit: 1, offset: 0, has_more: false },
    source: status === 'not_configured' || status === 'unavailable' ? null : { kind: 'explicit-project-index' },
    freshness: { checked_at: checkedAt },
  };
}

function briefResponse(status = 'real', requestedDate = '2026-10-20') {
  const hasRecord = ['real', 'partial', 'stale', 'failed'].includes(status);
  const generationStatus = status === 'real' ? 'generated' : status;
  return {
    status,
    items: hasRecord ? [{ brief_id: 'brief_synth_1', date: requestedDate, timezone: 'Asia/Shanghai', generated_at: checkedAt,
      generation_status: generationStatus, categories: ['synthetic'], summary: 'Synthetic daily brief only.',
      source_refs: [{ kind: 'task', id: 'task_synth_1', version: hash }] }] : [],
    source: status === 'not_configured' || status === 'unavailable' ? null : { kind: 'core-daily-brief-store' },
    freshness: { checked_at: checkedAt },
  };
}

describe('Projects and Daily Brief frozen read wire', () => {
  it('accepts the bounded Projects not_configured state and preserves checked_at', () => {
    const parsed = parseProjectsResponse(projectsResponse('not_configured'));
    expect(parsed?.status).toBe('not_configured');
    expect(parsed?.items).toEqual([]);
    expect(parsed?.freshness.checked_at).toBe(checkedAt);
  });

  it('requires exact UTC RFC3339 freshness and rejects normalized invalid dates', () => {
    const offsetFreshness = projectsResponse('not_configured') as ReturnType<typeof projectsResponse> & { freshness: { checked_at: string } };
    offsetFreshness.freshness.checked_at = '2026-10-20T09:30:00+08:00';
    expect(parseProjectsResponse(offsetFreshness)).toBeNull();
    const impossibleDate = briefResponse('not_configured') as ReturnType<typeof briefResponse> & { freshness: { checked_at: string } };
    impossibleDate.freshness.checked_at = '2026-02-30T10:00:00Z';
    expect(parseDailyBriefResponse(impossibleDate, '2026-10-20', 'Asia/Shanghai')).toBeNull();
  });

  it('rejects legacy Core not_configured responses missing the frozen freshness field', () => {
    const projects = projectsResponse('not_configured') as Record<string, unknown>;
    delete projects.freshness;
    expect(parseProjectsResponse(projects)).toBeNull();
    const brief = briefResponse('not_configured') as Record<string, unknown>;
    delete brief.freshness;
    expect(parseDailyBriefResponse(brief, '2026-10-20', 'Asia/Shanghai')).toBeNull();
  });

  it('accepts explicit project source refs and only the frozen project fields', () => {
    const parsed = parseProjectsResponse(projectsResponse());
    expect(parsed?.items[0]).toMatchObject({ id: 'project_synth_1', status: 'active', source_ref: { id: 'project_file_synth_1', version: hash } });
    const withPrivateBody = projectsResponse() as ReturnType<typeof projectsResponse> & { items: Array<Record<string, unknown>> };
    withPrivateBody.items[0].original_text = 'must not pass';
    expect(parseProjectsResponse(withPrivateBody)).toBeNull();
  });

  it('rejects contradictory Projects states, path-like source IDs, and invalid hashes', () => {
    const contradictory = projectsResponse('real') as ReturnType<typeof projectsResponse> & { items: unknown[] };
    contradictory.items = [];
    expect(parseProjectsResponse(contradictory)).toBeNull();
    const pathRef = projectsResponse() as ReturnType<typeof projectsResponse> & { items: Array<{ source_ref: { id: string; version: string } }> };
    pathRef.items[0].source_ref.id = '../Private/secret.md';
    expect(parseProjectsResponse(pathRef)).toBeNull();
    const badHash = projectsResponse() as ReturnType<typeof projectsResponse> & { items: Array<{ source_ref: { id: string; version: string } }> };
    badHash.items[0].source_ref.version = 'not-a-sha';
    expect(parseProjectsResponse(badHash)).toBeNull();
  });

  it('accepts a dated saved Brief only when its requested timezone and source hashes match', () => {
    const parsed = parseDailyBriefResponse(briefResponse(), '2026-10-20', 'Asia/Shanghai');
    expect(parsed?.status).toBe('real');
    expect(parsed?.items[0].summary).toBe('Synthetic daily brief only.');
    expect(parseDailyBriefResponse(briefResponse(), '2026-10-21', 'Asia/Shanghai')).toBeNull();
    expect(parseDailyBriefResponse(briefResponse(), '2026-10-20', 'UTC')).toBeNull();
  });

  it.each(['partial', 'stale', 'failed'] as const)('accepts explicit Brief %s state without promoting it to real', (status) => {
    const parsed = parseDailyBriefResponse(briefResponse(status), '2026-10-20', 'Asia/Shanghai');
    expect(parsed?.status).toBe(status);
    expect(parsed?.items[0].generation_status).toBe(status);
  });

  it('rejects stale source hashes, duplicate refs, and unexpected private fields', () => {
    const badHash = briefResponse() as ReturnType<typeof briefResponse> & { items: Array<{ source_refs: Array<{ version: string }> }> };
    badHash.items[0].source_refs[0].version = 'x';
    expect(parseDailyBriefResponse(badHash, '2026-10-20', 'Asia/Shanghai')).toBeNull();
    const extra = briefResponse() as ReturnType<typeof briefResponse> & { items: Array<Record<string, unknown>> };
    extra.items[0].session_id = 'private-session';
    expect(parseDailyBriefResponse(extra, '2026-10-20', 'Asia/Shanghai')).toBeNull();
    const duplicate = briefResponse() as ReturnType<typeof briefResponse> & { items: Array<{ source_refs: Array<{ kind: string; id: string; version: string }> }> };
    duplicate.items[0].source_refs.push({ ...duplicate.items[0].source_refs[0] });
    expect(parseDailyBriefResponse(duplicate, '2026-10-20', 'Asia/Shanghai')).toBeNull();
  });
});
