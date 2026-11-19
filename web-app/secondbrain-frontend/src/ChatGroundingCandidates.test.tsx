import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChatGroundingCandidates } from './ChatGroundingCandidates';

const event = { event: 'knowledge.grounding-candidates', version: 1, session_id: 'session-A', status: 'available',
  answer_attribution: 'not_established', items: [{ citation_id: 'AbcdefghijklmnopQRST', title: 'Synthetic source',
    sha256: 'a'.repeat(64), knowledge_status: 'version_verified', provenance_status: 'verified' }] };
const ok = () => new Response(JSON.stringify(event), { status: 200,
  headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store' } });

afterEach(() => vi.unstubAllGlobals());

describe('ChatGroundingCandidates', () => {
  it('waits for explicit user action, presents metadata, and clears on session/query change', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok()); vi.stubGlobal('fetch', fetchMock);
    const view = render(<ChatGroundingCandidates sessionId="session-A" query="synthetic question" locale="en" disabled={false} />);
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Check Knowledge sources' }));
    await screen.findByText('Synthetic source');
    expect(fetchMock).toHaveBeenCalledWith('/api/chat/sessions/session-A/grounding-candidates', expect.objectContaining({
      method: 'POST', cache: 'no-store', body: JSON.stringify({ query: 'synthetic question' }),
    }));
    expect(screen.getByText(/not_established/)).toBeTruthy();
    view.rerender(<ChatGroundingCandidates sessionId="session-B" query="new question" locale="en" disabled={false} />);
    await waitFor(() => expect(screen.queryByText('Synthetic source')).toBeNull());
  });
});
