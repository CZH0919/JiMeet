/**
 * 后端 HTTP 客户端：统一 `/api/v1` 前缀、JSON 信封、CSRF 会话流程。
 * 前端通过 Vite 开发代理转发到后端，不在页面硬编码后端地址（见 vite.config.ts）。
 */

const API_BASE = '/api/v1';

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: unknown;
  readonly requestId?: string;
  constructor(code: string, message: string, status: number, details?: unknown, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
  }
}

/** 后端错误码 → 中文文案（后端 message 为空或英文时兜底；用于展示，不作为判断依据） */
const CODE_MESSAGES: Record<string, string> = {
  UNAUTHENTICATED: '登录状态失效，请重新登录',
  AUTH_FAILED: '登录失败：编号或身份不合法',
  FORBIDDEN: '无权执行该操作',
  NOT_FOUND: '资源不存在或已被删除',
  VALIDATION_ERROR: '参数校验失败',
  METHOD_NOT_ALLOWED: '请求方法不允许',
  PRIVACY_NOT_CONSENTED: '请先确认个人信息处理告知',
  SELF_APPLICATION_FORBIDDEN: '不能申请本人发布的招募',
  RECRUITMENT_NOT_OPEN: '当前不允许新投递',
  RECRUITMENT_NOT_EDITABLE: '当前不允许编辑、关闭或删除',
  RECRUITMENT_FULL: '已满员，不能再接受申请',
  PROCESSING_WINDOW_CLOSED: '处理窗口已关闭',
  HEADCOUNT_BELOW_ACCEPTED: '人数上限低于已接受人数',
  DUPLICATE_APPLICATION: '你已申请过该招募',
  APPLICATION_NOT_PROCESSING: '该申请已不是处理中',
  INVALID_RESUME_FILE: '简历文件校验失败',
  INTERNAL_ERROR: '服务暂时不可用，请稍后重试',
  SSO_UNAVAILABLE: '统一身份认证服务暂时不可用',
};

export function describeCode(code: string): string {
  return CODE_MESSAGES[code] ?? '请求失败，请稍后重试';
}

function describeError(code: string, message: string, details?: unknown): string {
  let text = message && message.trim() ? message.trim() : describeCode(code);
  if (details && typeof details === 'object' && !Array.isArray(details)) {
    const parts = Object.entries(details as Record<string, unknown>).map(([k, v]) => {
      const val = Array.isArray(v) ? v.join('；') : String(v);
      return `${k}: ${val}`;
    });
    if (parts.length > 0) text = `${text}（${parts.join('；')}）`;
  }
  return text;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  json?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | undefined>;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `${url}?${s}` : url;
}

async function parseError(response: Response): Promise<ApiError> {
  let code = 'INTERNAL_ERROR';
  let message = '';
  let details: unknown;
  let requestId: string | undefined;
  try {
    const ct = response.headers.get('Content-Type') ?? '';
    if (ct.includes('application/json')) {
      const payload = await response.json();
      code = payload.code ?? code;
      message = payload.message ?? '';
      details = payload.data?.details;
      requestId = payload.request_id;
    }
  } catch {
    /* 非 JSON 错误响应，忽略 */
  }
  return new ApiError(code, describeError(code, message, details), response.status, details, requestId);
}

/** 发起 JSON 请求，返回成功信封的 data 字段 */
async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', json, formData, query } = opts;
  const headers: Record<string, string> = { Accept: 'application/json' };
  let body: BodyInit | undefined;

  if (formData) {
    body = formData; // 浏览器自动生成 multipart boundary，不手写 Content-Type
  } else if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  }

  if (method !== 'GET' && csrfToken) {
    headers['X-CSRFToken'] = csrfToken;
  }

  const response = await fetch(buildUrl(path, query), {
    method,
    headers,
    credentials: 'same-origin',
    body,
  });

  const ct = response.headers.get('Content-Type') ?? '';
  if (!ct.includes('application/json')) {
    throw new ApiError('HTTP', `非 JSON 响应：HTTP ${response.status}`, response.status);
  }

  const payload = await response.json();
  if (!response.ok || payload.code !== 'OK') {
    throw new ApiError(
      payload.code ?? 'INTERNAL_ERROR',
      describeError(payload.code, payload.message ?? '', payload.data?.details),
      response.status,
      payload.data?.details,
      payload.request_id,
    );
  }
  return payload.data as T;
}

export const http = {
  get<T>(path: string, query?: RequestOptions['query']) {
    return request<T>(path, { query });
  },
  post<T>(path: string, json?: unknown) {
    return request<T>(path, { method: 'POST', json });
  },
  patch<T>(path: string, json?: unknown) {
    return request<T>(path, { method: 'PATCH', json });
  },
  del<T>(path: string, json?: unknown) {
    return request<T>(path, { method: 'DELETE', json });
  },
  postForm<T>(path: string, formData: FormData) {
    return request<T>(path, { method: 'POST', formData });
  },
  patchForm<T>(path: string, formData: FormData) {
    return request<T>(path, { method: 'PATCH', formData });
  },
};

/** 获取 CSRF 令牌（同时接收 csrftoken Cookie） */
export async function fetchCsrf(): Promise<void> {
  const data = await http.get<{ csrf_token: string }>('/auth/csrf');
  setCsrfToken(data.csrf_token);
}

/** 浏览器触发文件下载（GET，无需 CSRF），失败抛 ApiError */
export async function downloadResume(applicationId: string): Promise<void> {
  const url = `${API_BASE}/applications/${applicationId}/resume`;
  const response = await fetch(url, { method: 'GET', credentials: 'same-origin' });
  if (!response.ok) {
    throw await parseError(response);
  }
  const blob = await response.blob();
  const cd = response.headers.get('Content-Disposition') ?? '';
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const filename = m ? decodeURIComponent(m[1]) : `简历-${applicationId}`;
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
