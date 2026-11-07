import { z } from 'zod';

export const LEAD_STATUSES = ['new', 'consulting', 'quoted', 'booked', 'closed'] as const;
export const LeadStatusSchema = z.enum(LEAD_STATUSES);

export const MESSAGE_ROLES = ['parent', 'assistant', 'system'] as const;
export const BOOKING_STATUSES = ['pending', 'confirmed', 'cancelled'] as const;
export const CHANNELS = ['wechat', 'sms', 'phone', 'in_app'] as const;

// ---------- Leads ----------
export const CreateLeadBody = z.object({
  parentName: z.string().min(1, '家长姓名不能为空').max(60),
  contact: z.string().min(1, '联系方式不能为空').max(120),
  childAge: z.number().int().min(1).max(18).optional(),
  goal: z.string().max(300).optional(),
  location: z.string().max(200).optional(),
  status: LeadStatusSchema.optional(),
});
export type CreateLeadInput = z.infer<typeof CreateLeadBody>;

export const LeadIdParams = z.object({ id: z.string().min(1) });

export const ListLeadsQuery = z.object({
  status: LeadStatusSchema.optional(),
  limit: z.coerce.number().int().min(1).max(100).default(50),
});

export const CreateMessageBody = z.object({
  content: z.string().min(1, '消息内容不能为空').max(4000),
  role: z.enum(MESSAGE_ROLES).default('parent'),
});

// ---------- AI employees ----------
export const SalesBody = z.object({
  leadId: z.string().min(1),
  message: z.string().min(1).max(4000),
});

export const CoachBody = z.object({
  leadId: z.string().min(1),
  childAge: z.number().int().min(1).max(18).optional(),
  goal: z.string().min(1).max(300).optional(),
  experience: z.string().max(300).optional(),
});

export const QuoteBody = z.object({
  leadId: z.string().min(1),
  message: z.string().min(1).max(4000).optional(),
  preferredSessions: z.number().int().min(1).max(20).optional(),
});

export const FollowupBody = z.object({
  leadId: z.string().min(1),
  channel: z.enum(CHANNELS).optional(),
});

export const RunBody = z.object({
  leadId: z.string().min(1),
  message: z.string().min(1).max(4000),
});

// ---------- Bookings ----------
export const CreateBookingBody = z.object({
  leadId: z.string().min(1),
  startAt: z.string().datetime({ offset: true, message: 'startAt 必须是 ISO 8601 时间' }),
  endAt: z.string().datetime({ offset: true, message: 'endAt 必须是 ISO 8601 时间' }),
  note: z.string().max(500).optional(),
});

export const BookingIdParams = z.object({ id: z.string().min(1) });

export const ListBookingsQuery = z.object({
  status: z.enum(BOOKING_STATUSES).optional(),
  leadId: z.string().optional(),
  limit: z.coerce.number().int().min(1).max(100).default(50),
});

// ---------- Unified response envelope (used for OpenAPI + serialization) ----------
export const ApiErrorSchema = z.object({
  code: z.string().describe('Machine readable error code'),
  message: z.string().describe('Human readable message'),
  details: z.any().optional().describe('Optional structured details'),
});

export const makeEnvelope = (data: z.ZodTypeAny) =>
  z.object({
    success: z.boolean().describe('true on success, false on error'),
    data: data.nullable().describe('Payload on success; null on error'),
    error: ApiErrorSchema.nullable().describe('Error body on failure; null on success'),
    requestId: z.string().describe('Unique id for this request (also x-request-id header)'),
  });

/** Loose data schema: keeps OpenAPI docs accurate without stripping payload keys. */
export const OkEnvelope = makeEnvelope(z.any());
