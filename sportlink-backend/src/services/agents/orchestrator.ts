import { prisma } from '../../db/prisma';
import { toJson } from '../../lib/json';
import type { SalesOutput } from '../../schemas/llm';
import { ensureLead } from '../leads';
import { runCoach } from './coach';
import { runFollowup } from './followup';
import { runQuote } from './quote';
import { runSales } from './sales';

export type StepStatus = 'success' | 'failed' | 'skipped' | 'awaiting_confirmation';

export interface StepReport<T = unknown> {
  step: string;
  name: string;
  status: StepStatus;
  durationMs: number;
  result: T | null;
  log: string;
}

async function persistAction(
  runId: string,
  step: string,
  name: string,
  status: StepStatus,
  durationMs: number,
  input: unknown,
  output: unknown,
  log: string,
) {
  await prisma.agentAction.create({
    data: {
      runId,
      step,
      name,
      status,
      durationMs,
      inputJson: toJson(input),
      outputJson: toJson(output),
      log,
    },
  });
}

async function runStep<T>(
  runId: string,
  step: string,
  name: string,
  input: unknown,
  fn: () => Promise<T>,
): Promise<StepReport<T>> {
  const started = Date.now();
  try {
    const result = await fn();
    const durationMs = Date.now() - started;
    const log = `${name} 执行成功（${durationMs}ms），结果已写入数据库`;
    await persistAction(runId, step, name, 'success', durationMs, input, result, log);
    return { step, name, status: 'success', durationMs, result, log };
  } catch (e) {
    const durationMs = Date.now() - started;
    const message = e instanceof Error ? e.message : String(e);
    const log = `${name} 执行失败（${durationMs}ms）：${message}`;
    await persistAction(runId, step, name, 'failed', durationMs, input, { error: message }, log);
    return { step, name, status: 'failed', durationMs, result: null, log };
  }
}

function staticStep<T>(
  step: string,
  name: string,
  status: StepStatus,
  result: T,
  log: string,
): StepReport<T> {
  return { step, name, status, durationMs: 0, result, log };
}

/**
 * Real orchestration: each step calls the corresponding business service, which
 * persists its own rows. Booking and external sending stop at a human gate.
 */
export async function runOrchestrator(input: { leadId: string; message: string }) {
  await ensureLead(input.leadId);
  const started = Date.now();
  const run = await prisma.agentRun.create({
    data: {
      leadId: input.leadId,
      inputMessage: input.message,
      status: 'running',
      summary: '编排进行中',
      durationMs: 0,
    },
  });

  const steps: StepReport[] = [];
  let status = 'completed';
  let summary = '';
  let nextStep: {
    action: string;
    description: string;
    requiresHumanConfirmation: boolean;
    suggestedReply?: string;
  };

  // Step 1: identify needs / ask for missing info (real sales service, persists).
  const salesStep = await runStep(
    run.id,
    'sales',
    '识别需求 / 补全信息',
    { leadId: input.leadId, message: input.message },
    () => runSales(input),
  );
  steps.push(salesStep);

  if (salesStep.status === 'failed' || salesStep.result == null) {
    status = 'failed';
    summary = '需求识别失败，后续步骤已停止';
    nextStep = {
      action: 'retry_sales',
      description: '请检查模型配置或稍后重试 /api/agent/run',
      requiresHumanConfirmation: false,
    };
  } else {
    const extraction: SalesOutput = salesStep.result.extraction;
    const missing = extraction.missingFields;

    if (missing.length > 0) {
      status = 'needs_input';
      summary = `已识别需求，但缺少 ${missing.join('、')}；已生成追问话术，等待家长补充后再生成课程与报价。`;
      nextStep = {
        action: 'ask_parent',
        description: summary,
        requiresHumanConfirmation: false,
        suggestedReply: extraction.suggestedReply,
      };
      for (const [step, name] of [
        ['coach', '生成四周课程方案'],
        ['quote', '生成报价'],
      ] as const) {
        const report = staticStep(
          step,
          name,
          'skipped',
          { reason: missing },
          `${name} 已跳过：缺少关键信息（${missing.join('、')}），按规则先向家长询问`,
        );
        steps.push(report);
        await persistAction(run.id, step, name, 'skipped', 0, { missing }, report.result, report.log);
      }
    } else {
      const ef = extraction.extractedFields;
      const coachStep = await runStep(
        run.id,
        'coach',
        '生成四周课程方案',
        { leadId: input.leadId, childAge: ef.childAge, goal: ef.goal, experience: ef.experience },
        () =>
          runCoach({
            leadId: input.leadId,
            childAge: ef.childAge ?? undefined,
            goal: ef.goal ?? undefined,
            experience: ef.experience ?? undefined,
          }),
      );
      steps.push(coachStep);

      const quoteStep = await runStep(
        run.id,
        'quote',
        '生成报价',
        { leadId: input.leadId, message: input.message },
        () => runQuote({ leadId: input.leadId, message: input.message }),
      );
      steps.push(quoteStep);

      if (coachStep.status === 'failed' || quoteStep.status === 'failed') {
        status = 'failed';
        summary = '课程方案或报价步骤失败，请查看执行日志';
        nextStep = {
          action: 'retry_run',
          description: '请查看各步骤执行日志后重试 /api/agent/run',
          requiresHumanConfirmation: false,
        };
      } else {
        summary = '已完成需求识别、四周课程方案与报价；下一步请家长确认预约时间。';
        nextStep = {
          action: 'confirm_booking',
          description:
            '请与家长确认上门训练的具体时间，然后显式调用 POST /api/bookings 创建待确认预约，再由用户 PATCH 确认；系统不会自动创建预约或发送消息。',
          requiresHumanConfirmation: true,
        };
      }
    }

    const followupStep = await runStep(
      run.id,
      'followup',
      '生成跟进话术草稿',
      { leadId: input.leadId },
      () => runFollowup({ leadId: input.leadId }),
    );
    steps.push(followupStep);
  }

  // Human gate 1: booking. No Booking row is ever created here.
  const bookingOutput = {
    requiresHumanConfirmation: true,
    proposedBooking: {
      leadId: input.leadId,
      status: 'pending',
      note: '请家长确认具体上课时间后，显式调用 POST /api/bookings 创建待确认预约',
    },
    message: '预约动作已挂起，等待人工确认',
  };
  const bookingStep = staticStep(
    'booking',
    '创建预约（等待人工确认）',
    'awaiting_confirmation',
    bookingOutput,
    '未创建任何 Booking 记录；必须由家长确认时间并显式调用 POST /api/bookings',
  );
  steps.push(bookingStep);
  await persistAction(
    run.id,
    'booking',
    '创建预约（等待人工确认）',
    'awaiting_confirmation',
    0,
    { leadId: input.leadId },
    bookingOutput,
    bookingStep.log,
  );

  // Human gate 2: external sending. Drafts only, nothing is sent.
  const sendOutput = {
    requiresHumanConfirmation: true,
    message: '外部发送（短信/微信/电话）动作已挂起；系统仅生成草稿，不自动发送',
  };
  const sendStep = staticStep(
    'external_send',
    '外部发送（等待人工确认）',
    'awaiting_confirmation',
    sendOutput,
    '未调用任何发送渠道；跟进话术仅作为草稿保存到 Message 表',
  );
  steps.push(sendStep);
  await persistAction(
    run.id,
    'external_send',
    '外部发送（等待人工确认）',
    'awaiting_confirmation',
    0,
    { leadId: input.leadId },
    sendOutput,
    sendStep.log,
  );

  const durationMs = Date.now() - started;
  await prisma.agentRun.update({
    where: { id: run.id },
    data: { status, summary, durationMs },
  });

  return { runId: run.id, leadId: input.leadId, status, summary, nextStep, durationMs, steps };
}
