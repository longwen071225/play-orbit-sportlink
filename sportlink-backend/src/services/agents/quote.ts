import { priceTableForDisplay } from '../../config/pricing';
import { completeJSON } from '../../llm/complete';
import { QUOTE_SYSTEM_PROMPT } from '../../llm/prompts';
import { QuoteOutputSchema } from '../../schemas/llm';
import { ensureLead } from '../leads';
import { saveQuote } from '../quotes';
import { mockQuote } from './mock';

export async function runQuote(input: {
  leadId: string;
  message?: string;
  preferredSessions?: number;
}) {
  const lead = await ensureLead(input.leadId);
  const user = [
    `客户需求：${input.message ?? lead.goal ?? '未明确说明'}`,
    `客户状态：${lead.status}；儿童年龄：${lead.childAge ?? '未知'}`,
    '可选套餐标识：single（单节课）、package4（四节套餐）。',
    '请只输出 recommendedPackage、quantity、note、highlights。严禁输出任何价格或金额数字。',
  ].join('\n');

  const { data } = await completeJSON({
    system: QUOTE_SYSTEM_PROMPT,
    user,
    schema: QuoteOutputSchema,
    mockValue: () => mockQuote(input.preferredSessions),
    repairHint: 'recommendedPackage 只能是 single 或 package4；不要包含价格字段。',
  });

  const { quote, computed } = await saveQuote(input.leadId, data);
  return {
    quoteId: quote.id,
    recommendation: data,
    computed,
    priceTable: priceTableForDisplay(),
    quote,
  };
}
