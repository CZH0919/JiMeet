import { ChevronLeft, MessageSquare, Search, Send } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { clsx } from 'clsx';
import { useNavigate, useParams } from 'react-router-dom';
import type { Conversation, Message } from '@/domain/models';
import { MAX_PAGE_SIZE } from '@/domain/models';
import { repo } from '@/data';
import { fetchAllPages } from '@/data/fetchAll';
import { ApiError } from '@/data/http/client';
import { useAsync } from '@/features/useAsync';
import { useSession } from '@/stores/session';
import { toast } from '@/stores/toast';
import { formatRelative } from '@/domain/format';
import { messageLength, validateMessage, LIMITS } from '@/domain/validation';
import { Button } from '@/components/ui/Button';

const MESSAGE_PAGE_SIZE = MAX_PAGE_SIZE;

function mergeMessages(older: Message[], newer: Message[]): Message[] {
  const map = new Map<string, Message>();
  for (const m of [...older, ...newer]) map.set(m.id, m);
  return [...map.values()].sort((a, b) => {
    const diff = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
    return diff !== 0 ? diff : Number(a.id) - Number(b.id);
  });
}

/** 站内一对一纯文本聊天：会话列表、历史回翻、发送与已读回执（api.md 第 10 章） */
export function ChatPage() {
  const user = useSession((s) => s.user);
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();

  const [listTick, setListTick] = useState(0);
  const [pollTick, setPollTick] = useState(0);
  const [reloadTick, setReloadTick] = useState(0);
  const [kw, setKw] = useState('');
  const [unreadTotal, setUnreadTotal] = useState(0);

  const conversations = useAsync(
    () =>
      fetchAllPages((p, s) => repo.messages.listConversations({ page: p, pageSize: s })),
    [user?.id, listTick],
  );

  const list = conversations.data ?? [];
  const active = list.find((c) => c.id === conversationId) ?? null;
  const activeId = conversationId ?? null;

  const [messages, setMessages] = useState<Message[]>([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [msgError, setMsgError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [olderLoading, setOlderLoading] = useState(false);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [pauseUntil, setPauseUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  const bottomRef = useRef<HTMLDivElement>(null);
  const receiptRef = useRef<Set<string>>(new Set());
  const initialLoadedRef = useRef<string | null>(null);

  const refreshList = useCallback(() => setListTick((t) => t + 1), []);

  const refreshUnread = useCallback(async () => {
    try {
      setUnreadTotal(await repo.messages.unreadCount());
    } catch {
      /* 轮询失败保留上次数值 */
    }
  }, []);

  useEffect(() => {
    void refreshUnread();
  }, [refreshUnread, user?.id]);

  // 15 秒轮询：静默合并最新消息与会话摘要，不打断正在输入的用户
  useEffect(() => {
    const timer = window.setInterval(() => {
      setPollTick((t) => t + 1);
      setListTick((t) => t + 1);
    }, 15_000);
    return () => window.clearInterval(timer);
  }, []);

  // 暂停发送倒计时
  useEffect(() => {
    if (pauseUntil <= Date.now()) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [pauseUntil]);

  // 切换会话：重置并加载最新一页（后端按时间倒序返回，页面按正序渲染）
  useEffect(() => {
    receiptRef.current.clear();
    setMessages([]);
    setDraft('');
    setMsgError(null);
    if (!activeId) {
      setMsgLoading(false);
      setHasMore(false);
      initialLoadedRef.current = null;
      return;
    }
    let cancelled = false;
    setMsgLoading(true);
    setHasMore(false);
    initialLoadedRef.current = activeId;
    repo.messages
      .listMessages(activeId, { page: 1, pageSize: MESSAGE_PAGE_SIZE })
      .then((page) => {
        if (cancelled) return;
        // 后端按 created_at / id 倒序返回，页面按时间正序渲染
        const ordered = page.items.slice().sort((a, b) => {
          const diff = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
          return diff !== 0 ? diff : Number(a.id) - Number(b.id);
        });
        setMessages(ordered);
        setHasMore(page.total > page.items.length);
        scrollToBottom();
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setMsgError(e instanceof Error ? e.message : '消息加载失败');
      })
      .finally(() => {
        if (!cancelled) setMsgLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId, reloadTick]);

  // 轮询静默合并：保留已回翻的历史，只并入最新一页
  useEffect(() => {
    if (!activeId || pollTick === 0) return;
    if (initialLoadedRef.current !== activeId) return;
    let cancelled = false;
    repo.messages
      .listMessages(activeId, { page: 1, pageSize: MESSAGE_PAGE_SIZE })
      .then((page) => {
        if (cancelled) return;
        setMessages((prev) => {
          const merged = mergeMessages(prev, page.items);
          if (merged.length > prev.length) {
            // 有新消息时贴近底部
            window.requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ block: 'end' }));
          }
          return merged;
        });
      })
      .catch(() => {
        /* 静默轮询失败不打扰 */
      });
    return () => {
      cancelled = true;
    };
  }, [pollTick, activeId]);

  // 实际展示对方消息后提交已读回执（最多 50 条，不重复提交）
  useEffect(() => {
    if (!user || !activeId || messages.length === 0) return;
    const ids = messages
      .filter((m) => m.senderId !== user.id && !m.readAt && !receiptRef.current.has(m.id))
      .map((m) => m.id)
      .slice(0, 50);
    if (ids.length === 0) return;
    ids.forEach((id) => receiptRef.current.add(id));
    void repo.messages
      .markRead(activeId, ids)
      .then((updated) => {
        if (updated > 0) {
          void refreshUnread();
          refreshList();
        }
      })
      .catch(() => {
        /* 回执失败不影响阅读 */
      });
  }, [messages, activeId, user, refreshUnread, refreshList]);

  const filtered = useMemo(() => {
    const k = kw.trim();
    return k ? list.filter((c) => c.peer.name.includes(k)) : list;
  }, [list, kw]);

  const scrollToBottom = () => {
    window.requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ block: 'end' }));
  };

  const loadOlder = async () => {
    if (!activeId || olderLoading || messages.length === 0) return;
    setOlderLoading(true);
    try {
      const page = await repo.messages.listMessages(activeId, {
        page: 1,
        pageSize: MESSAGE_PAGE_SIZE,
        beforeId: messages[0].id,
      });
      setMessages((prev) => mergeMessages(page.items, prev));
      setHasMore(messages.length + page.items.length < page.total);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '加载更早消息失败');
    } finally {
      setOlderLoading(false);
    }
  };

  const pausedSeconds = Math.max(0, Math.ceil((pauseUntil - now) / 1000));

  const send = async () => {
    if (!activeId || sending) return;
    const err = validateMessage(draft);
    if (err) {
      toast.error(err);
      return;
    }
    if (pausedSeconds > 0) {
      toast.error(`发送过于频繁，请 ${pausedSeconds} 秒后重试`);
      return;
    }
    setSending(true);
    try {
      const message = await repo.messages.send(activeId, draft);
      setMessages((prev) => mergeMessages(prev, [message]));
      setDraft('');
      refreshList();
      scrollToBottom();
    } catch (e) {
      if (e instanceof ApiError && e.code === 'RATE_LIMITED') {
        const raw = (e.details as Record<string, unknown> | undefined)?.retry_after;
        const seconds = Number(raw);
        const pause = Number.isFinite(seconds) && seconds > 0 ? seconds : 60;
        setPauseUntil(Date.now() + pause * 1000);
        setNow(Date.now());
        toast.error(`发送过于频繁，请 ${pause} 秒后重试`);
      } else {
        toast.error(e instanceof Error ? e.message : '发送失败');
      }
    } finally {
      setSending(false);
    }
  };

  const openConversation = (c: Conversation) => {
    navigate(`/messages/${c.id}`);
  };

  const inputLength = messageLength(draft);
  const canSend = !!activeId && draft.trim().length > 0 && inputLength <= LIMITS.message && pausedSeconds === 0;

  return (
    <div className="page-shell py-8 sm:py-10">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-ink">
            消息
            {unreadTotal > 0 && (
              <span className="rounded-full bg-danger-soft px-2 py-0.5 text-xs font-medium text-danger">
                {unreadTotal} 条未读
              </span>
            )}
          </h1>
          <p className="mt-1 text-sm text-ink2">与招聘发布者或申请人一对一沟通，内容仅双方可见</p>
        </div>
      </div>

      <div className="panel flex h-[calc(100vh-14rem)] min-h-[440px] overflow-hidden">
        {/* 联系人列表 */}
        <aside
          className={clsx(
            'w-full shrink-0 flex-col border-r border-line sm:flex sm:w-72',
            activeId ? 'hidden' : 'flex',
          )}
        >
          <div className="border-b border-line p-3">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                value={kw}
                onChange={(e) => setKw(e.target.value)}
                placeholder="搜索已有会话"
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
              <p className="px-4 py-6 text-center text-xs text-muted">
                暂无会话，可从招聘详情「聊一聊」或申请列表发起
              </p>
            )}
            {filtered.map((c) => (
              <button
                key={c.id}
                onClick={() => openConversation(c)}
                className={clsx(
                  'flex w-full flex-col gap-1 border-b border-line/60 px-4 py-3 text-left transition-colors',
                  c.id === activeId ? 'bg-primary-soft' : 'hover:bg-page',
                )}
              >
                <span className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-soft text-sm font-medium text-primary">
                    {c.peer.name.slice(0, 1)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{c.peer.name}</span>
                  {c.unreadCount > 0 && (
                    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-none text-white">
                      {c.unreadCount > 99 ? '99+' : c.unreadCount}
                    </span>
                  )}
                </span>
                <span className="flex items-center gap-2 pl-10">
                  <span className="min-w-0 flex-1 truncate text-xs text-ink2">
                    {c.lastMessage
                      ? `${c.lastMessage.senderId === user?.id ? '我：' : ''}${c.lastMessage.text}`
                      : '暂无消息'}
                  </span>
                  <span className="shrink-0 text-[11px] text-muted">
                    {c.lastMessage ? formatRelative(c.lastMessage.createdAt) : ''}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </aside>

        {/* 会话区 */}
        <div className={clsx('min-w-0 flex-1 flex-col', activeId ? 'flex' : 'hidden sm:flex')}>
          {!activeId ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm text-muted">
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-muted-soft">
                <MessageSquare size={22} />
              </span>
              选择一个会话开始聊天
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 border-b border-line px-4 py-3">
                <button
                  onClick={() => navigate('/messages')}
                  className="rounded-md p-1 text-muted hover:bg-muted-soft hover:text-ink sm:hidden"
                  aria-label="返回会话列表"
                >
                  <ChevronLeft size={18} />
                </button>
                <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
                  {active?.peer.name ?? '会话'}
                </span>
                {active && (
                  <span className="rounded-full bg-muted-soft px-2 py-0.5 text-xs text-ink2">
                    {active.peer.role === 'teacher' ? '教师' : '学生'}
                  </span>
                )}
              </div>

              <div className="flex-1 overflow-y-auto p-4 sm:p-5">
                {msgLoading ? (
                  <p className="py-8 text-center text-xs text-muted">加载中…</p>
                ) : msgError ? (
                  <div className="py-8 text-center text-xs text-muted">
                    {msgError}
                    <button
                      onClick={() => setReloadTick((t) => t + 1)}
                      className="mt-2 block w-full text-primary"
                    >
                      重试
                    </button>
                  </div>
                ) : (
                  <>
                    {hasMore && (
                      <div className="mb-4 text-center">
                        <Button size="sm" variant="secondary" loading={olderLoading} onClick={() => void loadOlder()}>
                          加载更早的消息
                        </Button>
                      </div>
                    )}
                    {messages.length === 0 && (
                      <p className="py-8 text-center text-xs text-muted">暂无消息</p>
                    )}
                    <div className="flex flex-col gap-3">
                      {messages.map((m) => {
                        const mine = m.senderId === user?.id;
                        return (
                          <div key={m.id} className={clsx('flex', mine ? 'justify-end' : 'justify-start')}>
                            <div className="max-w-[78%]">
                              <div
                                className={clsx(
                                  'whitespace-pre-wrap break-words rounded-lg px-4 py-2.5 text-sm leading-relaxed',
                                  mine ? 'bg-primary text-white' : 'bg-page text-ink',
                                )}
                              >
                                {m.text}
                              </div>
                              <p className={clsx('mt-1 text-[11px] text-muted', mine ? 'text-right' : 'text-left')}>
                                {new Date(m.createdAt).toLocaleString('zh-CN', {
                                  month: '2-digit',
                                  day: '2-digit',
                                  hour: '2-digit',
                                  minute: '2-digit',
                                })}
                              </p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <div ref={bottomRef} />
                  </>
                )}
              </div>

              <div className="border-t border-line p-3 sm:p-4">
                <div className="flex items-end gap-2">
                  <div className="min-w-0 flex-1">
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                          e.preventDefault();
                          void send();
                        }
                      }}
                      rows={2}
                      placeholder="输入纯文本消息，Enter 发送，Shift+Enter 换行"
                      className={clsx(
                        'w-full resize-none rounded-md border bg-page px-3 py-2 text-sm leading-relaxed focus:border-primary focus:outline-none',
                        inputLength > LIMITS.message ? 'border-danger' : 'border-line',
                      )}
                    />
                    <div className="mt-1 flex items-center justify-between text-[11px] text-muted">
                      <span>
                        {pausedSeconds > 0
                          ? `发送已暂停，请 ${pausedSeconds} 秒后重试`
                          : '仅纯文本，支持基础 Emoji'}
                      </span>
                      <span className={clsx(inputLength > LIMITS.message && 'text-danger')}>
                        {inputLength}/{LIMITS.message}
                      </span>
                    </div>
                  </div>
                  <Button onClick={() => void send()} disabled={!canSend} loading={sending}>
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
