export type UserLocale = 'zh-CN' | 'en';
export type CaptureFailure = { code?: string | null; message?: string | null } | null | undefined;

export function captureStatusLabel(status: string, locale: UserLocale): string {
  const labels: Record<string, [string, string]> = {
    receiving: ['接收中', 'Receiving'],
    processing: ['处理中', 'Processing'],
    completed: ['已完成', 'Completed'],
    partial_success: ['部分完成', 'Partial success'],
    failed: ['处理失败', 'Failed'],
  };
  const pair = labels[status] ?? [status, status];
  return pair[locale === 'en' ? 1 : 0];
}

export function isImageOcrDescriptionUnavailable(item: {
  source_type?: string;
  review_path?: string | null;
  processor?: { kind?: string } | null;
  error?: CaptureFailure;
}): boolean {
  return item.source_type === 'image' && item.processor?.kind === 'image_ocr'
    && Boolean(item.review_path) && item.error?.code === 'processor_unavailable';
}

export function captureFailureLabel(error: CaptureFailure, locale: UserLocale): string {
  if (!error) return locale === 'en' ? 'No processing error' : '处理过程中未提供错误详情。';
  const code = error.code || 'unknown';
  const message = error.message || '';
  if (locale === 'en') return message || code;
  if (code === 'processor_unavailable') return '处理功能暂不可用（processor_unavailable）。';
  if (code === 'processing_interrupted') return '处理已中断；原始文件已保留，可以重试。';
  if (code === 'processing_failed') {
    const text = message.toLowerCase();
    if (/timed? ?out|time limit|timeout|deadline/.test(text)) return '处理超时；原始文件已保留，可以重试。';
    if (/encrypted pdf/.test(text)) return 'PDF 已加密，当前无法读取；原始文件已保留。';
    if (/pdf exceeds|page limit|too many pages/.test(text)) return 'PDF 页数超过处理上限；原始文件已保留。';
    if (/permission denied|read-only file system|operation not permitted/.test(text)) return '运行环境没有目标目录写入权限；原始文件已保留。';
    if (/no space left|disk full|out of space/.test(text)) return '存储空间不足，处理未完成；原始文件已保留。';
    if (/write failed|could not write|storage/.test(text)) return '文件保存失败；请检查存储状态后重试。';
    if (/ocr|tesseract|poppler/.test(text)) return 'OCR 处理失败；请核对原始文件后重试（processing_failed）。';
    if (/no readable|no extractable|text was extracted/.test(text)) return '未能从原始内容中提取可读文字（processing_failed）。';
    if (/raw artifact.*(hash|verification)|raw.*hash/.test(text)) return '原始文件完整性校验失败（processing_failed）。';
    if (/review artifact/.test(text)) return 'Review 文件校验失败；原始文件仍已保留（processing_failed）。';
    if (/url|host|address|public|redirect/.test(text)) return '网页地址无法安全获取或未提取到正文（processing_failed）。';
    if (/empty/.test(text)) return '原始内容为空，无法生成 Review（processing_failed）。';
    return '内容处理失败；原始文件已保留，可以重试（processing_failed）。';
  }
  return `处理失败；原始文件状态未变（错误代码：${code}）。`;
}

export function apiFailureLabel(detail: unknown, status: number, locale: UserLocale, area: 'capture' | 'review' | 'chat' | 'general' = 'general'): string {
  const source = typeof detail === 'string' ? detail : '';
  if (locale === 'en') return source || `${area === 'chat' ? 'Hermes API' : 'Request'} failed (HTTP ${status})`;
  if (/[\u3400-\u9fff]/.test(source)) return source;
  const text = source.toLowerCase();

  if (/20 mib|file.{0,20}large|upload.{0,20}size/.test(text) || status === 413) return '文件超过 20 MiB 限制，请选择较小的文件。';
  if (/unsupported file type|supported files|unsupported text source/.test(text)) return '此文件或收录类型暂不支持。';
  if (/does not match its declared file type/.test(text)) return '文件内容与扩展名不匹配，请确认文件类型后重试。';
  if (/could not preserve raw/.test(text)) return '原始文件保存失败，尚未确认收录；请保留输入并重试。';
  if (/review.*(changed|modified|hash|version)|content.*changed|sha-?256/.test(text) && area === 'review') return 'Review 内容或版本已变化，请刷新并核对最新内容后重试。';
  if (/promote.*disabled|production write approval/.test(text)) return '正式入库尚未开放，当前无法执行此操作。';
  if (/text must contain/.test(text)) return '文本不能为空，且长度不得超过 200,000 个字符。';
  if (/valid url up to/.test(text)) return '请输入不超过 2,048 个字符的有效网址。';
  if (/only public http/.test(text) || /non-public address|local and internal|non-standard url ports/.test(text)) return '该网址不符合安全采集要求，未开始抓取。';
  if (/could not be resolved/.test(text)) return '网址域名无法解析，请检查后重试。';
  if (/no readable page text/.test(text)) return '网页已获取，但没有提取到可读正文。';
  if (/not retryable/.test(text)) return '此条目当前状态不支持重试，请刷新收件箱后确认状态。';
  if (/raw asset.*(missing|unsafe|invalid)/.test(text)) return '找不到安全可读的原始文件，无法重试处理。';
  if (/preview/.test(text) && status === 415) return '此文件类型暂不支持站内预览，可下载原件查看。';
  if (/hermes/.test(text) && (status === 502 || status === 503)) return 'Hermes 服务暂时不可用，请稍后重试。';
  if (status === 401) return area === 'capture' ? '登录会话已失效，请重新登录后再试。' : '登录会话已失效，请重新登录。';
  if (status === 403) return '请求来源或访问权限校验未通过，请确认当前 App 地址和登录状态。';
  if (status === 404) return area === 'review' ? '找不到对应的 Review 条目。' : '请求的内容不存在或已不可用。';
  if (status === 409) return area === 'review' ? '审核内容或状态已变化，请刷新并核对后重试。' : '当前状态不允许此操作，请刷新后重试。';
  if (status === 415) return '此文件类型暂不支持此操作。';
  if (status === 429) return '请求过于频繁，请稍后重试。';
  if (status >= 500) return area === 'chat' ? 'Hermes 对话服务暂时不可用，请稍后重试。' : 'SecondBrain 服务暂时不可用，请稍后重试。';
  if (/failed to fetch|networkerror|network request failed|connection refused/.test(text)) return '网络连接失败，请检查连接后重试。';
  if (/timeout|timed out/.test(text)) return '请求超时，请稍后重试。';
  if (source) return `请求未成功（HTTP ${status}），请检查输入后重试。`;
  return `${area === 'chat' ? '对话' : '请求'}未成功（HTTP ${status}），请稍后重试。`;
}

export function reviewStatusLabel(status: string, locale: UserLocale): string {
  const labels: Record<string, [string, string]> = {
    pending: ['待审核', 'Pending'], approved: ['已批准', 'Approved'], promoting: ['正在正式入库', 'Promoting'],
    promoted: ['已入库', 'Promoted'], deferred: ['已暂缓', 'Deferred'], failed: ['处理失败', 'Failed'],
    processing: ['处理中', 'Processing'], receiving: ['接收中', 'Receiving'], completed: ['已完成', 'Completed'],
  };
  const pair = labels[status] ?? [status, status];
  return pair[locale === 'en' ? 1 : 0];
}

export function chatFailureLabel(message: string, locale: UserLocale): string {
  if (locale === 'en') return message;
  if (/[\u3400-\u9fff]/.test(message)) return message;
  const text = message.toLowerCase();
  if (/interrupted|connection.*closed|stream.*ended/.test(text)) return '对话连接中断，正在尝试恢复任务状态。';
  if (/stopped|cancelled|canceled/.test(text)) return '任务已停止。';
  if (/invalid.*session|session.*not found/.test(text)) return '会话不可用，请刷新会话列表后重试。';
  if (/identifier|run id|session id/.test(text)) return 'Hermes 未返回有效的会话或任务标识。';
  if (/hermes/.test(text) || /api unavailable|http 50[234]/.test(text)) return 'Hermes 对话服务暂时不可用，请稍后重试。';
  if (/timeout|timed out/.test(text)) return '对话请求超时，请稍后重试。';
  if (/failed to fetch|networkerror|connection refused/.test(text)) return '网络连接失败，请检查连接后重试。';
  return '对话任务未能完成；请检查连接或稍后重试。';
}

export function chatStatusLabel(status: string, locale: UserLocale): string {
  const labels: Record<string, [string, string]> = {
    queued: ['排队中', 'Queued'], pending: ['排队中', 'Pending'], receiving: ['接收中', 'Receiving'],
    running: ['执行中', 'Running'], processing: ['处理中', 'Processing'], completed: ['已完成', 'Completed'],
    failed: ['处理失败', 'Failed'], error: ['处理失败', 'Error'], cancelled: ['已停止', 'Cancelled'],
    canceled: ['已停止', 'Canceled'], interrupted: ['已中断', 'Interrupted'], expired: ['已过期', 'Expired'],
  };
  const pair = labels[status.toLowerCase()] ?? [status, status];
  return pair[locale === 'en' ? 1 : 0];
}

export function chatToolStageLabel(event: string, locale: UserLocale): string {
  const stage = event.toLowerCase();
  if (locale === 'en') return event;
  if (/start|begin/.test(stage)) return '工具开始';
  if (/progress|running|update/.test(stage)) return '工具运行中';
  if (/complete|finish|success|end/.test(stage)) return '工具已完成';
  if (/fail|error/.test(stage)) return '工具失败';
  return '工具状态';
}
