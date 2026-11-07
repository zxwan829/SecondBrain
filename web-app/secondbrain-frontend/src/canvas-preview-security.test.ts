import { describe, expect, it } from 'vitest';
import { resolvePreviewColor } from './canvas-preview';
describe('inline canvas preview colors', () => {
  it('keeps archived theme and literal colors', () => {
    for (const value of ['#fff', '#12345678', 'transparent', 'rgba(1,2,3,.5)', 'var(--affine-primary-color)']) expect(resolvePreviewColor(value, '#000')).toBe(value);
    expect(resolvePreviewColor({ light: '#abc' }, '#000')).toBe('#abc');
  });
  it('does not let color payloads turn a preview into a network-fetching SVG', () => {
    for (const value of ['url(https://example.invalid/pixel)', 'url(data:image/svg+xml,x)', 'red;fill:url(x)', '<script>x</script>']) expect(resolvePreviewColor(value, '#000')).toBe('#000');
  });
});
