import { describe, expect, it } from 'vitest';
import { sanitizeArchiveExportHtml } from './archive-export-safety';

describe('native resource HTML export boundary', () => {
  it('keeps rich table geometry and visible formatting while dropping executable nodes', () => {
    const result = sanitizeArchiveExportHtml('<table><tr><td rowspan="2" colspan="3" style="text-align:center;color:red">保留</td></tr></table><script>alert(1)</script><iframe srcdoc="x"></iframe>');
    expect(result).toContain('rowspan="2"'); expect(result).toContain('colspan="3"');
    expect(result).toMatch(/text-align:\s*center/); expect(result).toContain('保留');
    expect(result).not.toContain('<script'); expect(result).not.toContain('<iframe');
  });
  it('strips handlers, active URLs and CSS network fetches without deleting text', () => {
    const result = sanitizeArchiveExportHtml('<a href="javascript:alert(1)" onclick="x()">文本</a><img src="data:image/svg+xml,<svg onload=x()>" onerror="x()"><p style="background-image:url(https://example.invalid/pixel);text-align:right">位置</p>');
    expect(result).not.toContain('javascript:'); expect(result).not.toContain('onclick'); expect(result).not.toContain('onerror');
    expect(result).not.toContain('data:image/svg'); expect(result).not.toContain('url(');
    expect(result).toMatch(/text-align:\s*right/); expect(result).toContain('文本'); expect(result).toContain('位置');
  });
});
