import { prisma } from '../src/db/prisma';

export async function resetDb() {
  await prisma.agentAction.deleteMany();
  await prisma.agentRun.deleteMany();
  await prisma.quoteItem.deleteMany();
  await prisma.quote.deleteMany();
  await prisma.booking.deleteMany();
  await prisma.trainingPlan.deleteMany();
  await prisma.message.deleteMany();
  await prisma.lead.deleteMany();
}

export function createLeadFixture(overrides: Record<string, unknown> = {}) {
  return prisma.lead.create({
    data: {
      parentName: '林女士（虚构）',
      contact: 'demo-wechat-001',
      childAge: 8,
      goal: '跳绳',
      location: '福州市鼓楼区（虚构）',
      status: 'new',
      ...overrides,
    },
  });
}
