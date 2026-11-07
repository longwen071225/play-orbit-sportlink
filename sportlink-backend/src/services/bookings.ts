import { prisma } from '../db/prisma';
import { AppError, badRequest, notFound } from '../lib/errors';
import { advanceLeadStatus, ensureLead } from './leads';

const ACTIVE_STATUSES = ['pending', 'confirmed'];

export async function createBooking(input: {
  leadId: string;
  startAt: string;
  endAt: string;
  note?: string;
}) {
  const start = new Date(input.startAt);
  const end = new Date(input.endAt);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    throw badRequest('startAt / endAt 不是合法时间');
  }
  if (end.getTime() <= start.getTime()) {
    throw badRequest('endAt 必须晚于 startAt');
  }

  await ensureLead(input.leadId);

  const conflicts = await prisma.booking.findMany({
    where: {
      status: { in: ACTIVE_STATUSES },
      startAt: { lt: end },
      endAt: { gt: start },
    },
    select: { id: true, startAt: true, endAt: true, status: true },
  });
  if (conflicts.length > 0) {
    throw new AppError(409, 'BOOKING_CONFLICT', '该时间段已有预约，请另选时间', { conflicts });
  }

  // Always created as pending. Only PATCH /confirm can promote it to confirmed.
  return prisma.booking.create({
    data: {
      leadId: input.leadId,
      startAt: start,
      endAt: end,
      note: input.note ?? null,
      status: 'pending',
    },
  });
}

export async function listBookings(query: { status?: string; leadId?: string; limit: number }) {
  return prisma.booking.findMany({
    where: {
      ...(query.status ? { status: query.status } : {}),
      ...(query.leadId ? { leadId: query.leadId } : {}),
    },
    orderBy: { startAt: 'asc' },
    take: query.limit,
    include: { lead: { select: { id: true, parentName: true, contact: true } } },
  });
}

export async function confirmBooking(id: string) {
  const booking = await prisma.booking.findUnique({ where: { id } });
  if (!booking) throw notFound('BOOKING_NOT_FOUND', `预约 ${id} 不存在`);
  if (booking.status === 'confirmed') {
    throw new AppError(409, 'INVALID_STATE_TRANSITION', '该预约已确认，无需重复操作');
  }
  if (booking.status !== 'pending') {
    throw new AppError(
      409,
      'INVALID_STATE_TRANSITION',
      `当前状态 ${booking.status} 不能变更为 confirmed`,
    );
  }

  // Re-check on confirmation: no other active booking may overlap.
  const conflicts = await prisma.booking.findMany({
    where: {
      id: { not: id },
      status: { in: ACTIVE_STATUSES },
      startAt: { lt: booking.endAt },
      endAt: { gt: booking.startAt },
    },
    select: { id: true },
  });
  if (conflicts.length > 0) {
    throw new AppError(409, 'BOOKING_CONFLICT', '确认失败：该时段与其他预约冲突', { conflicts });
  }

  const updated = await prisma.booking.update({
    where: { id },
    data: { status: 'confirmed' },
  });
  await advanceLeadStatus(booking.leadId, 'booked', ['new', 'consulting', 'quoted']);
  return updated;
}
