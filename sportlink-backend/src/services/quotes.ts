import { computeQuote, type ComputedQuote } from '../config/pricing';
import { prisma } from '../db/prisma';
import type { QuoteOutput } from '../schemas/llm';
import { advanceLeadStatus, ensureLead } from './leads';

/**
 * Persists a Quote + QuoteItems. Every monetary value comes from computeQuote(),
 * which only reads the configured price table - never from the LLM output.
 */
export async function saveQuote(leadId: string, recommendation: QuoteOutput) {
  await ensureLead(leadId);
  const computed: ComputedQuote = computeQuote(
    recommendation.recommendedPackage,
    recommendation.quantity,
  );

  const quote = await prisma.quote.create({
    data: {
      leadId,
      currency: 'CNY',
      totalCents: computed.totalCents,
      note: recommendation.note,
      items: {
        create: computed.items.map((item) => ({
          name: item.name,
          quantity: item.quantity,
          unitPriceCents: item.unitPriceCents,
          amountCents: item.amountCents,
        })),
      },
    },
    include: { items: true },
  });

  await advanceLeadStatus(leadId, 'quoted', ['new', 'consulting']);
  return { quote, computed };
}
