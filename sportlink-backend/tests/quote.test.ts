import { beforeEach, describe, expect, it } from 'vitest';
import { PRICE_TABLE, computeQuote } from '../src/config/pricing';
import { prisma } from '../src/db/prisma';
import { QuoteOutputSchema } from '../src/schemas/llm';
import { runQuote } from '../src/services/agents/quote';
import { createLeadFixture, resetDb } from './helpers';

beforeEach(resetDb);

describe('D. 报价：金额由后端确定性计算', () => {
  it('单节课与四节套餐按配置价目表计算', () => {
    expect(computeQuote('single', 1).totalCents).toBe(PRICE_TABLE.single.unitPriceCents);
    expect(computeQuote('package4', 1).totalCents).toBe(PRICE_TABLE.package4.unitPriceCents);
    expect(computeQuote('package4', 2).totalCents).toBe(PRICE_TABLE.package4.unitPriceCents * 2);
    expect(computeQuote('single', 3).items[0].amountCents).toBe(
      PRICE_TABLE.single.unitPriceCents * 3,
    );
    expect(computeQuote('package4', 2).totalSessions).toBe(8);
  });

  it('LLM 输出 schema 没有价格字段，注入的价格会被 Zod 剥离', () => {
    const injected = QuoteOutputSchema.parse({
      recommendedPackage: 'single',
      quantity: 1,
      note: '说明',
      highlights: ['理由'],
      priceCents: 1,
      totalYuan: '0.01',
    });
    expect(injected).not.toHaveProperty('priceCents');
    expect(injected).not.toHaveProperty('totalYuan');
  });

  it('AI 商务员工落库后金额仍完全来自后端', async () => {
    const lead = await createLeadFixture({ status: 'consulting' });
    const result = await runQuote({ leadId: lead.id, preferredSessions: 4 });

    expect(result.recommendation.recommendedPackage).toBe('package4');
    expect(result.computed.totalCents).toBe(PRICE_TABLE.package4.unitPriceCents);

    const quote = await prisma.quote.findUniqueOrThrow({
      where: { id: result.quoteId },
      include: { items: true },
    });
    expect(quote.totalCents).toBe(PRICE_TABLE.package4.unitPriceCents);
    expect(quote.items).toHaveLength(1);
    expect(quote.items[0].unitPriceCents).toBe(PRICE_TABLE.package4.unitPriceCents);
    expect(quote.items[0].amountCents).toBe(quote.totalCents);
    expect(quote.items[0].quantity).toBe(1);

    const updatedLead = await prisma.lead.findUniqueOrThrow({ where: { id: lead.id } });
    expect(updatedLead.status).toBe('quoted');
  });
});
