import { MessageSquare, Search, Send } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { clsx } from 'clsx';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useSession } from '@/stores/session';
import { toast } from '@/stores/toast';
import { Button } from '@/components/ui/Button';

/**
 * 站内纯文本聊天（设计稿 F8）。
 * 后端 Sprint2 未交付聊天接口，当前使用本地演示仓储，仅用于界面走查。
 */
export function ChatPage() {
  const user = useSession((s) => s.user);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [kw, setKw] = useState('');
  const [sending, setSending] = useState(false);

  const conversations = useAsync(
    () => repo.messages.listConversations({ page: 1, pageSize: 100 }),
    [user?.id],
  );

  useEffect(() => {
    const first = conversations.data?.items[0]?.id ?? null;
    if (!activeId && first) setActiveId(first);
    if (activeId && conversations.data && !conversations.data.items.some((c) => c.id === activeId)) {
      setActiveId(first);
    }
  }, [conversations.data, activeId]);

  const messages = useAsync(
    () =>
      activeId
        ? repo.messages.listMessages(activeId, { page: 1, pageSize: 200 })
        : Promise.resolve({ items: [], page: 1, pageSize: 200, total: 0 }),
    [activeId],
  );

  const list = conversations.data?.items ?? [];
  const active = list.find((c) => c.id === activeId) ?? null;

  const filtered = useMemo(() => {
    const k = kw.trim();
    return k ? list.filter((c) => c.peer.name.includes(k)) : list;
  }, [list, kw]);

  const send = async () => {
    const text = draft.trim();
    if (!text || !activeId || sending) return;
    setSending(true);
    try {
      await repo.messages.send(activeId, text);
      setDraft('');
      messages.reload();
      conversations.reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '发送失败');
    } finally {
      setSending(false);
    }
  };

  const body = messages.data?.items ?? [];

  return (
    <div className="page-shell max-w-[1100px] py-8 sm:py-10">
      <div className="mb-4">
        <h1 className="text-xl font-bold text-ink">消息</h1>
        <p className="mt-1 text-sm text-ink2">与招聘发布者一对一沟通，聊天内容仅双方可见</p>
      </div>

      <div className="mb-4 rounded-md border border-warning/25 bg-warning-soft px-4 py-2.5 text-xs leading-relaxed text-ink2">
        聊天接口尚未开放，当前为本地演示数据。
      </div>

      <div className="panel flex h-[calc(100vh-16rem)] min-h-[420px] overflow-hidden">
        {/* 联系人列表 */}
        <aside className="flex w-64 shrink-0 flex-col border-r border-line">
          <div className="border-b border-line p-3">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                value={kw}
                onChange={(e) => setKw(e.target.value)}
                placeholder="搜索联系人"
                className="w-full rounded-md border border-line bg-page py-2 pl-8 pr-3 text-sm focus:border-primary focus:outline-none"
              />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {conversations.loading && <p className="px-4 py-6 text-center text-xs text-muted">加载中…</p>}
            {conversations.error && (
              <div className="px-4 py-6 text-center text-xs text-muted">
                {conversations.error}
                <button onClick={conversations.reload} className="mt-2 block w-full text-primary">
                  重试
                </button>
              </div>
            )}
            {!conversations.loading && !conversations.error && filtered.length === 0 && (
              <p className="px-4 py-6 text-center text-xs text-muted">暂无会话</p>
            )}
            {filtered.map((c) => (
              <button
                key={c.id}
                onClick={() => setActiveId(c.id)}
                className={clsx(
                  'flex w-full flex-col gap-1 border-b border-line/60 px-4 py-3 text-left transition-colors',
                  c.id === activeId ? 'bg-primary-soft' : 'hover:bg-page',
                )}
              >
                <span className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-soft text-sm font-medium text-primary">
                    {c.peer.name.slice(0, 1)}
                  </span>
                  <span className="text-sm font-medium text-ink">{c.peer.name}</span>
                </span>
                <span className="truncate pl-10 text-xs text-ink2">
                  {c.lastMessage
                    ? `${c.lastMessage.senderId === 'me' ? '我：' : ''}${c.lastMessage.text}`
                    : '暂无消息'}
                </span>
              </button>
            ))}
          </div>
        </aside>

        {/* 会话区 */}
        <div className="flex min-w-0 flex-1 flex-col">
          {!active ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm text-muted">
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-muted-soft">
                <MessageSquare size={22} />
              </span>
              选择一个会话开始聊天
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between border-b border-line px-5 py-3">
                <span className="text-sm font-semibold text-ink">{active.peer.name}</span>
              </div>

              <div className="flex-1 overflow-y-auto p-5">
                {messages.loading && <p className="py-6 text-center text-xs text-muted">加载中…</p>}
                {messages.error && (
                  <div className="py-6 text-center text-xs text-muted">
                    {messages.error}
                    <button onClick={messages.reload} className="mt-2 block w-full text-primary">
                      重试
                    </button>
                  </div>
                )}
                {!messages.loading && !messages.error && body.length === 0 && (
                  <p className="py-6 text-center text-xs text-muted">还没有消息，说点什么吧</p>
                )}
                <div className="flex flex-col gap-3">
                  {body.map((m) => {
                    const mine = m.senderId === 'me';
                    return (
                      <div key={m.id} className={clsx('flex', mine ? 'justify-end' : 'justify-start')}>
                        <div className="max-w-[70%]">
                          <div
                            className={clsx(
                              'rounded-lg px-4 py-2.5 text-sm leading-relaxed',
                              mine ? 'bg-primary text-white' : 'bg-page text-ink',
                            )}
                          >
                            {m.text}
                          </div>
                          <p className={clsx('mt-1 text-[11px] text-muted', mine ? 'text-right' : 'text-left')}>
                            {new Date(m.createdAt).toLocaleTimeString('zh-CN', {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="border-t border-line p-4">
                <p className="mb-2 text-xs text-muted">聊天内容仅双方可见</p>
                <div className="flex gap-2">
                  <input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && void send()}
                    placeholder="输入纯文本消息"
                    className="flex-1 rounded-md border border-line bg-page px-3 py-2 text-sm focus:border-primary focus:outline-none"
                  />
                  <Button onClick={() => void send()} disabled={sending || !draft.trim()}>
                    <Send size={15} /> 发送
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
