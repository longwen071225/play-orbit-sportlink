import { z } from 'zod';
import { env } from '../config/env';
import { AppError } from '../lib/errors';
import { realCompletion, type ChatMessage, type CompletionFn } from './client';

export interface CompleteOptions<T> {
  system: string;
  user: string;
  schema: z.ZodType<T>;
  /** Deterministic value used in mock mode (no API key required). */
  mockValue: T | ((user: string) => T);
  /** Overrides the transport; used by tests, bypasses mock mode. */
  completionFn?: CompletionFn;
  repairHint?: string;
}

export interface CompleteResult<T> {
  data: T;
  /** Number of model calls (0 in mock mode). */
  attempts: number;
  raw: string | null;
}

/** Pull a JSON object out of plain text, ```json fences, or surrounding prose. */
export function extractJson(text: string): unknown {
  let t = text.trim();
  const fence = t.match(/^```(?:json)?\s*([\s\S]*?)```$/i);
  if (fence) t = fence[1].trim();

  const start = t.indexOf('{');
  const end = t.lastIndexOf('}');
  if (start === -1 || end === -1 || end <= start) {
    throw new Error('输出中未找到 JSON 对象');
  }
  return JSON.parse(t.slice(start, end + 1));
}

/**
 * Calls the LLM, parses JSON, validates with Zod, and retries once with a
 * corrective message on any parse/validation failure.
 */
export async function completeJSON<T>(opts: CompleteOptions<T>): Promise<CompleteResult<T>> {
  // Mock mode: deterministic, offline, still Zod-validated.
  if (!opts.completionFn && env.mockAI) {
    const value =
      typeof opts.mockValue === 'function'
        ? (opts.mockValue as (user: string) => T)(opts.user)
        : opts.mockValue;
    const parsed = opts.schema.safeParse(value);
    if (!parsed.success) {
      throw new AppError(
        500,
        'MOCK_INVALID',
        'mock AI 输出未通过 Zod 校验',
        parsed.error.flatten().fieldErrors,
      );
    }
    return { data: parsed.data, attempts: 0, raw: null };
  }

  const fn: CompletionFn = opts.completionFn ?? realCompletion;
  const messages: ChatMessage[] = [
    { role: 'system', content: opts.system },
    { role: 'user', content: opts.user },
  ];
  let lastError = 'unknown';

  for (let attempt = 1; attempt <= 2; attempt += 1) {
    let raw: string;
    try {
      raw = await fn(messages);
    } catch (e) {
      lastError = e instanceof Error ? e.message : String(e);
      if (attempt === 2) {
        throw new AppError(502, 'LLM_REQUEST_FAILED', `模型调用失败: ${lastError}`);
      }
      continue;
    }

    try {
      const json = extractJson(raw);
      const parsed = opts.schema.safeParse(json);
      if (parsed.success) {
        return { data: parsed.data, attempts: attempt, raw };
      }
      lastError = JSON.stringify(parsed.error.flatten().fieldErrors);
      messages.push(
        { role: 'assistant', content: raw },
        {
          role: 'user',
          content: `上一次输出不是合法的业务 JSON。校验错误：${lastError}。${
            opts.repairHint ?? ''
          } 请只输出符合要求的 JSON 对象，不要包含解释文字或 Markdown 代码块。`,
        },
      );
    } catch (e) {
      lastError = e instanceof Error ? e.message : String(e);
      messages.push(
        { role: 'assistant', content: raw },
        {
          role: 'user',
          content: `上一次输出无法解析为 JSON：${lastError}。请只输出一个合法的 JSON 对象。`,
        },
      );
    }
  }

  throw new AppError(
    502,
    'LLM_INVALID_RESPONSE',
    '模型输出经一次重试后仍未通过 Zod 校验',
    { lastError },
  );
}
