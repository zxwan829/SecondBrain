import { describe, expect, it } from 'vitest';
import { apiFailureLabel, captureFailureLabel, captureStatusLabel, isImageOcrDescriptionUnavailable, reviewStatusLabel } from './user-messages';

describe('Chinese user-visible status and error copy', () => {
  it('uses the agreed Simplified Chinese capture status labels while preserving English mode', () => {
    expect(captureStatusLabel('completed', 'zh-CN')).toBe('已完成');
    expect(captureStatusLabel('processing', 'zh-CN')).toBe('处理中');
    expect(captureStatusLabel('partial_success', 'zh-CN')).toBe('部分完成');
    expect(captureStatusLabel('failed', 'zh-CN')).toBe('处理失败');
    expect(captureStatusLabel('partial_success', 'en')).toBe('Partial success');
  });

  it('maps backend capture error codes and reasons without passing English through', () => {
    expect(captureFailureLabel({ code: 'processor_unavailable', message: 'No OCR processor was configured.' }, 'zh-CN'))
      .toContain('处理功能暂不可用');
    expect(captureFailureLabel({ code: 'processing_failed', message: 'Image OCR exceeded its time limit' }, 'zh-CN'))
      .toContain('处理超时');
    expect(captureFailureLabel({ code: 'processing_interrupted', message: 'Processing stopped before completion.' }, 'zh-CN'))
      .toContain('处理已中断');
    expect(captureFailureLabel({ code: 'processing_failed', message: 'Low-level unexpected exception.' }, 'zh-CN'))
      .not.toContain('Low-level unexpected exception');
    expect(captureFailureLabel({ code: 'processing_failed', message: 'Image OCR exceeded its time limit' }, 'en'))
      .toBe('Image OCR exceeded its time limit');
  });

  it('treats only OCR-complete image records with a Review as missing visual description', () => {
    expect(isImageOcrDescriptionUnavailable({ source_type: 'image', review_path: 'capture.md', processor: { kind: 'image_ocr' }, error: { code: 'processor_unavailable' } })).toBe(true);
    expect(isImageOcrDescriptionUnavailable({ source_type: 'image', processor: { kind: 'image_ocr' }, error: { code: 'processor_unavailable' } })).toBe(false);
    expect(isImageOcrDescriptionUnavailable({ source_type: 'image', review_path: 'capture.md', processor: { kind: 'image_ocr' }, error: { code: 'processing_failed' } })).toBe(false);
  });

  it('maps known HTTP causes and never renders an unknown backend English error in Chinese', () => {
    expect(apiFailureLabel('Uploaded file content does not match its declared file type', 400, 'zh-CN', 'capture'))
      .toContain('扩展名不匹配');
    const unknown = apiFailureLabel('Unexpected lower-level storage failure', 500, 'zh-CN', 'capture');
    expect(unknown).toContain('SecondBrain 服务');
    expect(unknown).not.toContain('Unexpected lower-level storage failure');
    expect(apiFailureLabel('Unexpected lower-level storage failure', 500, 'en', 'capture'))
      .toBe('Unexpected lower-level storage failure');
  });

  it('localizes Review decision statuses and retains unknown technical codes', () => {
    expect(reviewStatusLabel('promoting', 'zh-CN')).toBe('正在正式入库');
    expect(reviewStatusLabel('custom_state_code', 'zh-CN')).toBe('custom_state_code');
  });
});
