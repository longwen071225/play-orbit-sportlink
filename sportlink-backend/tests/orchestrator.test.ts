import type { FastifyInstance } from 'fastify';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app';
import { PRICE_TABLE } from '../src/config/pricing';
import { prisma } from '../src/db/prisma';
import { createLeadFixture, resetDb } from './helpers';

let app: FastifyInstance;

beforeAll(async () => {
  app = await buildApp();
  await app.ready();
});
afterAll(async () => {
  await app.close();
});
beforeEach(resetDb);

const step = (body: { data: { steps: { step: string; status: string }[] } }, name: string) =>
  body.data.steps.find((s) => s.step === name);

describe('G. AI 总控：真实编排 + 人工确认门禁', () => {
  it('信息齐全时逐步调用各模块并写入数据库', async () => {
    const lead = await createLeadFixture();
    const res = await app.inject({
      method: 'POST',
      url: '/api/agent/run',
      payload: {
        leadId: lead.id,
        message: '我家孩子8岁，想提升跳绳和体能，零基础，周末下午可以上课，住在鼓楼区',
      },
    });
    const body = res.json();
    expect(body.success).toBe(true);
    expect(body.data.status).toBe('completed');
    expect(body.data.nextStep.action).toBe('confirm_booking');
    expect(body.data.nextStep.requiresHumanConfirmation).toBe(true);
    expect(body.data.durationMs).toEqual(expect.any(Number));

    expect(step(body, 'sales')?.status).toBe('success');
    expect(step(body, 'coach')?.status).toBe('success');
    expect(step(body, 'quote')?.status).toBe('success');
    expect(step(body, 'followup')?.status).toBe('success');
    expect(step(body, 'booking')?.status).toBe('awaiting_confirmation');
    expect(step(body, 'external_send')?.status).toBe('awaiting_confirmation');

    // Every step exposes status / result / durationMs / log.
    for (const s of body.data.steps) {
      expect(s.status).toEqual(expect.any(String));
      expect(s.durationMs).toEqual(expect.any(Number));
      expect(s.log).toEqual(expect.any(String));
      expect(s).toHaveProperty('result');
    }

    const plan = await prisma.trainingPlan.findFirst({ where: { leadId: lead.id } });
    expect(plan).not.toBeNull();
    expect(plan?.weeksJson).toContain('week');

    const quote = await prisma.quote.findFirst({ where: { leadId: lead.id }, include: { items: true } });
    expect(quote?.totalCents).toBe(PRICE_TABLE.package4.unitPriceCents);
    expect(quote?.items).toHaveLength(1);

    // The human gates did NOT create a booking or send anything.
    expect(await prisma.booking.count({ where: { leadId: lead.id } })).toBe(0);
    const draft = await prisma.message.findFirst({ where: { leadId: lead.id, role: 'draft' } });
    expect(draft).not.toBeNull();

    const run = await prisma.agentRun.findUniqueOrThrow({
      where: { id: body.data.runId },
      include: { actions: true },
    });
    expect(run.status).toBe('completed');
    expect(run.actions.length).toBeGreaterThanOrEqual(6);
    expect(run.inputMessage).toContain('8岁');

    const updatedLead = await prisma.lead.findUniqueOrThrow({ where: { id: lead.id } });
    expect(updatedLead.status).toBe('quoted');
  });

  it('关键信息缺失时先询问，跳过课程与报价', async () => {
    const lead = await createLeadFixture({ goal: null, childAge: null });
    const res = await app.inject({
      method: 'POST',
      url: '/api/agent/run',
      payload: { leadId: lead.id, message: '你好，想了解一下' },
    });

    const body = res.json();
    expect(body.data.status).toBe('needs_input');
    expect(body.data.nextStep.action).toBe('ask_parent');
    expect(body.data.nextStep.suggestedReply).toEqual(expect.any(String));
    expect(step(body, 'sales')?.status).toBe('success');
    expect(step(body, 'coach')?.status).toBe('skipped');
    expect(step(body, 'quote')?.status).toBe('skipped');
    expect(await prisma.trainingPlan.count({ where: { leadId: lead.id } })).toBe(0);
    expect(await prisma.quote.count({ where: { leadId: lead.id } })).toBe(0);
  });

  it('跟进员工只生成草稿，不自动发送', async () => {
    const lead = await createLeadFixture({ status: 'quoted' });
    const res = await app.inject({
      method: 'POST',
      url: '/api/agent/followup',
      payload: { leadId: lead.id },
    });
    expect(res.statusCode).toBe(200);
    const data = res.json().data;
    expect(data.sent).toBe(false);
    expect(data.requiresHumanConfirmation).toBe(true);
    expect(data.draft.doNotDisturb).toBe(true);
    expect(data.draft.body.length).toBeGreaterThan(0);
  });
});
