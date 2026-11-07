import { env } from '../../config/env';
import {
  FIELD_LABELS,
  MEDICAL_DISCLAIMER,
  REQUIRED_SALES_FIELDS,
  type CoachOutput,
  type ExtractedFields,
  type FollowupOutput,
  type QuoteOutput,
  type SalesOutput,
} from '../../schemas/llm';

/** Lightweight deterministic extraction so the offline demo chain really works. */
export function heuristicExtract(text: string, base?: Partial<ExtractedFields>): ExtractedFields {
  const ageM = text.match(/(\d{1,2})\s*(?:岁|周岁)/);
  const childAge = ageM
    ? Math.min(18, Math.max(1, Number(ageM[1])))
    : (base?.childAge ?? null);

  const timeM = text.match(
    /(周[一二三四五六日天1-7]|周末|平时|每天|上午|下午|晚上|放学后|工作日晚)[^，。,.!！\n]{0,12}/,
  );
  const availableTime = timeM ? timeM[0].trim() : (base?.availableTime ?? null);

  const goalWords = [
    '跳绳', '篮球', '足球', '体能', '协调性', '长高', '减肥', '增强体质', '感统',
    '游泳', '跑步', '羽毛球', '平衡', '专注力', '柔韧', '力量',
  ];
  const foundGoal = goalWords.find((word) => text.includes(word));
  const goalM = text.match(/目标[:：]?\s*([^，。,.!！\n]{1,30})/);
  const goal = foundGoal ?? goalM?.[1]?.trim() ?? (base?.goal ?? null);

  const expM = text.match(/(零基础|没基础|没有基础|有基础|学过|练过|初级|进阶|一年|两年)/);
  const experience = expM ? expM[0] : (base?.experience ?? null);

  const locM = text.match(/(?:住在|地址是|地址|小区|位于|在)([^，。,.!！\n]{1,20})/);
  const location = locM ? locM[1].trim() : (base?.location ?? null);

  return { childAge, goal, experience, availableTime, location };
}

export function missingSalesFields(ef: ExtractedFields): string[] {
  return REQUIRED_SALES_FIELDS.filter((key) => {
    const value = ef[key];
    return value == null || (typeof value === 'string' && value.trim() === '');
  });
}

export function mockSales(message: string, base: Partial<ExtractedFields>): SalesOutput {
  const ef = heuristicExtract(message, base);
  const missing = missingSalesFields(ef);
  const labels = missing.map((key) => FIELD_LABELS[key as keyof typeof FIELD_LABELS]);
  const suggestedReply = missing.length
    ? `您好，感谢咨询！为了给孩子安排合适的上门训练，还想跟您确认一下：${labels.join('、')}。您方便时回复即可，不会打扰您。`
    : `您好，已了解孩子的情况（${ef.childAge} 岁，目标：${ef.goal}）。我们可以先安排一次上门体验课，随后给您一份四周课程方案和报价，您看可以吗？`;

  return {
    extractedFields: ef,
    missingFields: missing,
    suggestedReply,
    recommendedService: missing.length ? 'ask_more' : 'package4',
  };
}

export function mockCoach(age: number, goal: string, experience: string): CoachOutput {
  const themes = ['基础动作与兴趣建立', '协调与平衡进阶', '目标技能专项练习', '综合巩固与成果展示'];
  const weeks = themes.map((theme, i) => ({
    week: i + 1,
    theme: `第 ${i + 1} 周：${theme}（${goal}）`,
    warmup: '5-8 分钟动态拉伸、关节激活与轻松追逐跑',
    mainTraining: `围绕「${goal}」的基础动作分解练习，每组 8-10 次、共 3 组，强度按 ${age} 岁儿童与「${experience}」基础调整`,
    game: '趣味接力或标志桶游戏，融入本节动作要点，控制对抗强度',
    cooldown: '5 分钟慢走 + 静态拉伸 + 呼吸放松',
    homework: `每天约 10 分钟亲子练习：${goal} 相关基础动作，家长陪同即可，无需器械`,
  }));
  return { age, goal, experience, weeks, disclaimer: MEDICAL_DISCLAIMER };
}

export function mockQuote(preferredSessions?: number): QuoteOutput {
  const sessions = preferredSessions ?? 4;
  const recommendedPackage = sessions >= env.PACKAGE_SESSIONS ? 'package4' : 'single';
  const quantity =
    recommendedPackage === 'package4'
      ? Math.max(1, Math.ceil(sessions / env.PACKAGE_SESSIONS))
      : sessions;

  return {
    recommendedPackage,
    quantity,
    note: `根据您期望的约 ${sessions} 节课，推荐「${
      recommendedPackage === 'package4' ? '四节套餐' : '单节课'
    }」。金额由系统按当前统一价目表自动计算，不含隐藏费用；上门交通安排另行协商。`,
    highlights: [
      recommendedPackage === 'package4'
        ? '四节套餐更适合建立稳定的训练节奏'
        : '单节课适合先体验、再决定是否长期安排',
      '上门训练，家长可全程陪同',
      '课程内容按孩子年龄与目标逐周调整',
    ],
  };
}

export function mockFollowup(
  status: string,
  parentName: string,
  channel?: string,
): FollowupOutput {
  const byStatus: Record<string, { tone: string; body: string; reason: string; subject: string }> = {
    new: {
      tone: '友好、简短',
      subject: '关于上门体育训练',
      body: `${parentName}您好，我是 SoloCoach 教练助理。之前收到您的咨询，若还想了解儿童上门训练，随时回复我就好，不着急。`,
      reason: '新咨询尚未深入沟通，先做一次低打扰的轻触达',
    },
    consulting: {
      tone: '温和、提供价值',
      subject: '课程方案小提示',
      body: `${parentName}您好，之前聊到的训练目标我记下了。需要的话可以给您一份四周活动安排参考，您方便时告诉我就行。`,
      reason: '沟通中，给出可选价值而不是催促',
    },
    quoted: {
      tone: '克制、不催单',
      subject: '报价已备好',
      body: `${parentName}您好，报价和课程方案已整理好，随时可发您。有任何疑问直接问我，不用急着决定。`,
      reason: '已报价，避免反复推销造成打扰',
    },
    booked: {
      tone: '贴心、确认信息',
      subject: '上课前的小提醒',
      body: `${parentName}您好，提醒一下已确认的上门训练时间。如需调整时间，提前告诉我即可，祝孩子玩得开心。`,
      reason: '已预约，只做必要的时间确认',
    },
    closed: {
      tone: '礼貌收尾',
      subject: '感谢',
      body: `${parentName}您好，感谢之前的信任。后续若有训练方面的问题，随时可以来问，祝一切顺利。`,
      reason: '已结束，礼貌收尾且不召回骚扰',
    },
  };
  const picked = byStatus[status] ?? byStatus.new;
  return {
    channel: (channel as FollowupOutput['channel']) ?? 'wechat',
    ...picked,
    doNotDisturb: true,
  };
}
