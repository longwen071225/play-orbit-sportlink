import type { FastifyInstance } from 'fastify';
import { ZodTypeProvider } from 'fastify-type-provider-zod';
import { sendOk } from '../lib/response';
import {
  CreateLeadBody,
  CreateMessageBody,
  LeadIdParams,
  ListLeadsQuery,
  OkEnvelope,
} from '../schemas/api';
import * as leads from '../services/leads';

export async function registerLeadRoutes(app: FastifyInstance) {
  const r = app.withTypeProvider<ZodTypeProvider>();

  r.post(
    '/api/leads',
    {
      schema: {
        tags: ['A. 客户管理'],
        summary: '创建咨询客户',
        description: '字段：parentName, contact, childAge?, goal?, location?, status?',
        body: CreateLeadBody,
        response: { 201: OkEnvelope },
      },
    },
    async (request, reply) => {
      const lead = await leads.createLead(request.body);
      return sendOk(request, reply, lead, 201);
    },
  );

  r.get(
    '/api/leads',
    {
      schema: {
        tags: ['A. 客户管理'],
        summary: '获取客户列表',
        querystring: ListLeadsQuery,
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) => sendOk(request, reply, await leads.listLeads(request.query)),
  );

  r.get(
    '/api/leads/:id',
    {
      schema: {
        tags: ['A. 客户管理'],
        summary: '查看客户详情与咨询记录',
        description: '返回客户资料、全部 Message、课程方案、报价、预约与 AgentRun 记录',
        params: LeadIdParams,
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) =>
      sendOk(request, reply, await leads.getLeadDetail(request.params.id)),
  );

  r.post(
    '/api/leads/:id/messages',
    {
      schema: {
        tags: ['A. 客户管理'],
        summary: '保存家长消息',
        params: LeadIdParams,
        body: CreateMessageBody,
        response: { 201: OkEnvelope },
      },
    },
    async (request, reply) => {
      const message = await leads.addMessage(
        request.params.id,
        request.body.role,
        request.body.content,
      );
      return sendOk(request, reply, message, 201);
    },
  );
}
