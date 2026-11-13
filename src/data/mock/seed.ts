import type { Job, Message, UserRole } from '@/domain/models';

/**
 * 本地 mock 种子：仅保留后端暂未提供的「竞赛通知」与「站内聊天」。
 * 其余（招聘/申请/通知）已切到后端，不再走本地数据。
 */

const NOW = Date.now();
const DAY = 86_400_000;
const HOUR = 3_600_000;

function days(n: number): string {
  return new Date(NOW + n * DAY).toISOString();
}
function hoursAgo(n: number): string {
  return new Date(NOW - n * HOUR).toISOString();
}

export interface DemoUser {
  id: string;
  name: string;
  role: UserRole;
}

export interface ConversationRow {
  id: string;
  participantIds: [string, string];
  updatedAt: string;
}

export interface LocalSeed {
  notices: Job[];
  demoUsers: DemoUser[];
  conversations: ConversationRow[];
  messages: Message[];
}

export function buildSeed(): LocalSeed {
  const demoUsers: DemoUser[] = [
    { id: '20230001', name: '张同学', role: 'student' },
    { id: '20230002', name: '李同学', role: 'student' },
    { id: '20230003', name: '赵同学', role: 'student' },
    { id: 'T2024001', name: '王老师', role: 'teacher' },
    { id: 'T2024002', name: '刘老师', role: 'teacher' },
  ];

  const teacher = (id: string): Job['publisher'] => {
    const u = demoUsers.find((x) => x.id === id)!;
    return { id, name: u.name, role: u.role };
  };

  // 竞赛通知（后端未提供该类型，保留本地 mock）
  const notices: Job[] = [
    {
      id: 'notice-1',
      type: 'competition_notice',
      title: '全国大学生程序设计竞赛报名通知',
      description:
        '2026 年全国大学生程序设计竞赛校内选拔报名现已开启，请有意参赛的同学在规定时间内完成组队与报名，具体赛程与培训安排将另行通知。',
      tags: [{ id: 1, name: '计算机' }],
      minHeadcount: null,
      maxHeadcount: 0,
      acceptedCount: 0,
      deadline: days(14),
      status: 'open',
      isDeleted: false,
      publisher: teacher('T2024001'),
      createdAt: hoursAgo(8),
      updatedAt: hoursAgo(8),
      applicationCount: 0,
    },
    {
      id: 'notice-2',
      type: 'competition_notice',
      title: '大学生创新创业大赛宣讲会通知',
      description:
        '大学生创新创业大赛校内宣讲会将于近期举办，面向全校师生介绍赛道设置、参赛流程与时间安排，欢迎到场了解。',
      tags: [{ id: 8, name: '设计创意' }],
      minHeadcount: null,
      maxHeadcount: 0,
      acceptedCount: 0,
      deadline: days(2),
      status: 'open',
      isDeleted: false,
      publisher: teacher('T2024002'),
      createdAt: hoursAgo(12),
      updatedAt: hoursAgo(12),
      applicationCount: 0,
    },
  ];

  // 站内聊天（保留本地 mock；后端上线后接入 MessageRepository 的 http 实现）
  const conversations: ConversationRow[] = [
    { id: 'conv-1', participantIds: ['20230002', '20230001'], updatedAt: hoursAgo(19) },
    { id: 'conv-2', participantIds: ['20230002', 'T2024002'], updatedAt: hoursAgo(11) },
  ];

  const msg = (id: string, conversationId: string, senderId: string, text: string, h: number): Message => ({
    id,
    conversationId,
    senderId,
    text,
    createdAt: hoursAgo(h),
  });

  const messages: Message[] = [
    msg('m-1', 'conv-1', '20230001', '你好，请问组队还在招人吗？', 22),
    msg('m-2', 'conv-1', '20230002', '在的，还缺一名开发队员。', 21),
    msg('m-3', 'conv-2', '20230002', '老师好，想咨询一下作品集要求。', 12),
    msg('m-4', 'conv-2', 'T2024002', '作品集不限形式，能体现能力即可。', 11),
  ];

  return { notices, demoUsers, conversations, messages };
}
