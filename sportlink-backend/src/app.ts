import cors from '@fastify/cors';
import Fastify from 'fastify';
import swagger from '@fastify/swagger';
import swaggerUi from '@fastify/swagger-ui';
import {
  hasZodFastifySchemaValidationErrors,
  jsonSchemaTransform,
  serializerCompiler,
  validatorCompiler,
} from 'fastify-type-provider-zod';
import { env } from './config/env';
import { AppError } from './lib/errors';
import { envelopeFail, newRequestId } from './lib/response';
import { registerAgentRoutes } from './routes/agent';
import { registerBookingRoutes } from './routes/bookings';
import { registerHealthRoutes } from './routes/health';
import { registerLeadRoutes } from './routes/leads';

function corsOrigin(value: string): boolean | string | string[] {
  if (value === '*' || value.toLowerCase() === 'true') return true;
  const parts = value.split(',').map((s) => s.trim()).filter(Boolean);
  return parts.length === 1 ? parts[0] : parts;
}

export async function buildApp() {
  const app = Fastify({
    logger: env.isTest ? false : { level: env.LOG_LEVEL },
    bodyLimit: 1024 * 1024,
  });

  // Zod drives both request validation and OpenAPI generation.
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);

  // Bodyless endpoints (e.g. PATCH /confirm) are often called with a JSON
  // Content-Type. Treat an empty body as {} so schema validation decides.
  app.removeContentTypeParser('application/json');
  app.addContentTypeParser(
    'application/json',
    { parseAs: 'string' },
    (_request, body, done) => {
      const text = (body as string).trim();
      if (text === '') {
        done(null, {});
        return;
      }
      try {
        done(null, JSON.parse(text));
      } catch (error) {
        done(error as Error);
      }
    },
  );

  app.addHook('onRequest', async (request, reply) => {
    request.requestId = newRequestId();
    reply.header('x-request-id', request.requestId);
  });

  await app.register(cors, {
    origin: corsOrigin(env.CORS_ORIGIN),
    methods: ['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'],
  });

  await app.register(swagger, {
    openapi: {
      openapi: '3.0.3',
      info: {
        title: 'SoloCoach AI Backend',
        version: '1.0.0',
        description:
          '面向独立儿童体育教练的一人公司 AI 员工系统后端。所有 /api/* 响应统一为 {success,data,error,requestId}。金额由后端确定性计算；预约与外部发送必须人工确认。',
      },
      servers: [{ url: '/', description: '本地服务' }],
      tags: [
        { name: 'system', description: '健康检查' },
        { name: 'A. 客户管理', description: 'Lead / Message' },
        { name: 'B. AI 销售员工', description: '信息抽取与追问' },
        { name: 'C. AI 课程员工', description: '四周课程方案' },
        { name: 'D. AI 商务员工', description: '套餐推荐与报价' },
        { name: 'E. 预约管理', description: '待确认预约与确认' },
        { name: 'F. AI 跟进员工', description: '跟进话术草稿' },
        { name: 'G. AI 总控员工', description: '多步编排与执行日志' },
      ],
    },
    transform: jsonSchemaTransform,
  });

  await app.register(swaggerUi, { routePrefix: '/documentation' });

  app.setErrorHandler((error, request, reply) => {
    const requestId = request.requestId ?? 'unknown';
    const shaped = error as Error & {
      statusCode?: number;
      code?: string;
      validation?: unknown;
    };

    let statusCode = 500;
    let code = 'INTERNAL_ERROR';
    let message = shaped.message || '服务器内部错误';
    let details: unknown;

    if (error instanceof AppError) {
      statusCode = error.statusCode;
      code = error.code;
      message = error.message;
      details = error.details;
    } else if (hasZodFastifySchemaValidationErrors(error)) {
      statusCode = 400;
      code = 'VALIDATION_ERROR';
      message = '请求参数校验失败';
      details = error.validation;
    } else if (
      typeof shaped.statusCode === 'number' &&
      shaped.statusCode >= 400 &&
      shaped.statusCode < 500
    ) {
      statusCode = shaped.statusCode;
      code = typeof shaped.code === 'string' ? shaped.code : 'BAD_REQUEST';
      details = shaped.validation;
    }

    if (statusCode >= 500) request.log.error({ err: error, requestId }, message);
    else request.log.warn({ requestId, code }, message);

    return reply.code(statusCode).send(
      envelopeFail(requestId, {
        code,
        message,
        ...(details !== undefined ? { details } : {}),
      }),
    );
  });

  app.setNotFoundHandler((request, reply) =>
    reply.code(404).send(
      envelopeFail(request.requestId ?? 'unknown', {
        code: 'ROUTE_NOT_FOUND',
        message: `未找到路由 ${request.method} ${request.url}`,
      }),
    ),
  );

  await registerHealthRoutes(app);
  await registerLeadRoutes(app);
  await registerBookingRoutes(app);
  await registerAgentRoutes(app);

  return app;
}
