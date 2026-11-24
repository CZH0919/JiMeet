import type { Announcement, Application, Job, User } from './models';

/**
 * 权限判定纯函数。组件层用它决定「渲染或不渲染」，
 * 详情接口返回的 permissions 是服务端权威结果，优先使用；此层只做兜底。
 */
export const can = {
  /** 编辑本人发布的招聘 */
  editJob: (u: User | null, job: Job) => (job.permissions ? job.permissions.canEdit : !!u && u.id === job.publisher.id),

  /** 本人删除招聘（发布者入口，受进行中限制） */
  deleteJob: (u: User | null, job: Job) =>
    job.permissions ? job.permissions.canDelete : !!u && u.id === job.publisher.id,

  /** 管理员治理删除（独立入口，不受发布者窗口限制） */
  governDeleteJob: (u: User | null, job: Job) => job.permissions?.canGovernDelete ?? !!u?.isAdmin,

  /** 申请招聘 */
  applyJob: (u: User | null, job: Job) => !!u && (job.permissions?.canApply ?? false),

  /** 管理本人招聘的申请列表 */
  manageApps: (u: User | null, job: Job) =>
    job.permissions ? job.permissions.canViewApplications : !!u && u.id === job.publisher.id,

  /** 查看简历：申请者本人 / 招聘发布者（且后端返回了简历元数据） */
  viewResume: (u: User | null, app: Application, jobPublisherId: string) => {
    if (!u || app.resume === null) return false;
    return u.id === app.applicant.id || u.id === jobPublisherId;
  },

  /** 编辑公告：当前管理员且为作者 */
  editAnnouncement: (u: User | null, a: Announcement) => a.permissions.canEdit ?? !!u?.isAdmin,

  /** 删除公告（本人入口） */
  deleteAnnouncement: (u: User | null, a: Announcement) => a.permissions.canDelete ?? !!u?.isAdmin,

  /** 治理删除公告 */
  governDeleteAnnouncement: (a: Announcement) => a.permissions.canGovernDelete,
};
