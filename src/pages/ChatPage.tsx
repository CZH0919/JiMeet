import { Search, Send } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { clsx } from 'clsx';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useSession } from '@/stores/session';
import { toast } from '@/stores/toast';

/** 站内纯文本聊天（设计稿第 13 页）。数据全部经 MessageRepository 端口取得。 */
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

  // 默认选中第一个会话
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
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex h-[calc(100vh-10rem)] overflow-hidden rounded-xl border border-line bg-surface">
        {/* 联系人列表 */}
        <aside className="flex w-64 shrink-0 flex-col border-r border-line">
          <div className="border-b border-line p-3">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                value={kw}
                onChange={(e) => setKw(e.target.value)}
                placeholder="搜索联系人"
                className="w-full rounded-md border border-line bg-page py-2 pl-8 pr-3 text-sm focus:outline-none focus:border-primary"
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
                  'flex w-full flex-col gap-0.5 border-b border-line/60 px-4 py-3 text-left transition-colors',
                  c.id === activeId ? 'bg-primary-soft' : 'hover:bg-page',
                )}
              >
                <span className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-soft text-sm text-primary">
                    {c.peer.name[0]}
                  </span>
                  <span className="text-sm font-medium text-ink">{c.peer.name}</span>
                </span>
                <span className="truncate pl-10 text-xs text-ink2">
                  {c.lastMessage
                    ? `${c.lastMessage.senderId === user?.id ? '我：' : ''}${c.lastMessage.text}`
                    : '暂无消息'}
                </span>
              </button>
            ))}
          </div>
        </aside>

        {/* 会话区 */}
        <div className="flex min-w-0 flex-1 flex-col">
          {!active && (
            <div className="flex flex-1 items-center justify-center text-sm text-muted">
              选择一个会话开始聊天
            </div>
          )}

          {active && (
            <>
              <div className="border-b border-line px-5 py-3">
                <span className="text-sm font-semibold text-ink">{active.peer.name}</span>
                <span className="ml-2 text-xs text-muted">纯文本自由聊天</span>
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
                    const mine = m.senderId === user?.id;
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
                          <p className={clsx('mt-1 text-xs text-muted', mine ? 'text-right' : 'text-left')}>
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
                <p className="mb-2 text-xs text-muted">纯文本自由聊天，聊天记录不会被管理员查看</p>
                <div className="flex gap-2">
                  <input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && void send()}
                    placeholder="输入纯文本消息"
                    className="flex-1 rounded-md border border-line bg-page px-3 py-2 text-sm focus:outline-none focus:border-primary"
                  />
                  <button
                    onClick={() => void send()}
                    disabled={sending || !draft.trim()}
                    className="flex items-center gap-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Send size={15} /> 发送
                  </button>
                </div>
                {user && <p className="mt-2 text-xs text-muted">当前登录：{user.name}</p>}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
