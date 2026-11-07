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

export function resolvePreviewColor(value: unknown, fallback: string): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object') {
    const candidate = value as Record<string, unknown>;
    for (const key of ['light', 'normal', 'value']) {
      if (typeof candidate[key] === 'string') return candidate[key] as string;
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
