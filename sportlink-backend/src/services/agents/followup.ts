import { prisma } from '../../db/prisma';
import { completeJSON } from '../../llm/complete';
import { FOLLOWUP_SYSTEM_PROMPT } from '../../llm/prompts';
import { toJson } from '../../lib/json';
import { FollowupOutputSchema, type FollowupOutput } from '../../schemas/llm';
import { ensureLead } from '../leads';
import { mockFollowup } from './mock';

/** Generates a draft only. Never sends anything and never schedules a send. */
export async function runFollowup(input: { leadId: string; channel?: string }) {
  const lead = await ensureLead(input.leadId);
  const [lastQuote, lastBooking, lastParentMessage] = await Promise.all([
    prisma.quote.findFirst({ where: { leadId: input.leadId }, orderBy: { createdAt: 'desc' } }),
    prisma.booking.findFirst({ where: { leadId: input.leadId }, orderBy: { createdAt: 'desc' } }),
    prisma.message.findFirst({
      where: { leadId: input.leadId, role: 'parent' },
      orderBy: { createdAt: 'desc' },
    }),
  ]);

  const user = [
    `客户姓名=${lead.parentName}；状态=${lead.status}；目标=${lead.goal ?? '未知'}`,
    `最近报价=${lastQuote ? `${lastQuote.totalCents} 分` : '无'}`,
    `最近预约=${lastBooking ? lastBooking.status : '无'}`,
    `最近家长消息=${lastParentMessage?.content ?? '无'}`,
    '请生成一条自然、简洁、不骚扰的跟进话术草稿。',
  ].join('\n');

  const { data } = await completeJSON({
    system: FOLLOWUP_SYSTEM_PROMPT,
    user,
    schema: FollowupOutputSchema,
    mockValue: () => mockFollowup(lead.status, lead.parentName, input.channel),
    repairHint: 'body 控制在 120 字以内；channel 只能是 wechat/sms/phone/in_app。',
  });

  const draftMessage = await prisma.message.create({
    data: {
      leadId: input.leadId,
      role: 'draft',
      content: toJson({ type: 'followup_draft', ...data }),
    },
  });

  return {
    draft: data as FollowupOutput,
    draftMessageId: draftMessage.id,
    sent: false,
    requiresHumanConfirmation: true,
  };
}
