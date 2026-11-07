import type { FastifyInstance } from 'fastify';
import { ZodTypeProvider } from 'fastify-type-provider-zod';
import { env } from '../config/env';
import { priceTableForDisplay } from '../config/pricing';
import { sendOk } from '../lib/response';
import { OkEnvelope } from '../schemas/api';

export async function registerHealthRoutes(app: FastifyInstance) {
  const r = app.withTypeProvider<ZodTypeProvider>();
  r.get(
    '/api/health',
    {
      schema: {
        tags: ['system'],
        summary: '健康检查：运行模式、模型与当前价目表',
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) =>
      sendOk(request, reply, {
        status: 'ok',
        mockAI: env.mockAI,
        model: env.mockAI ? 'mock' : env.DASHSCOPE_MODEL,
        priceTable: priceTableForDisplay(),
        time: new Date().toISOString(),
      }),
  );
}
