import type { SlashMenuItem } from '@blocksuite/affine-widget-slash-menu';

const labels: Record<string, string> = {
  'Other Headings': '其他标题', 'Heading 1': '一级标题', 'Heading 2': '二级标题', 'Heading 3': '三级标题', 'Heading 4': '标题 4', 'Heading 5': '标题 5',
  'Heading 6': '标题 6', Text: '正文', 'Code Block': '代码块', Quote: '引用',
  Divider: '分隔线', 'Inline equation': '行内公式', Equation: '公式块',
  'Bulleted List': '项目符号列表', 'Numbered List': '编号列表', 'To-do List': '待办事项',
  Bold: '加粗', Italic: '斜体', Underline: '下划线', Strikethrough: '删除线',
  'New Doc': '新建文档', 'Linked Doc': '关联文档', Table: '普通表格', Image: '图片',
  Link: '链接', Attachment: '附件', PDF: 'PDF 文件', Embed: '嵌入内容', YouTube: 'YouTube 视频',
  GitHub: 'GitHub 仓库', Figma: 'Figma 设计', Loom: 'Loom 视频', Frame: '画布框架',
  'Mind Map': '思维导图', Today: '今天', Tomorrow: '明天', Yesterday: '昨天', Now: '当前时间',
  Callout: '提示框', Todo: '待办',
  'Table View': '表格视图', 'Kanban View': '看板视图', 'Move Up': '上移内容块',
  'Move Down': '下移内容块', Copy: '复制内容块', Duplicate: '复制一份', Delete: '删除内容块',
};

const descriptions: Record<string, string> = {
  'Start typing with plain text.': '插入普通正文段落。',
  'Headings in the largest font.': '插入一级标题。',
  'Headings in the 2nd font size.': '插入二级标题。',
  'Headings in the 3rd font size.': '插入三级标题。',
  'Headings in the 4th font size.': '插入四级标题。',
  'Headings in the 5th font size.': '插入五级标题。',
  'Headings in the 6th font size.': '插入六级标题。',
  'Code snippet with formatting.': '插入代码块。',
  'Add a blockquote for emphasis.': '插入引用块。',
  'Visually separate content.': '插入分隔线。',
  'Create a inline equation.': '插入行内公式。',
  'Create a bulleted list.': '插入项目符号列表。',
  'Create a numbered list.': '插入编号列表。',
  'Add tasks to a to-do list.': '插入待办事项列表。',
  'Create a equation block.': '插入公式块。',
  'Create a simple table.': '插入普通表格。',
  'Insert an image.': '插入图片。',
  'Attach a file to document.': '插入附件。',
  'Display items in a table format.': '以表格形式显示数据库记录。',
  'Visualize data in a dashboard.': '以看板形式显示数据库记录。',
  'Shift this line up.': '将当前内容块上移。',
  'Shift this line down.': '将当前内容块下移。',
  'Copy this line to clipboard.': '复制当前内容块。',
  'Create a duplicate of this line.': '复制当前内容块并插入副本。',
  'Remove this line permanently.': '删除当前内容块。',
  'Upload a PDF to document.': '向文档添加 PDF 文件。',
  'Add a bookmark for reference.': '添加网页书签。',
  'Let your words stand out.': '突出显示一段内容。',
  'Insert a blank frame': '插入空白画布框架。',
  'Insert a mind map': '插入思维导图。',
  'Start a new document.': '创建并链接新文档。',
  'Link to another document.': '链接到另一个文档。',
  'For Google Drive, and more.': '嵌入 Google Drive 等内容。',
  'Embed a Figma document.': '嵌入 Figma 设计文件。',
  'Link to a GitHub repository.': '链接 GitHub 仓库。',
  'Embed a Loom video.': '嵌入 Loom 视频。',
  'Embed a YouTube video.': '嵌入 YouTube 视频。',
};

const aliases: Record<string, string[]> = {
  'Other Headings': ['其他标题', '标题 4', '标题 5', '标题 6'],
  'Code Block': ['代码', '代码块'], Quote: ['引用', '引用块'], Divider: ['分隔线'],
  'Inline equation': ['行内公式', '数学公式'], Equation: ['公式', '公式块'],
  'Bulleted List': ['列表', '项目符号', '无序列表'], 'Numbered List': ['编号', '有序列表'],
  'To-do List': ['待办', '任务清单', 'todo'], Table: ['表格', '普通表格'],
  Image: ['图片', '图像'], Attachment: ['附件', '文件'], Link: ['链接', '书签'],
  'Heading 1': ['一级标题', '标题一'], 'Heading 2': ['二级标题', '标题二'], 'Heading 3': ['三级标题', '标题三'],
  'Mind Map': ['思维导图', '脑图'], 'Table View': ['表格视图', '数据库表格'],
  'Kanban View': ['看板', '看板视图'], 'New Doc': ['新建文档', '新文档'],
  Callout: ['提示框', '标注'], Todo: ['待办', '任务'],
  PDF: ['PDF', 'PDF 文件'], Frame: ['框架', '画布框架'],
};

const numericGroupLabels: Record<string, string> = {
  '0': '基础',
  '1': '列表',
  '2': '样式',
  '3': '文档',
  '4': '内容与媒体',
  '5': '画布',
  '6': '日期',
  '7': '数据库',
  '8': '操作',
};

export function localizeSlashMenuItem(item: SlashMenuItem): SlashMenuItem {
  const dynamicName = item.name.startsWith('Frame: ') ? `框架：${item.name.slice(7)}`
    : item.name.startsWith('Group: ') ? `分组：${item.name.slice(7)}` : undefined;
  const label = labels[item.name] ?? dynamicName;
  const next = {
    ...item,
    ...(label ? { name: label } : {}),
    ...(item.description ? { description: descriptions[item.description] ?? item.description } : {}),
    ...('searchAlias' in item ? { searchAlias: [...new Set([...(item.searchAlias ?? []), ...(aliases[item.name] ?? []), ...(label ? [label] : [])])] } : {}),
  };
  // Keep the discriminated union intact: assigning `subMenu` after building a
  // SlashMenuItem union makes TypeScript treat the action branch as possible.
  const localized: SlashMenuItem = 'subMenu' in item
    ? { ...next, subMenu: item.subMenu.map(localizeSlashMenuItem) }
    : next as SlashMenuItem;
  if (item.group) {
    const [, groupName, index] = item.group.match(/^(\d+)_([^@]+)@(\d+)$/) ?? [];
    if (groupName) {
      const translated: Record<string, string> = { Basic: '基础', List: '列表', Style: '样式', Page: '文档', 'Content & Media': '内容与媒体', 'Edgeless Element': '画布元素', Date: '日期', Database: '数据库', Actions: '操作', ...numericGroupLabels };
      localized.group = `${Number(item.group.split('_')[0])}_${translated[groupName] ?? groupName}@${index}` as `${number}_${string}@${number}`;
    }
  }
  return localized;
}
