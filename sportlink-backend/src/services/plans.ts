import { prisma } from '../db/prisma';
import { toJson } from '../lib/json';
import { MEDICAL_DISCLAIMER, type CoachOutput, type Week } from '../schemas/llm';
import { ensureLead } from './leads';

export async function savePlan(leadId: string, plan: CoachOutput) {
  await ensureLead(leadId);
  const weeks: Week[] = plan.weeks.map((w, i) => ({ ...w, week: i + 1 }));

  const row = await prisma.trainingPlan.create({
    data: {
      leadId,
      age: plan.age,
      goal: plan.goal,
      experience: plan.experience,
      weeksJson: toJson(weeks),
      // Server-controlled: the LLM cannot override the safety disclaimer.
      disclaimer: MEDICAL_DISCLAIMER,
    },
  });

  return { ...row, weeks, disclaimer: MEDICAL_DISCLAIMER };
}
