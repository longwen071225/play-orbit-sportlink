import 'dotenv/config';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

const MEDICAL_DISCLAIMER =
  '本方案仅为一般儿童体育活动建议，不构成医疗诊断、康复治疗或任何医学判断；如孩子有伤病或特殊健康状况，请咨询专业医生。';

const singleCents = Number(process.env.PRICE_SINGLE_CENTS ?? 12900);
const package4Cents = Number(process.env.PRICE_PACKAGE_4_CENTS ?? 49900);

function week(n: number, theme: string, goal: string) {
  return {
    week: n,
    theme: `第 ${n} 周：${theme}（${goal}）`,
    warmup: '5-8 分钟动态拉伸、关节激活与轻松追逐跑',
    mainTraining: `围绕「${goal}」的基础动作分解练习，每组 8-10 次、共 3 组`,
    game: '趣味接力或标志桶游戏，控制对抗强度',
    cooldown: '5 分钟慢走 + 静态拉伸 + 呼吸放松',
    homework: `每天约 10 分钟亲子练习：${goal} 相关基础动作`,
  };
}

async function main() {
  // Idempotent demo reset (children first).
  await prisma.agentAction.deleteMany();
  await prisma.agentRun.deleteMany();
  await prisma.quoteItem.deleteMany();
  await prisma.quote.deleteMany();
  await prisma.booking.deleteMany();
  await prisma.trainingPlan.deleteMany();
  await prisma.message.deleteMany();
  await prisma.lead.deleteMany();

  const lin = await prisma.lead.create({
    data: {
      parentName: '林女士（虚构演示数据）',
      contact: 'demo-wechat-001',
      childAge: 8,
      goal: '跳绳与体能',
      location: '福州市鼓楼区（虚构）',
      status: 'quoted',
    },
  });
  const chen = await prisma.lead.create({
    data: {
      parentName: '陈先生（虚构演示数据）',
      contact: 'demo-wechat-002',
      childAge: 10,
      goal: '篮球基础',
      location: '福州市仓山区（虚构）',
      status: 'booked',
    },
  });
  const wang = await prisma.lead.create({
    data: {
      parentName: '王女士（虚构演示数据）',
      contact: 'demo-wechat-003',
      childAge: 7,
      goal: '协调性与平衡',
      location: '福州市台江区（虚构）',
      status: 'new',
    },
  });

  await prisma.message.createMany({
    data: [
      { leadId: lin.id, role: 'parent', content: '你好，孩子8岁，想提升跳绳，周末下午有空' },
      { leadId: lin.id, role: 'assistant', content: '已了解，稍后给您一份四周课程方案和报价。' },
      { leadId: chen.id, role: 'parent', content: '想给孩子约篮球上门体验课' },
      { leadId: wang.id, role: 'parent', content: '想咨询一下儿童体能训练' },
    ],
  });

  await prisma.trainingPlan.create({
    data: {
      leadId: lin.id,
      age: 8,
      goal: '跳绳与体能',
      experience: '零基础',
      weeksJson: JSON.stringify([
        week(1, '基础动作与兴趣建立', '跳绳与体能'),
        week(2, '协调与平衡进阶', '跳绳与体能'),
        week(3, '目标技能专项练习', '跳绳与体能'),
        week(4, '综合巩固与成果展示', '跳绳与体能'),
      ]),
      disclaimer: MEDICAL_DISCLAIMER,
    },
  });

  await prisma.quote.create({
    data: {
      leadId: lin.id,
      currency: 'CNY',
      totalCents: package4Cents,
      note: '演示报价：四节套餐，金额由后端价目表确定性计算。',
      items: {
        create: [
          {
            name: '四节套餐',
            quantity: 1,
            unitPriceCents: package4Cents,
            amountCents: package4Cents,
          },
        ],
      },
    },
  });

  await prisma.quote.create({
    data: {
      leadId: chen.id,
      currency: 'CNY',
      totalCents: singleCents * 2,
      note: '演示报价：两节单节课。',
      items: {
        create: [
          {
            name: '单节课',
            quantity: 2,
            unitPriceCents: singleCents,
            amountCents: singleCents * 2,
          },
        ],
      },
    },
  });

  await prisma.booking.create({
    data: {
      leadId: chen.id,
      startAt: new Date('2026-12-05T15:00:00+08:00'),
      endAt: new Date('2026-12-05T16:00:00+08:00'),
      status: 'pending',
      note: '演示待确认预约（虚构）',
    },
  });

  const run = await prisma.agentRun.create({
    data: {
      leadId: lin.id,
      inputMessage: '孩子8岁，想提升跳绳，周末下午有空',
      status: 'completed',
      summary: '演示编排记录：需求识别 -> 课程方案 -> 报价；预约等待人工确认。',
      durationMs: 120,
    },
  });
  await prisma.agentAction.createMany({
    data: [
      {
        runId: run.id,
        step: 'sales',
        name: '识别需求 / 补全信息',
        status: 'success',
        durationMs: 20,
        inputJson: JSON.stringify({ leadId: lin.id }),
        outputJson: JSON.stringify({ missingFields: [] }),
        log: '演示：需求识别成功',
      },
      {
        runId: run.id,
        step: 'coach',
        name: '生成四周课程方案',
        status: 'success',
        durationMs: 40,
        inputJson: JSON.stringify({ age: 8, goal: '跳绳与体能' }),
        outputJson: JSON.stringify({ planId: 'demo' }),
        log: '演示：课程方案已入库',
      },
      {
        runId: run.id,
        step: 'booking',
        name: '创建预约（等待人工确认）',
        status: 'awaiting_confirmation',
        durationMs: 0,
        inputJson: JSON.stringify({ leadId: lin.id }),
        outputJson: JSON.stringify({ requiresHumanConfirmation: true }),
        log: '演示：未创建 Booking，等待人工确认',
      },
    ],
  });

  // eslint-disable-next-line no-console
  console.log(
    `Seed 完成：3 个虚构客户 (${lin.id}, ${chen.id}, ${wang.id})、课程方案、报价、待确认预约、编排日志`,
  );
}

main()
  .catch((e) => {
    // eslint-disable-next-line no-console
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
