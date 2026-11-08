import type { Application, Job, User } from './models';
import { canApply } from './jobStatus';

/**
 * 权限判定纯函数。组件层用它决定「渲染或不渲染」，
 * 提交层与 Repository 层再各自校验一次（三层防线）。
 */
export const can = {
  /** 编辑本人发布的招聘 */
  editJob: (u: User | null, job: Job) => !!u && u.id === job.publisher.id,

  /** 删除本人发布的招聘 */
  deleteJob: (u: User | null, job: Job) => !!u && u.id === job.publisher.id,

  /** 管理员治理删除：管理员且非发布者本人 */
  moderateJob: (u: User | null, job: Job) => !!u && u.isAdmin && u.id !== job.publisher.id,

  /** 申请招聘（统一走 canApply；详情页优先用后端 permissions） */
  applyJob: (u: User | null, job: Job) =>
    job.permissions ? job.permissions.canApply : canApply(job, u).ok,

  /** 管理本人招聘的申请列表 */
  manageApps: (u: User | null, job: Job) => !!u && u.id === job.publisher.id,

  /** 查看简历：申请者本人 / 招聘发布者（且简历可见） */
  viewResume: (u: User | null, app: Application, job: Job) => {
    if (!u) return false;
    if (u.id === app.applicant.id) return app.resume !== null;
    if (u.id === job.publisher.id) return app.resume !== null;
    return false;
  },
};
