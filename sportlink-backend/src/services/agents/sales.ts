import { prisma } from '../../db/prisma';
import { completeJSON } from '../../llm/complete';
import { SALES_SYSTEM_PROMPT } from '../../llm/prompts';
import { toJson } from '../../lib/json';
import {
  FIELD_LABELS,
  REQUIRED_SALES_FIELDS,
  SalesOutputSchema,
  type SalesOutput,
} from '../../schemas/llm';
import { advanceLeadStatus, ensureLead } from '../leads';
import { mockSales } from './mock';

/**
 * Deterministic boundary guard: missingFields is recomputed from actual values,
 * so the model cannot both fabricate a field and claim it is missing. When key
 * info is absent we force "ask more" and make sure the reply asks a question.
 */
export function sanitizeSales(raw: SalesOutput): SalesOutput {
  const ef = raw.extractedFields;
  const missing = REQUIRED_SALES_FIELDS.filter((key) => {
    const value = ef[key];
    return value == null || (typeof value === 'string' && value.trim() === '');
  });

  let suggestedReply = raw.suggestedReply;
  if (missing.length > 0 && !/[?？]/.test(suggestedReply)) {
    suggestedReply += ` 另外还想确认一下：${missing
      .map((key) => FIELD_LABELS[key])
      .join('、')}。`;
  }

  return {
    extractedFields: ef,
    missingFields: [...missing],
    suggestedReply,
    recommendedService: missing.length > 0 ? 'ask_more' : raw.recommendedService,
  };
}

export interface SalesRunResult {
  leadId: string;
  extraction: SalesOutput;
  persisted: {
    parentMessageId: string;
    extractionMessageId: string;
    assistantMessageId: string;
  };
}

export async function runSales(input: { leadId: string; message: string }): Promise<SalesRunResult> {
  const lead = await ensureLead(input.leadId);
  const recent = await prisma.message.findMany({
    where: { leadId: input.leadId },
    orderBy: { createdAt: 'desc' },
    take: 8,
  });
  const history = recent.reverse().map((m) => `${m.role}: ${m.content}`).join('\n');
  const user = [
    `客户已有资料：家长=${lead.parentName}，儿童年龄=${lead.childAge ?? '未知'}，目标=${lead.goal ?? '未知'}，位置=${lead.location ?? '未知'}，状态=${lead.status}`,
    `最近对话：\n${history || '（暂无）'}`,
    `家长最新消息：${input.message}`,
  ].join('\n\n');

  const { data } = await completeJSON({
    system: SALES_SYSTEM_PROMPT,
    user,
    schema: SalesOutputSchema,
    mockValue: () =>
      mockSales(input.message, {
        childAge: lead.childAge,
        goal: lead.goal,
        location: lead.location,
        experience: null,
        availableTime: null,
      }),
    repairHint: 'extractedFields 中未知字段必须填 null，不要编造。',
  });
  const extraction = sanitizeSales(data);

  const parentMsg = await prisma.message.create({
    data: { leadId: input.leadId, role: 'parent', content: input.message },
  });
  const extractionMsg = await prisma.message.create({
    data: {
      leadId: input.leadId,
      role: 'system',
      content: toJson({ type: 'sales_extraction', ...extraction }),
    },
  });
  const assistantMsg = await prisma.message.create({
    data: { leadId: input.leadId, role: 'assistant', content: extraction.suggestedReply },
  });

  const ef = extraction.extractedFields;
  await prisma.lead.update({
    where: { id: input.leadId },
    data: {
      ...(lead.childAge == null && ef.childAge != null ? { childAge: ef.childAge } : {}),
      ...(lead.goal == null && ef.goal != null ? { goal: ef.goal } : {}),
      ...(lead.location == null && ef.location != null ? { location: ef.location } : {}),
    },
  });
  await advanceLeadStatus(input.leadId, 'consulting', ['new']);

  return {
    leadId: input.leadId,
    extraction,
    persisted: {
      parentMessageId: parentMsg.id,
      extractionMessageId: extractionMsg.id,
      assistantMessageId: assistantMsg.id,
    },
  };
}
