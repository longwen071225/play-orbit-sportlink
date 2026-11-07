import { z } from 'zod';
import { describe, expect, it } from 'vitest';
import { completeJSON, extractJson } from '../src/llm/complete';
import { SalesOutputSchema } from '../src/schemas/llm';
import { mockSales } from '../src/services/agents/mock';

describe('AI JSON 解析', () => {
  it('解析 Markdown 代码块中的 JSON', () => {
    expect(extractJson('```json\n{"a":1}\n```')).toEqual({ a: 1 });
  });

  it('从解释文字中截取 JSON 对象', () => {
    expect(extractJson('好的，结果如下：{"a":2,"b":{"c":3}} 谢谢')).toEqual({
      a: 2,
      b: { c: 3 },
    });
  });

  it('没有 JSON 时抛出错误', () => {
    expect(() => extractJson('完全没有结构化输出')).toThrow();
  });
});

describe('LLM 响应 Zod 校验 + 失败重试一次', () => {
  const schema = z.object({ value: z.number(), label: z.string() });
  const base = { system: 'sys', user: 'usr', schema, mockValue: { value: 0, label: 'mock' } };

  it('第一次输出类型错误，追加修正消息后第二次通过', async () => {
    let calls = 0;
    const messagesSeen: number[] = [];
    const completionFn = async (messages: { role: string; content: string }[]) => {
      calls += 1;
      messagesSeen.push(messages.length);
      return calls === 1
        ? '```json\n{"value":"不是数字","label":"x"}\n```'
        : '{"value":42,"label":"ok"}';
    };

    const result = await completeJSON({ ...base, completionFn });
    expect(calls).toBe(2);
    expect(result.attempts).toBe(2);
    expect(result.data).toEqual({ value: 42, label: 'ok' });
    // Retry includes a corrective user message.
    expect(messagesSeen[1]).toBeGreaterThan(messagesSeen[0]);
  });

  it('两次都输出非 JSON 时抛出 LLM_INVALID_RESPONSE', async () => {
    let calls = 0;
    const completionFn = async () => {
      calls += 1;
      return '抱歉，我不会输出 JSON';
    };
    await expect(completeJSON({ ...base, completionFn })).rejects.toMatchObject({
      code: 'LLM_INVALID_RESPONSE',
    });
    expect(calls).toBe(2);
  });

  it('mock 模式直接返回确定性结果，不发起任何模型调用', async () => {
    const mockValue = mockSales('孩子8岁，想练跳绳，周末下午有空，零基础', {});
    const result = await completeJSON({
      system: 'sys',
      user: 'usr',
      schema: SalesOutputSchema,
      mockValue,
    });
    expect(result.attempts).toBe(0);
    expect(result.raw).toBeNull();
    expect(result.data.extractedFields.childAge).toBe(8);
    expect(result.data.missingFields).toEqual([]);
  });

  it('mock 输出不合法时同样被 Zod 拦截', async () => {
    await expect(
      completeJSON({ ...base, mockValue: { value: 'bad' } as never }),
    ).rejects.toMatchObject({ code: 'MOCK_INVALID' });
  });
});
