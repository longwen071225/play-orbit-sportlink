import { prisma } from '../db/prisma';
import { AppError } from '../lib/errors';
import { fromJson } from '../lib/json';
import type { CreateLeadInput } from '../schemas/api';
import type { Week } from '../schemas/llm';

export async function ensureLead(id: string) {
  const lead = await prisma.lead.findUnique({ where: { id } });
  if (!lead) throw new AppError(404, 'LEAD_NOT_FOUND', `客户 ${id} 不存在`);
  return lead;
}

export async function createLead(input: CreateLeadInput) {
  return prisma.lead.create({
    data: {
      parentName: input.parentName,
      contact: input.contact,
      childAge: input.childAge ?? null,
      goal: input.goal ?? null,
      location: input.location ?? null,
      status: input.status ?? 'new',
    },
  });
}

export async function listLeads(query: { status?: string; limit: number }) {
  return prisma.lead.findMany({
    where: query.status ? { status: query.status } : {},
    orderBy: { createdAt: 'desc' },
    take: query.limit,
  });
}

export async function getLeadDetail(id: string) {
  await ensureLead(id);
  const lead = await prisma.lead.findUniqueOrThrow({
    where: { id },
    include: {
      messages: { orderBy: { createdAt: 'asc' } },
      plans: { orderBy: { createdAt: 'desc' } },
      quotes: { orderBy: { createdAt: 'desc' }, include: { items: true } },
      bookings: { orderBy: { startAt: 'asc' } },
      agentRuns: {
        orderBy: { createdAt: 'desc' },
        include: { actions: { orderBy: { createdAt: 'asc' } } },
      },
    },
  });
  return {
    ...lead,
    plans: lead.plans.map((plan) => ({
      ...plan,
      weeks: fromJson<Week[]>(plan.weeksJson),
    })),
  };
}

export async function addMessage(leadId: string, role: string, content: string) {
  await ensureLead(leadId);
  return prisma.message.create({ data: { leadId, role, content } });
}

/** Only advances a lead along the funnel; never downgrades booked/closed. */
export async function advanceLeadStatus(id: string, to: string, allowedFrom: string[]) {
  const lead = await prisma.lead.findUnique({ where: { id }, select: { status: true } });
  if (lead && allowedFrom.includes(lead.status)) {
    await prisma.lead.update({ where: { id }, data: { status: to } });
  }
}
