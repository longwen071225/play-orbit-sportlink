import type { FastifyInstance } from 'fastify';
import { ZodTypeProvider } from 'fastify-type-provider-zod';
import { sendOk } from '../lib/response';
import { CoachBody, FollowupBody, OkEnvelope, QuoteBody, RunBody, SalesBody } from '../schemas/api';
import { runCoach } from '../services/agents/coach';
import { runFollowup } from '../services/agents/followup';
import { runOrchestrator } from '../services/agents/orchestrator';
import { runQuote } from '../services/agents/quote';
import { runSales } from '../services/agents/sales';

export async function registerAgentRoutes(app: FastifyInstance) {
  const r = app.withTypeProvider<ZodTypeProvider>();

  r.post(
    '/api/agent/sales',
    {
      schema: {
        tags: ['B. AI 销售员工'],
        summary: '抽取咨询信息 / 补全缺失字段 / 生成回复',
        description: '返回 extractedFields, missingFields, suggestedReply, recommendedService；对话与抽取结果写入 Message 表',
        body: SalesBody,
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) => sendOk(request, reply, await runSales(request.body)),
  );

  r.post(
    '/api/agent/coach',
    {
      schema: {
        tags: ['C. AI 课程员工'],
        summary: '生成四周课程计划并入库',
        description: '每周包含 theme/warmup/mainTraining/game/cooldown/homework；仅一般体育活动建议',
        body: CoachBody,
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) => sendOk(request, reply, await runCoach(request.body)),
  );

  r.post(
    '/api/agent/quote',
    {
      schema: {
        tags: ['D. AI 商务员工'],
        summary: '生成套餐推荐与报价（金额后端确定性计算）',
        description: 'LLM 只决定套餐类型与数量；金额来自可配置价目表，写入 Quote + QuoteItem',
        body: QuoteBody,
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) => sendOk(request, reply, await runQuote(request.body)),
  );

  r.post(
    '/api/agent/followup',
    {
      schema: {
        tags: ['F. AI 跟进员工'],
        summary: '生成跟进话术草稿（不自动发送）',
        description: '仅保存为 draft 消息，sent=false，需要人工确认后才可发送',
        body: FollowupBody,
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) => sendOk(request, reply, await runFollowup(request.body)),
  );

  r.post(
    '/api/agent/run',
    {
      schema: {
        tags: ['G. AI 总控员工'],
        summary: '编排完整链路：识别需求 -> 询问/课程 -> 报价 -> 跟进 -> 下一步建议',
        description: '逐步真实调用各业务模块并落库；返回每步 status/result/durationMs/log 与结构化 nextStep 下一步建议；预约与外部发送停在人工确认门禁',
        body: RunBody,
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) => sendOk(request, reply, await runOrchestrator(request.body)),
  );
}
