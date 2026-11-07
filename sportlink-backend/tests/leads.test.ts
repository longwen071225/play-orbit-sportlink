import type { FastifyInstance } from 'fastify';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app';
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

describe('A. 客户管理 + 统一响应信封', () => {
  it('创建咨询客户并返回 {success,data,error,requestId}', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/leads',
      payload: {
        parentName: '陈先生（虚构）',
        contact: 'demo-wechat-abc',
        childAge: 9,
        goal: '篮球基础',
        location: '福州市仓山区（虚构）',
      },
    });

    expect(res.statusCode).toBe(201);
    const body = res.json();
    expect(body.success).toBe(true);
    expect(body.error).toBeNull();
    expect(body.requestId).toEqual(expect.any(String));
    expect(res.headers['x-request-id']).toBe(body.requestId);
    expect(body.data).toMatchObject({
      parentName: '陈先生（虚构）',
      contact: 'demo-wechat-abc',
      childAge: 9,
      status: 'new',
    });
    expect(body.data.id).toEqual(expect.any(String));
    expect(body.data.createdAt).toEqual(expect.any(String));
  });

  it('参数校验失败也返回统一信封', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/leads',
      payload: { parentName: '', contact: '' },
    });
    expect(res.statusCode).toBe(400);
    const body = res.json();
    expect(body.success).toBe(false);
    expect(body.data).toBeNull();
    expect(body.error.code).toBe('VALIDATION_ERROR');
    expect(body.requestId).toEqual(expect.any(String));
  });

  it('客户详情包含咨询记录', async () => {
    const lead = await createLeadFixture();
    const saved = await app.inject({
      method: 'POST',
      url: `/api/leads/${lead.id}/messages`,
      payload: { content: '你好，想咨询上门训练', role: 'parent' },
    });
    expect(saved.statusCode).toBe(201);

    const res = await app.inject({ method: 'GET', url: `/api/leads/${lead.id}` });
    expect(res.statusCode).toBe(200);
    const detail = res.json().data;
    expect(detail.id).toBe(lead.id);
    expect(detail.messages).toHaveLength(1);
    expect(detail.messages[0].content).toBe('你好，想咨询上门训练');
    expect(detail.plans).toEqual([]);
  });

  it('列表支持按状态过滤', async () => {
    await createLeadFixture();
    await createLeadFixture({ parentName: '王女士（虚构）', status: 'booked' });
    const res = await app.inject({ method: 'GET', url: '/api/leads?status=booked' });
    expect(res.json().data).toHaveLength(1);
    expect(res.json().data[0].status).toBe('booked');
  });

  it('不存在的客户返回 404 统一信封', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/leads/does-not-exist' });
    expect(res.statusCode).toBe(404);
    expect(res.json().error.code).toBe('LEAD_NOT_FOUND');
  });
});
