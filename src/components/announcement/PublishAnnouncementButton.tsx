import { PenLine } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '@/stores/session';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';

const RULES = [
  '仅限竞赛 / 活动类专业信息，不发布与招聘无关的广告或闲聊。',
  '普通用户提交后进入管理员待审池，需经管理员审核后才能公开。',
  '管理员预计在 24 小时内处理；超过 24 小时未处理的投稿会优先处理。',
  '每日最多投稿 5 条，同时待审最多 5 条；投稿提交后不能改稿、撤回。',
];

/**
 * 首页「发布公告」入口。
 * 管理员直接进入发布表单；普通用户先展示投稿规则，确认后再进入投稿表单（FR-09）。
 */
export function PublishAnnouncementButton({ className }: { className?: string }) {
  const user = useSession((s) => s.user);
  const navigate = useNavigate();
  const [rulesOpen, setRulesOpen] = useState(false);

  if (!user) return null;

  const start = () => {
    setRulesOpen(false);
    navigate('/announcements/new');
  };

  return (
    <>
      <Button
        size="sm"
        className={className}
        onClick={() => (user.isAdmin ? start() : setRulesOpen(true))}
      >
        <PenLine size={15} /> 发布公告
      </Button>

      <Modal
        open={rulesOpen}
        title="公告投稿规则"
        description="请先了解投稿要求，确认后进入投稿表单。"
        onClose={() => setRulesOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRulesOpen(false)}>
              取消
            </Button>
            <Button onClick={start}>我已了解，去投稿</Button>
          </>
        }
      >
        <ul className="flex flex-col gap-2.5">
          {RULES.map((r) => (
            <li key={r} className="flex gap-2 text-sm leading-relaxed text-ink2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              {r}
            </li>
          ))}
        </ul>
      </Modal>
    </>
  );
}
