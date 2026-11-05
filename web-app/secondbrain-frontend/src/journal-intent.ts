// Route only an explicit, message-leading capture instruction. This remains a
// deterministic safety boundary; ordinary prose is left to Chat and does not
// imply consent to write.
const JOURNAL_PREFIX = /^\s*(?:(?:请|麻烦)?\s*(?:帮我)?\s*)?(?:记一下|记下来|写日记|记录一下|保存这段话|写到日记里|记到日记里|记录到日记里)(?:[：:,，\s]+|$)/;

export function isExplicitJournalIntent(text: string): boolean {
  return JOURNAL_PREFIX.test(text);
}
