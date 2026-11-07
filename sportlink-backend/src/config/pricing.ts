import { env } from './env';

export type PackageType = 'single' | 'package4';

export interface PriceDefinition {
  name: string;
  unitPriceCents: number;
  sessionsPerUnit: number;
}

/**
 * Single source of truth for prices. All amounts are integer CNY cents.
 * The LLM is NEVER given these numbers and its output schema has no price fields.
 */
export const PRICE_TABLE: Record<PackageType, PriceDefinition> = {
  single: {
    name: '单节课',
    unitPriceCents: env.PRICE_SINGLE_CENTS,
    sessionsPerUnit: 1,
  },
  package4: {
    name: '四节套餐',
    unitPriceCents: env.PRICE_PACKAGE_4_CENTS,
    sessionsPerUnit: env.PACKAGE_SESSIONS,
  },
};

export interface ComputedQuoteItem {
  name: string;
  quantity: number;
  unitPriceCents: number;
  amountCents: number;
  amountYuan: string;
}

export interface ComputedQuote {
  currency: string;
  items: ComputedQuoteItem[];
  totalCents: number;
  totalYuan: string;
  totalSessions: number;
}

export function yuan(cents: number): string {
  return (cents / 100).toFixed(2);
}

/** Deterministic quote calculation. No LLM input can influence the amounts. */
export function computeQuote(packageType: PackageType, quantity: number): ComputedQuote {
  const def = PRICE_TABLE[packageType];
  const qty = Math.max(1, Math.min(50, Math.trunc(quantity) || 1));
  const amountCents = def.unitPriceCents * qty;

  return {
    currency: 'CNY',
    items: [
      {
        name: def.name,
        quantity: qty,
        unitPriceCents: def.unitPriceCents,
        amountCents,
        amountYuan: yuan(amountCents),
      },
    ],
    totalCents: amountCents,
    totalYuan: yuan(amountCents),
    totalSessions: def.sessionsPerUnit * qty,
  };
}

export function priceTableForDisplay() {
  return (Object.keys(PRICE_TABLE) as PackageType[]).map((key) => {
    const def = PRICE_TABLE[key];
    return {
      packageType: key,
      name: def.name,
      unitPriceCents: def.unitPriceCents,
      unitPriceYuan: yuan(def.unitPriceCents),
      sessionsPerUnit: def.sessionsPerUnit,
    };
  });
}
