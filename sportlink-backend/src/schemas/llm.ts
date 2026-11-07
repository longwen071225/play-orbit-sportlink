import { z } from 'zod';

/** Required sales fields; the backend recomputes missingFields from these. */
export const REQUIRED_SALES_FIELDS = ['childAge', 'goal', 'availableTime'] as const;
export type RequiredSalesField = (typeof REQUIRED_SALES_FIELDS)[number];

export const ExtractedFieldsSchema = z.object({
  childAge: z.number().int().min(1).max(18).nullable(),
  goal: z.string().min(1).max(300).nullable(),
  experience: z.string().min(1).max(300).nullable(),
  availableTime: z.string().min(1).max(300).nullable(),
  location: z.string().min(1).max(200).nullable(),
});
export type ExtractedFields = z.infer<typeof ExtractedFieldsSchema>;

export const FIELD_LABELS: Record<RequiredSalesField, string> = {
  childAge: '孩子的年龄',
  goal: '想训练的运动目标',
  availableTime: '方便上课的时间',
};

export const SalesOutputSchema = z.object({
  extractedFields: ExtractedFieldsSchema,
  missingFields: z.array(z.string()),
  suggestedReply: z.string().min(1).max(1200),
  recommendedService: z.string().min(1).max(60),
});
export type SalesOutput = z.infer<typeof SalesOutputSchema>;

export const WeekSchema = z.object({
  week: z.number().int().min(1).max(4),
  theme: z.string().min(1),
  warmup: z.string().min(1),
  mainTraining: z.string().min(1),
  game: z.string().min(1),
  cooldown: z.string().min(1),
  homework: z.string().min(1),
});
export type Week = z.infer<typeof WeekSchema>;

export const CoachOutputSchema = z.object({
  age: z.number().int().min(1).max(18),
  goal: z.string().min(1),
  experience: z.string().min(1),
  weeks: z.array(WeekSchema).length(4),
  disclaimer: z.string().min(1),
});
export type CoachOutput = z.infer<typeof CoachOutputSchema>;

/** NOTE: deliberately contains NO price/amount fields. Amounts are computed server-side. */
export const QuoteOutputSchema = z.object({
  recommendedPackage: z.enum(['single', 'package4']),
  quantity: z.number().int().min(1).max(20),
  note: z.string().min(1).max(600),
  highlights: z.array(z.string()).min(1),
});
export type QuoteOutput = z.infer<typeof QuoteOutputSchema>;

export const FollowupOutputSchema = z.object({
  channel: z.enum(['wechat', 'sms', 'phone', 'in_app']),
  tone: z.string().min(1).max(60),
  subject: z.string().max(120),
  body: z.string().min(1).max(600),
  reason: z.string().min(1).max(300),
  doNotDisturb: z.boolean(),
});
export type FollowupOutput = z.infer<typeof FollowupOutputSchema>;

/** Server-controlled, never taken from the LLM. */
export const MEDICAL_DISCLAIMER =
  '本方案仅为一般儿童体育活动建议，不构成医疗诊断、康复治疗或任何医学判断；如孩子有伤病或特殊健康状况，请咨询专业医生。';
