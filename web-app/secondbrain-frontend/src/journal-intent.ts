const JOURNAL_PREFIX = /^\s*(?:记一下|记下来|写日记|记录一下|保存这段话|写到日记里)(?:[：:,，\s]+|$)/;

export function isExplicitJournalIntent(text: string): boolean {
  return JOURNAL_PREFIX.test(text);
}
