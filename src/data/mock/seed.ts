import type { Application, AuditLog, Job, Message, Notification, ResumeFile, User } from '@/domain/models';

/** Mock 种子数据。时间戳相对「首次生成时刻」，刷新后 localStorage 持久化不丢。 */

const NOW = Date.now();
const DAY = 86_400_000;
const HOUR = 3_600_000;

function days(n: number): string {
  return new Date(NOW + n * DAY).toISOString();
}
function hoursAgo(n: number): string {
  return new Date(NOW - n * HOUR).toISOString();
}

/** 会话的库内表示：参与者是「绝对」的，peer 由当前登录人推导（见 mock/repository） */
export interface ConversationRow {
  id: string;
  participantIds: [string, string];
  updatedAt: string;
}

export interface SeedData {
  users: User[];
  jobs: Job[];
  applications: Application[];
  notifications: Notification[];
  auditLogs: AuditLog[];
  conversations: ConversationRow[];
  messages: Message[];
}

export function buildSeed(): SeedData {
  const users: User[] = [
    { id: '20230001', name: '张同学', email: 'zhang@tongji.edu.cn', role: 'student', isAdmin: true, college: '计算机学院', major: '软件工程' },
    { id: '20230002', name: '李同学', email: 'li@tongji.edu.cn', role: 'student', isAdmin: false, college: '计算机学院', major: '人工智能' },
    { id: '20230003', name: '赵同学', email: 'zhao@tongji.edu.cn', role: 'student', isAdmin: false, college: '设计创意学院', major: '视觉传达设计' },
    { id: '20230004', name: '陈同学', email: 'chen@tongji.edu.cn', role: 'student', isAdmin: false, college: '机械与能源工程学院', major: '机械设计制造及其自动化' },
    { id: 'T2024001', name: '王老师', email: 'wang@tongji.edu.cn', role: 'teacher', isAdmin: false, college: '计算机科学与技术学院', major: '' },
    { id: 'T2024002', name: '刘老师', email: 'liu@tongji.edu.cn', role: 'teacher', isAdmin: false, college: '设计创意学院', major: '' },
  ];

  const u = (id: string) => users.find((x) => x.id === id)!;
  const pub = (id: string): Job['publisher'] => ({ id, name: u(id).name, role: u(id).role });

  const jobs: Job[] = [
    {
      id: 'job-1', type: 'competition', field: '计算机',
      title: '智能机器人创新竞赛组队',
      description: '面向全国大学生智能机器人竞赛，招募具备编程、机械设计或项目管理经验的队员，要求每周可投入固定时间参与讨论与开发，有竞赛经历者优先。',
      requirement: '需提供简历，说明编程语言与相关项目经历。',
      recruitCount: 6, acceptedCount: 0, deadline: days(5), status: 'open',
      publisher: pub('20230002'), createdAt: hoursAgo(20), updatedAt: hoursAgo(20), applicationCount: 0,
    },
    {
      id: 'job-2', type: 'competition', field: '计算机',
      title: '算法挑战赛前端开发组队',
      description: '参加校级算法挑战赛，现招募前端开发队员，负责可视化展示与交互界面实现，熟悉 React 或 Vue 优先。',
      requirement: '有 Web 前端作品或项目经验者优先。',
      recruitCount: 5, acceptedCount: 0, deadline: days(7), status: 'open',
      publisher: pub('20230001'), createdAt: hoursAgo(18), updatedAt: hoursAgo(18), applicationCount: 0,
    },
    {
      id: 'job-3', type: 'competition', field: '计算机',
      title: '大数据分析竞赛组队',
      description: '面向大数据分析竞赛，招募擅长数据清洗、特征工程与建模的同学，共同完成竞赛题目。',
      requirement: '熟悉 Python / Pandas / 机器学习者优先。',
      recruitCount: 4, acceptedCount: 0, deadline: days(9), status: 'open',
      publisher: pub('20230003'), createdAt: hoursAgo(30), updatedAt: hoursAgo(30), applicationCount: 0,
    },
    {
      id: 'job-4', type: 'competition', field: '工程',
      title: '机械创新设计竞赛组队',
      description: '参与机械创新设计竞赛，招募机械结构设计、三维建模方向的队员，共同完成创新作品。',
      requirement: '熟悉 SolidWorks / CAD 建模，有动手实践能力。',
      recruitCount: 4, acceptedCount: 0, deadline: days(12), status: 'open',
      publisher: pub('20230004'), createdAt: hoursAgo(40), updatedAt: hoursAgo(40), applicationCount: 0,
    },
    {
      id: 'job-5', type: 'competition', field: '商学',
      title: '挑战杯参赛组队',
      description: '参与挑战杯竞赛，完成产品设计与商业计划书，招募市场调研、商业模式方向队员。',
      requirement: '有商业计划书或创业比赛经历者优先。',
      recruitCount: 4, acceptedCount: 0, deadline: days(20), status: 'open',
      publisher: pub('20230001'), createdAt: hoursAgo(50), updatedAt: hoursAgo(50), applicationCount: 0,
    },
    {
      id: 'job-6', type: 'competition', field: '工程',
      title: '大创项目组队',
      description: '招募机械与软件方向队员，完成创新创业训练计划项目，方向为智能硬件原型开发。',
      requirement: '对嵌入式或硬件开发有兴趣，可投入课余时间。',
      recruitCount: 6, acceptedCount: 0, deadline: days(30), status: 'open',
      publisher: pub('20230002'), createdAt: hoursAgo(60), updatedAt: hoursAgo(60), applicationCount: 0,
    },
    {
      id: 'job-7', type: 'competition', field: '计算机',
      title: '数学建模竞赛组队',
      description: '备战全国大学生数学建模竞赛，招募擅长数学建模、编程求解与论文写作的队员。',
      requirement: '有数学建模或论文写作经验者优先。',
      recruitCount: 3, acceptedCount: 0, deadline: days(3), status: 'open',
      publisher: pub('20230004'), createdAt: hoursAgo(70), updatedAt: hoursAgo(70), applicationCount: 0,
    },
    {
      id: 'job-8', type: 'competition', field: '电气',
      title: '电子设计竞赛组队',
      description: '参与电子设计竞赛，招募电路设计与嵌入式开发方向队员，共同完成竞赛作品。',
      requirement: '熟悉单片机或 FPGA 开发。',
      recruitCount: 4, acceptedCount: 0, deadline: days(2), status: 'closed',
      publisher: pub('20230004'), createdAt: hoursAgo(80), updatedAt: hoursAgo(20), applicationCount: 0,
    },
    {
      id: 'job-9', type: 'campus_activity', field: '设创',
      title: '校园文创设计助手招募',
      description: '校内文创项目招募设计助手，负责文创产品视觉设计、海报与周边制作。',
      requirement: '熟练使用 PS / AI，有设计作品集者优先。',
      recruitCount: 3, acceptedCount: 0, deadline: days(3), status: 'open',
      publisher: pub('T2024002'), createdAt: hoursAgo(16), updatedAt: hoursAgo(16), applicationCount: 0,
    },
    {
      id: 'job-10', type: 'campus_activity', field: '设创',
      title: '学生科创活动视觉设计招聘',
      description: '学生科创活动招募视觉设计同学，负责活动主视觉、展板与宣传物料设计。',
      requirement: '有校园活动设计经验者优先。',
      recruitCount: 4, acceptedCount: 0, deadline: days(6), status: 'open',
      publisher: pub('T2024002'), createdAt: hoursAgo(26), updatedAt: hoursAgo(26), applicationCount: 0,
    },
    {
      id: 'job-11', type: 'campus_activity', field: '商学',
      title: '创业训练营项目助理招聘',
      description: '创业训练营招募项目助理，协助活动组织、材料整理与项目对接。',
      requirement: '沟通能力强，可投入固定时间。',
      recruitCount: 8, acceptedCount: 0, deadline: days(10), status: 'open',
      publisher: pub('T2024001'), createdAt: hoursAgo(36), updatedAt: hoursAgo(36), applicationCount: 0,
    },
    {
      id: 'job-12', type: 'campus_activity', field: '设创',
      title: '校园科技节宣传组招聘',
      description: '校园科技节招募宣传组同学，负责活动宣传策划与现场执行。',
      requirement: '有新媒体运营或活动组织经验者优先。',
      recruitCount: 5, acceptedCount: 0, deadline: days(-1), status: 'closed',
      publisher: pub('T2024002'), createdAt: hoursAgo(100), updatedAt: hoursAgo(40), applicationCount: 0,
    },
  ];

  const resume = (id: string, owner: string): ResumeFile => ({
    id: `resume-${id}`,
    fileName: `简历_${owner}.pdf`,
    size: 2_048_000,
    mimeType: 'application/pdf',
    uploadedAt: hoursAgo(1),
    downloadUrl: `mock://resume/${id}`,
  });

  const app = (
    id: string,
    jobId: string,
    applicantId: string,
    status: Application['status'],
    note: string,
    daysAgo: number,
  ): Application => {
    const job = jobs.find((j) => j.id === jobId)!;
    const a = u(applicantId);
    return {
      id,
      jobId,
      jobTitle: job.title,
      jobType: job.type,
      applicant: { id: a.id, name: a.name, role: a.role },
      resume: resume(id, a.name),
      note,
      status,
      createdAt: hoursAgo(daysAgo * 24),
      updatedAt: hoursAgo(daysAgo * 24 - 2),
      resumeHidden: status === 'withdrawn',
    };
  };

  const applications: Application[] = [
    app('app-1', 'job-1', '20230001', 'accepted', '有三年 Python 开发经验，参加过机器人大赛。', 3),
    app('app-2', 'job-1', '20230003', 'pending', '擅长前端与交互设计，希望加入。', 2),
    app('app-3', 'job-1', '20230004', 'pending', '机械方向，有 SolidWorks 建模经验。', 1),
    app('app-4', 'job-2', '20230002', 'accepted', '熟悉 React 与 TypeScript。', 4),
    app('app-5', 'job-2', '20230003', 'accepted', '有可视化作品集。', 3),
    app('app-6', 'job-2', '20230004', 'pending', '想学习前端，有一定基础。', 1),
    app('app-7', 'job-3', '20230002', 'pending', '做过数据分析项目。', 2),
    app('app-8', 'job-3', '20230001', 'rejected', '对数据建模感兴趣。', 5),
    app('app-9', 'job-3', '20230004', 'pending', '熟悉 Pandas。', 1),
    app('app-10', 'job-4', '20230001', 'pending', '了解机械结构。', 2),
    app('app-11', 'job-4', '20230002', 'pending', '有硬件开发经验。', 1),
    app('app-12', 'job-5', '20230003', 'accepted', '做过市场调研。', 4),
    app('app-13', 'job-5', '20230002', 'accepted', '写过商业计划书。', 3),
    app('app-14', 'job-6', '20230004', 'accepted', '嵌入式开发方向。', 6),
    app('app-15', 'job-6', '20230001', 'accepted', '负责软件部分。', 5),
    app('app-16', 'job-6', '20230003', 'accepted', '负责交互设计。', 5),
    app('app-17', 'job-7', '20230001', 'accepted', '负责建模求解。', 2),
    app('app-18', 'job-7', '20230002', 'accepted', '负责编程。', 2),
    app('app-19', 'job-7', '20230003', 'accepted', '负责论文写作。', 1),
    app('app-20', 'job-9', '20230002', 'pending', '有平面设计经验。', 2),
    app('app-21', 'job-9', '20230001', 'accepted', '有校园海报设计作品。', 2),
    app('app-22', 'job-9', '20230003', 'pending', '视觉传达专业。', 1),
    app('app-23', 'job-11', '20230002', 'withdrawn', '已找到其他安排。', 4),
    app('app-24', 'job-11', '20230001', 'accepted', '有活动组织经验。', 3),
    app('app-25', 'job-10', '20230004', 'rejected', '想做宣传设计。', 3),
    app('app-26', 'job-12', '20230002', 'withdrawn', '', 6),
    app('app-27', 'job-8', '20230001', 'withdrawn', '', 7),
    app('app-28', 'job-10', '20230002', 'rejected', '尝试参与。', 2),
  ];

  const notifications: Notification[] = [
    { id: 'n-1', type: 'application_accepted', title: '你申请的「智能机器人创新竞赛组队」已被发布者接受。', body: '', jobId: 'job-1', jobTitle: '智能机器人创新竞赛组队', recipientId: '20230001', createdAt: hoursAgo(5), read: false },
    { id: 'n-2', type: 'application_rejected', title: '你申请的「大数据分析竞赛组队」未通过发布者筛选。', body: '', jobId: 'job-3', jobTitle: '大数据分析竞赛组队', recipientId: '20230001', createdAt: hoursAgo(20), read: false },
    { id: 'n-3', type: 'job_modified', title: '发布者修改了「校园文创设计助手招募」的截止时间与招募人数。', body: '', jobId: 'job-9', jobTitle: '校园文创设计助手招募', recipientId: '20230001', createdAt: hoursAgo(30), read: true },
    { id: 'n-4', type: 'job_removed_by_admin', title: '「创业训练营项目助理招聘」已被管理员删除。', body: '', jobId: 'job-11', jobTitle: '创业训练营项目助理招聘', recipientId: '20230001', createdAt: hoursAgo(50), read: true },
    { id: 'n-5', type: 'application_accepted', title: '你申请的「算法挑战赛前端开发组队」已被发布者接受。', body: '', jobId: 'job-2', jobTitle: '算法挑战赛前端开发组队', recipientId: '20230002', createdAt: hoursAgo(8), read: false },
    { id: 'n-6', type: 'application_rejected', title: '你申请的「学生科创活动视觉设计招聘」未通过发布者筛选。', body: '', jobId: 'job-10', jobTitle: '学生科创活动视觉设计招聘', recipientId: '20230002', createdAt: hoursAgo(26), read: false },
    { id: 'n-7', type: 'application_withdrawn', title: '申请人已撤回对「机械创新设计竞赛组队」的申请。', body: '', jobId: 'job-4', jobTitle: '机械创新设计竞赛组队', recipientId: '20230004', createdAt: hoursAgo(55), read: true },
    { id: 'n-8', type: 'application_accepted', title: '你申请的「挑战杯参赛组队」已被发布者接受。', body: '', jobId: 'job-5', jobTitle: '挑战杯参赛组队', recipientId: '20230003', createdAt: hoursAgo(12), read: false },
  ];

  const auditLogs: AuditLog[] = [
    { id: 'log-1', operatorId: '20230001', operatorName: '张同学', operatorRole: 'student', targetType: 'job', targetId: 'job-11', targetTitle: '创业训练营项目助理招聘', action: 'delete_job', reason: '内容包含校外商业推广信息，违反平台规范。', createdAt: hoursAgo(50) },
    { id: 'log-2', operatorId: '20230001', operatorName: '张同学', operatorRole: 'student', targetType: 'job', targetId: 'job-0', targetTitle: '校外实习内推信息', action: 'delete_job', reason: '发布校外企业招聘信息，超出平台范围。', createdAt: hoursAgo(120) },
  ];

  // ── 站内聊天（设计稿第 13 页：纯文本，任意两用户可对话） ──
  const conversations: ConversationRow[] = [
    { id: 'conv-1', participantIds: ['20230002', '20230001'], updatedAt: hoursAgo(19) },
    { id: 'conv-2', participantIds: ['20230002', '20230003'], updatedAt: hoursAgo(29) },
    { id: 'conv-3', participantIds: ['20230002', '20230004'], updatedAt: hoursAgo(40) },
    { id: 'conv-4', participantIds: ['20230001', 'T2024001'], updatedAt: hoursAgo(5) },
    { id: 'conv-5', participantIds: ['20230002', 'T2024002'], updatedAt: hoursAgo(11) },
  ];

  const msg = (id: string, conversationId: string, senderId: string, text: string, h: number): Message => ({
    id,
    conversationId,
    senderId,
    text,
    createdAt: hoursAgo(h),
  });

  const messages: Message[] = [
    msg('m-1', 'conv-1', '20230001', '你好，请问智能机器人竞赛组队还在招人吗？', 22),
    msg('m-2', 'conv-1', '20230002', '在的，我们还缺一名开发队员。', 21),
    msg('m-3', 'conv-1', '20230001', '我可以参与，简历已经上传了。', 20),
    msg('m-4', 'conv-1', '20230002', '好的，我会尽快查看你的申请。', 19),
    msg('m-5', 'conv-2', '20230003', '关于项目分工想和你确认一下。', 30),
    msg('m-6', 'conv-2', '20230002', '没问题，你定时间我们聊。', 29),
    msg('m-7', 'conv-3', '20230004', '简历已经更新了，麻烦看一下。', 40),
    msg('m-8', 'conv-4', 'T2024001', '同学你好，创业训练营这边还想再招一名项目助理。', 6),
    msg('m-9', 'conv-4', '20230001', '老师好，我比较感兴趣，方便了解下时间安排吗？', 5),
    msg('m-10', 'conv-5', '20230002', '老师好，想咨询一下文创设计助手岗位的作品集要求。', 12),
    msg('m-11', 'conv-5', 'T2024002', '作品集不限形式，能体现视觉设计能力即可。', 11),
  ];

  return { users, jobs, applications, notifications, auditLogs, conversations, messages };
}
