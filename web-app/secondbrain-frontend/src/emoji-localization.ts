import type { EmojiMartData } from '@emoji-mart/data';

// Emoji Mart's bundled English keywords do not include Chinese search terms.
// Keep a small, deterministic set of common Chinese names in the isolated PoC;
// the native searchable picker still supplies the complete emoji catalogue.
const chineseKeywords: Record<string, string[]> = {
  grinning: ['笑脸', '微笑', '开心'], smile: ['微笑', '笑脸', '开心'],
  laughing: ['大笑', '笑哭'], joy: ['笑哭', '开心'], cry: ['哭', '流泪'], sob: ['大哭', '痛哭'],
  heart_eyes: ['爱心眼', '喜欢'], thinking_face: ['思考', '想一想'], cat: ['猫', '猫咪', '喵'], dog: ['狗', '小狗'],
  red_heart: ['红心', '爱心', '喜欢'], heart: ['爱心', '喜欢'], broken_heart: ['心碎', '伤心'],
  fire: ['火', '火焰', '厉害'], thumbsup: ['点赞', '赞', '竖拇指'], '+1': ['点赞', '赞', '竖拇指'],
  clap: ['鼓掌', '拍手'], pray: ['祈祷', '谢谢'], wave: ['挥手', '你好', '再见'], sparkles: ['闪亮', '星光'],
  star: ['星星', '五角星'], sun: ['太阳', '晴天'], moon: ['月亮', '月亮脸'], rainbow: ['彩虹'], coffee: ['咖啡'],
  pizza: ['披萨', '比萨'], cake: ['蛋糕'], rocket: ['火箭'], tada: ['庆祝', '礼物'], party_popper: ['派对', '庆祝'],
  check_mark: ['对勾', '完成', '正确'], x: ['叉号', '错误'], warning: ['警告', '注意'],
};

export function withChineseEmojiKeywords<T extends EmojiMartData>(data: T): T {
  const emojis = { ...data.emojis };
  for (const [id, additions] of Object.entries(chineseKeywords)) {
    const emoji = emojis[id as keyof typeof emojis];
    if (!emoji) continue;
    emojis[id as keyof typeof emojis] = {
      ...emoji,
      keywords: [...new Set([...(emoji.keywords ?? []), ...additions])],
    } as (typeof emojis)[keyof typeof emojis];
  }
  return { ...data, emojis };
}
