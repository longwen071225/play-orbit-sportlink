import 'dotenv/config';
import { z } from 'zod';

const EnvSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  HOST: z.string().default('0.0.0.0'),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  LOG_LEVEL: z.string().default('info'),
  CORS_ORIGIN: z.string().default('*'),
  DATABASE_URL: z.string().default('file:./dev.db'),
  DASHSCOPE_BASE_URL: z.string().default('https://dashscope.aliyuncs.com/compatible-mode/v1'),
  DASHSCOPE_API_KEY: z.string().default(''),
  DASHSCOPE_MODEL: z.string().default('qwen-plus'),
  MOCK_AI: z.enum(['auto', 'true', 'false']).default('auto'),
  PRICE_SINGLE_CENTS: z.coerce.number().int().nonnegative().default(12900),
  PRICE_PACKAGE_4_CENTS: z.coerce.number().int().nonnegative().default(49900),
  PACKAGE_SESSIONS: z.coerce.number().int().positive().default(4),
});

const parsed = EnvSchema.safeParse(process.env);
if (!parsed.success) {
  // eslint-disable-next-line no-console
  console.error('[config] invalid environment:', parsed.error.flatten().fieldErrors);
  throw new Error('Invalid environment configuration');
}

const raw = parsed.data;

const mockAI =
  raw.MOCK_AI === 'true' || (raw.MOCK_AI === 'auto' && raw.DASHSCOPE_API_KEY.trim() === '');

export const env = {
  ...raw,
  mockAI,
  isTest: raw.NODE_ENV === 'test',
};

export type Env = typeof env;
