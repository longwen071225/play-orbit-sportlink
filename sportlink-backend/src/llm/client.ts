import OpenAI from 'openai';
import { env } from '../config/env';
import { AppError } from '../lib/errors';

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

/** Returns the raw text content of the model reply. Injectable for tests. */
export type CompletionFn = (messages: ChatMessage[]) => Promise<string>;

let cachedClient: OpenAI | null = null;

function getClient(): OpenAI {
  if (!env.DASHSCOPE_API_KEY.trim()) {
    throw new AppError(
      503,
      'LLM_NOT_CONFIGURED',
      '未配置 DASHSCOPE_API_KEY。请设置真实 Key，或设置 MOCK_AI=true 使用离线演示模式。',
    );
  }
  if (!cachedClient) {
    cachedClient = new OpenAI({
      apiKey: env.DASHSCOPE_API_KEY,
      baseURL: env.DASHSCOPE_BASE_URL,
      timeout: 30_000,
      maxRetries: 0,
    });
  }
  return cachedClient;
}

export const realCompletion: CompletionFn = async (messages) => {
  const client = getClient();
  const response = await client.chat.completions.create({
    model: env.DASHSCOPE_MODEL,
    messages,
    response_format: { type: 'json_object' },
    temperature: 0.2,
  });
  const text = response.choices?.[0]?.message?.content;
  if (!text) throw new AppError(502, 'LLM_EMPTY_RESPONSE', '模型返回了空内容');
  return text;
};
