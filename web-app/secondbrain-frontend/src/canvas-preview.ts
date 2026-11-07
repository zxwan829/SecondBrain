export type CanvasPreviewShape = {
  id: string;
  type: string;
  shapeType: string;
  bound: [number, number, number, number];
  text?: string;
  opacity?: number;
  rotate?: number;
  filled?: boolean;
  fillColor?: unknown;
  strokeColor?: unknown;
  strokeWidth?: number;
  strokeStyle?: string;
  shapeStyle?: string;
  roughness?: number;
  radius?: number;
  color?: unknown;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: string | number;
  textAlign?: string;
  textVerticalAlign?: string;
  points?: Array<[number, number]>;
  mode?: string;
  frontEndpointStyle?: string;
  rearEndpointStyle?: string;
};

function safePreviewColor(value: string): boolean {
  const candidate = value.trim();
  if (!candidate || candidate.length > 160 || /url\s*\(|expression\s*\(|[;{}<>]/i.test(candidate)) return false;
  if (/^var\(--(?:affine|sb|edgeless)-[a-z0-9-]+(?:,\s*(?:#[0-9a-f]{3,8}|[a-z]+))?\)$/i.test(candidate)) return true;
  if (/^#[0-9a-f]{3,8}$/i.test(candidate) || /^[a-z]+$/i.test(candidate)) return true;
  return /^(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color)\([a-z0-9.,%+\-/\s]+\)$/i.test(candidate);
}

export function resolvePreviewColor(value: unknown, fallback: string): string {
  if (typeof value === 'string') return safePreviewColor(value) ? value : fallback;
  if (value && typeof value === 'object') {
    const candidate = value as Record<string, unknown>;
    for (const key of ['light', 'normal', 'value']) {
      if (typeof candidate[key] === 'string' && safePreviewColor(candidate[key])) return candidate[key];
    }
  }
  return fallback;
}

export function toCanvasPreviewShape(element: any): CanvasPreviewShape | null {
  const bound = element.elementBound;
  if (!bound || !(bound.w > 0) || !(bound.h > 0)) return null;
  const item: CanvasPreviewShape = {
    id: element.id,
    type: element.type,
    shapeType: element.shapeType ?? '',
    bound: [bound.x, bound.y, bound.w, bound.h],
    text: element.text?.toString?.() ?? '',
    opacity: element.opacity ?? 1,
    rotate: element.rotate ?? 0,
  };
  if (element.type === 'shape') Object.assign(item, {
    filled: element.filled, fillColor: element.fillColor,
    strokeColor: element.strokeColor, strokeWidth: element.strokeWidth,
    strokeStyle: element.strokeStyle, radius: element.radius,
    shapeStyle: element.shapeStyle, roughness: element.roughness,
    color: element.color, fontSize: element.fontSize,
    fontFamily: element.fontFamily, fontWeight: element.fontWeight,
    textAlign: element.textHorizontalAlign ?? element.textAlign,
    textVerticalAlign: element.textVerticalAlign,
  });
  if (element.type === 'connector') Object.assign(item, {
    points: (element.absolutePath ?? []).map((point: any) => [point.x ?? point[0], point.y ?? point[1]]),
    strokeColor: element.stroke, strokeWidth: element.strokeWidth,
    strokeStyle: element.strokeStyle, mode: element.mode,
    frontEndpointStyle: element.frontEndpointStyle,
    rearEndpointStyle: element.rearEndpointStyle,
  });
  return item;
}
