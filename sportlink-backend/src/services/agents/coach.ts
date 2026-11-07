import { completeJSON } from '../../llm/complete';
import { COACH_SYSTEM_PROMPT } from '../../llm/prompts';
import { AppError } from '../../lib/errors';
import {
  CoachOutputSchema,
  MEDICAL_DISCLAIMER,
  type CoachOutput,
} from '../../schemas/llm';
import { ensureLead } from '../leads';
import { savePlan } from '../plans';
import { mockCoach } from './mock';

export async function runCoach(input: {
  leadId: string;
  childAge?: number;
  goal?: string;
  experience?: string;
}) {
  const lead = await ensureLead(input.leadId);
  const age = input.childAge ?? lead.childAge;
  const goal = input.goal ?? lead.goal;
  const experience = input.experience ?? '未提供（按零基础安排）';

  if (!age || !goal) {
    throw new AppError(
      422,
      'COACH_INSUFFICIENT_INFO',
      '生成课程方案需要儿童年龄和运动目标，请先用销售员工补全信息',
    );
  }

  const { data } = await completeJSON({
    system: COACH_SYSTEM_PROMPT,
    user: `儿童年龄：${age} 岁；运动目标：${goal}；运动基础：${experience}。请输出四周课程计划 JSON。`,
    schema: CoachOutputSchema,
    mockValue: () => mockCoach(age, goal, experience),
    repairHint: 'weeks 必须恰好 4 项，week 为 1..4，每项都要有 theme/warmup/mainTraining/game/cooldown/homework。',
  });

  // Server owns the safety wording, regardless of what the model returned.
  const plan: CoachOutput = { ...data, age, goal, experience, disclaimer: MEDICAL_DISCLAIMER };
  const stored = await savePlan(input.leadId, plan);
  return { planId: stored.id, plan };
}
