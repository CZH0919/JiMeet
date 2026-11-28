import { ArrowLeft, MessageSquare, UserRound } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { ROLE_LABEL } from '@/domain/labels';
import { Button } from '@/components/ui/Button';
import { ErrorState, InfoBanner, PageLoader } from '@/components/ui/Feedback';
import { toast } from '@/stores/toast';

/**
 * 对方主页（GET /users/{uid}）：只展示公开编号、昵称、师生身份与聊天入口。
 * 首次联系须从招聘详情（recruitment_id）或申请列表（application_id）进入，
 * 打开主页不会创建会话。
 */
export function PeerProfilePage() {
  const { uid } = useParams<{ uid: string }>();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const recruitmentId = params.get('recruitment_id') ?? undefined;
  const applicationId = params.get('application_id') ?? undefined;

  const profile = useAsync(
    () => repo.users.getPeer(uid!, { recruitmentId, applicationId }),
    [uid, recruitmentId, applicationId],
  );

  const [opening, setOpening] = useState(false);

  if (profile.loading) return <PageLoader />;
  if (profile.error) {
    return (
      <div className="page-shell py-10">
        <ErrorState message={profile.error} onRetry={profile.reload} />
        <p className="mt-3 text-center text-xs text-muted">
          首次联系请从招聘详情或申请列表进入对方主页。
        </p>
      </div>
    );
  }
  if (!profile.data) return null;

  const peer = profile.data;

  const openChat = async () => {
    if (!uid) return;
    setOpening(true);
    try {
      const conversation = await repo.messages.openWith(uid, { recruitmentId, applicationId });
      navigate(`/messages/${conversation.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '无法发起聊天');
    } finally {
      setOpening(false);
    }
  };

  return (
    <div className="page-shell py-8 sm:py-10">
      <button
        onClick={() => navigate(-1)}
        className="mb-4 inline-flex items-center gap-1 text-sm text-ink2 transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} /> 返回
      </button>

      <section className="panel flex flex-col gap-5 px-6 py-7 sm:flex-row sm:items-center sm:px-8">
        <span className="mx-auto flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-primary-soft text-2xl font-semibold text-primary sm:mx-0">
          {peer.nickname.slice(0, 1) || '?'}
        </span>
        <div className="min-w-0 flex-1 text-center sm:text-left">
          <h1 className="truncate text-xl font-bold text-ink">{peer.nickname}</h1>
          <p className="mt-1.5 flex items-center justify-center gap-1.5 text-sm text-ink2 sm:justify-start">
            <UserRound size={14} /> {ROLE_LABEL[peer.role]}
          </p>
          <p className="mt-2 break-all text-xs leading-relaxed text-ink2">
            公开编号 <span className="font-mono text-ink">{peer.uid}</span>
          </p>
        </div>
        <div className="flex w-full shrink-0 flex-col gap-2 sm:w-44">
          {peer.conversationId ? (
            <Link to={`/messages/${peer.conversationId}`} className="w-full">
              <Button size="lg" className="w-full">
                <MessageSquare size={16} /> 继续聊天
              </Button>
            </Link>
          ) : peer.canChat ? (
            <Button size="lg" className="w-full" loading={opening} onClick={openChat}>
              <MessageSquare size={16} /> 聊一聊
            </Button>
          ) : (
            <Button size="lg" className="w-full" disabled>
              暂不可联系
            </Button>
          )}
        </div>
      </section>

      <div className="mt-4">
        <InfoBanner>聊天内容仅双方可见，请勿发送敏感信息。</InfoBanner>
      </div>
    </div>
  );
}
