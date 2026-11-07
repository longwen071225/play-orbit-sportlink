import type { FastifyInstance } from 'fastify';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app';
import { prisma } from '../src/db/prisma';
import { createLeadFixture, resetDb } from './helpers';

let app: FastifyInstance;

const TIME_A = { startAt: '2026-12-05T10:00:00+08:00', endAt: '2026-12-05T11:00:00+08:00' };

beforeAll(async () => {
  app = await buildApp();
  await app.ready();
});
afterAll(async () => {
  await app.close();
});
beforeEach(resetDb);

describe('E. 预约：冲突检测 + 人工确认门禁', () => {
  it('创建的预约始终是 pending', async () => {
    const lead = await createLeadFixture();
    const res = await app.inject({
      method: 'POST',
      url: '/api/bookings',
      payload: { leadId: lead.id, ...TIME_A },
    });
    expect(res.statusCode).toBe(201);
    expect(res.json().data.status).toBe('pending');
  });

  it('重叠时段返回 409 BOOKING_CONFLICT，相邻时段允许', async () => {
    const lead = await createLeadFixture();
    await app.inject({
      method: 'POST',
      url: '/api/bookings',
      payload: { leadId: lead.id, ...TIME_A },
    });

    const overlap = await app.inject({
      method: 'POST',
      url: '/api/bookings',
      payload: {
        leadId: lead.id,
        startAt: '2026-12-05T10:30:00+08:00',
        endAt: '2026-12-05T11:30:00+08:00',
      },
    });
    expect(overlap.statusCode).toBe(409);
    expect(overlap.json().error.code).toBe('BOOKING_CONFLICT');

    const adjacent = await app.inject({
      method: 'POST',
      url: '/api/bookings',
      payload: {
        leadId: lead.id,
        startAt: '2026-12-05T11:00:00+08:00',
        endAt: '2026-12-05T12:00:00+08:00',
      },
    });
    expect(adjacent.statusCode).toBe(201);
  });

  it('只有 PATCH /confirm 能把预约改成 confirmed，并推进客户状态', async () => {
    const lead = await createLeadFixture({ status: 'quoted' });
    const created = await app.inject({
      method: 'POST',
      url: '/api/bookings',
      payload: { leadId: lead.id, ...TIME_A },
    });
    const id = created.json().data.id;

    let stored = await prisma.booking.findUniqueOrThrow({ where: { id } });
    expect(stored.status).toBe('pending');

    const confirmed = await app.inject({ method: 'PATCH', url: `/api/bookings/${id}/confirm` });
    expect(confirmed.statusCode).toBe(200);
    expect(confirmed.json().data.status).toBe('confirmed');

    stored = await prisma.booking.findUniqueOrThrow({ where: { id } });
    expect(stored.status).toBe('confirmed');
    const updatedLead = await prisma.lead.findUniqueOrThrow({ where: { id: lead.id } });
    expect(updatedLead.status).toBe('booked');

    const again = await app.inject({ method: 'PATCH', url: `/api/bookings/${id}/confirm` });
    expect(again.statusCode).toBe(409);
    expect(again.json().error.code).toBe('INVALID_STATE_TRANSITION');
  });

  it('带 JSON Content-Type 但无 body 的 PATCH /confirm 也能正常确认', async () => {
    const lead = await createLeadFixture();
    const created = await app.inject({
      method: 'POST',
      url: '/api/bookings',
      payload: { leadId: lead.id, ...TIME_A },
    });
    const id = created.json().data.id;

    const confirmed = await app.inject({
      method: 'PATCH',
      url: `/api/bookings/${id}/confirm`,
      headers: { 'content-type': 'application/json' },
    });
    expect(confirmed.statusCode).toBe(200);
    expect(confirmed.json().data.status).toBe('confirmed');
  });

  it('endAt 不晚于 startAt 时返回 400', async () => {
    const lead = await createLeadFixture();
    const res = await app.inject({
      method: 'POST',
      url: '/api/bookings',
      payload: {
        leadId: lead.id,
        startAt: '2026-12-05T11:00:00+08:00',
        endAt: '2026-12-05T10:00:00+08:00',
      },
    });
    expect(res.statusCode).toBe(400);
  });
});
