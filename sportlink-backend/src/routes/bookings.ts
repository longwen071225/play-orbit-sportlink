import type { FastifyInstance } from 'fastify';
import { ZodTypeProvider } from 'fastify-type-provider-zod';
import { sendOk } from '../lib/response';
import {
  BookingIdParams,
  CreateBookingBody,
  ListBookingsQuery,
  OkEnvelope,
} from '../schemas/api';
import * as bookings from '../services/bookings';

export async function registerBookingRoutes(app: FastifyInstance) {
  const r = app.withTypeProvider<ZodTypeProvider>();

  r.post(
    '/api/bookings',
    {
      schema: {
        tags: ['E. 预约管理'],
        summary: '创建待确认预约（检查时间冲突）',
        description: '预约始终以 pending 创建，重叠时段返回 409 BOOKING_CONFLICT',
        body: CreateBookingBody,
        response: { 201: OkEnvelope },
      },
    },
    async (request, reply) => {
      const booking = await bookings.createBooking(request.body);
      return sendOk(request, reply, booking, 201);
    },
  );

  r.get(
    '/api/bookings',
    {
      schema: {
        tags: ['E. 预约管理'],
        summary: '获取预约列表',
        querystring: ListBookingsQuery,
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) => sendOk(request, reply, await bookings.listBookings(request.query)),
  );

  r.patch(
    '/api/bookings/:id/confirm',
    {
      schema: {
        tags: ['E. 预约管理'],
        summary: '确认预约（唯一能把状态改为 confirmed 的入口）',
        description: '仅 pending -> confirmed；需人工/用户显式调用，AI 总控不会自动调用',
        params: BookingIdParams,
        response: { 200: OkEnvelope },
      },
    },
    async (request, reply) =>
      sendOk(request, reply, await bookings.confirmBooking(request.params.id)),
  );
}
