import { randomUUID } from 'node:crypto';
import type { FastifyReply, FastifyRequest } from 'fastify';

declare module 'fastify' {
  interface FastifyRequest {
    /** Generated per request in the onRequest hook. */
    requestId: string;
  }
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: ApiErrorBody | null;
  requestId: string;
}

export function envelopeOk<T>(requestId: string, data: T): ApiEnvelope<T> {
  return { success: true, data, error: null, requestId };
}

export function envelopeFail(requestId: string, error: ApiErrorBody): ApiEnvelope<null> {
  return { success: false, data: null, error, requestId };
}

export function sendOk<T>(request: FastifyRequest, reply: FastifyReply, data: T, statusCode = 200) {
  return reply.code(statusCode).send(envelopeOk(request.requestId ?? 'unknown', data));
}

export function sendFail(
  request: FastifyRequest,
  reply: FastifyReply,
  statusCode: number,
  error: ApiErrorBody,
) {
  return reply.code(statusCode).send(envelopeFail(request.requestId ?? 'unknown', error));
}

export function newRequestId(): string {
  return randomUUID();
}
