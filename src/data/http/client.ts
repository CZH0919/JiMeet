import { canonicalPasswordMessage } from '@/domain/validation';

/**
 * 后端 HTTP 客户端：统一 `/api/v1` 前缀、JSON 信封、CSRF 会话流程。
 * 前端通过 Vite 开发代理转发到后端，不在页面硬编码后端地址（见 vite.config.ts）。
 * 契约见 `backend/design_file/api.md` §2、§3。
 */

const API_BASE = '/api/v1';

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
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

/** 后端错误码 → 中文文案（用于展示，不作为判断依据） */
const CODE_MESSAGES: Record<string, string> = {
  UNAUTHENTICATED: '登录状态已失效，请重新登录',
  AUTH_FAILED: '邮箱或密码不正确',
  FORBIDDEN: '无权执行该操作',
  NOT_FOUND: '资源不存在或已被删除',
  VALIDATION_ERROR: '参数校验失败',
  METHOD_NOT_ALLOWED: '请求方法不允许',
  RATE_LIMITED: '尝试次数过多，请稍后再试',
  PRIVACY_NOT_CONSENTED: '请先确认个人信息处理告知',
  SELF_APPLICATION_FORBIDDEN: '不能申请本人发布的招聘',
  RECRUITMENT_NOT_OPEN: '当前不允许新投递',
  RECRUITMENT_NOT_EDITABLE: '当前不允许编辑、关闭或删除',
  RECRUITMENT_FULL: '已满员，不能再接受申请',
  PROCESSING_WINDOW_CLOSED: '处理窗口已关闭',
  HEADCOUNT_BELOW_ACCEPTED: '人数上限低于已接受人数',
  DUPLICATE_APPLICATION: '你已申请过该招聘',
  APPLICATION_NOT_PROCESSING: '该申请已不是处理中',
  INVALID_RESUME_FILE: '简历文件校验失败',
  INTERNAL_ERROR: '服务暂时不可用，请稍后重试',
  SSO_UNAVAILABLE: '统一身份认证服务暂时不可用',
};

export function describeCode(code: string): string {
  return CODE_MESSAGES[code] ?? '请求失败，请稍后重试';
}

/** 后端 details 里的字段级说明 → 文本数组，密码类原文先归一到前端统一文案 */
function detailMessages(details: unknown): string[] {
  if (!details || typeof details !== 'object' || Array.isArray(details)) return [];
  const out: string[] = [];
  for (const value of Object.values(details as Record<string, unknown>)) {
    const text = (Array.isArray(value) ? value.join('；') : String(value ?? '')).trim();
    if (!text) continue;
    out.push(canonicalPasswordMessage(text) ?? text);
  }
  return out;
}

/** 简历文件校验失败时 `data.details.reason` 的取值 → 可读说明 */
const RESUME_REASON_MESSAGES: Record<string, string> = {
  type: '简历仅支持 PDF / DOC / DOCX 格式',
  size: '简历文件不得超过 10 MB',
  signature: '简历文件内容与扩展名不符，请勿直接修改扩展名',
};

/**
 * 错误文案组装：
 * 校验类错误直接给出具体原因，不再拼成「参数校验失败（这个密码太常见了。）」；
 * 业务类错误保留后端的具体说明，并在有字段明细时附在后面。
 */
function describeError(code: string, message: string, details?: unknown): string {
  if (code === 'INVALID_RESUME_FILE' && details && typeof details === 'object' && !Array.isArray(details)) {
    const reason = (details as Record<string, unknown>).reason;
    if (typeof reason === 'string' && RESUME_REASON_MESSAGES[reason]) return RESUME_REASON_MESSAGES[reason];
  }

  const own = message.trim();
  const canonical = own ? canonicalPasswordMessage(own) : null;
  const fields = detailMessages(details);

  if (code === 'VALIDATION_ERROR') {
    if (canonical) return canonical;
    if (fields.length > 0) return fields.join('；');
    if (own && own !== CODE_MESSAGES.VALIDATION_ERROR) return own;
    return '请检查填写内容后重试';
  }

  const base = canonical ?? (own || describeCode(code));
  return fields.length > 0 ? `${base}（${fields.join('；')}）` : base;
}

/** 后端字段级错误（`data.details`）→ 表单字段错误，便于把提示直接落到输入框下方 */
export function fieldErrorsFrom(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.details) return {};
  if (typeof error.details !== 'object' || Array.isArray(error.details)) return {};
  const out: Record<string, string> = {};
  for (const [field, value] of Object.entries(error.details as Record<string, unknown>)) {
    const text = (Array.isArray(value) ? value.join('；') : String(value ?? '')).trim();
    if (!text) continue;
    out[field] = canonicalPasswordMessage(text) ?? text;
  }
  return out;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  json?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | boolean | undefined>;
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

/** 发起请求，返回成功信封的 data 字段 */
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
    const hint =
      response.status === 404
        ? '接口不存在（HTTP 404），请确认后端版本与代理配置'
        : `服务返回了非 JSON 响应（HTTP ${response.status}）`;
    throw new ApiError('HTTP', hint, response.status);
  }

  const payload = await response.json();
  if (!response.ok || payload.code !== 'OK') {
    // 会话失效时通知应用层清理登录态（页头与路由守卫会随之回到未登录视图）
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('jiyu:unauthenticated'));
    }
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

/** 获取 CSRF 令牌（同时接收 csrftoken Cookie）。登录/注册成功后需再次调用刷新令牌。 */
export async function fetchCsrf(): Promise<string> {
  const data = await http.get<{ csrf_token: string }>('/auth/csrf');
  setCsrfToken(data.csrf_token);
  return data.csrf_token;
}

/**
 * 取简历文件流（GET，无需 CSRF）。
 * 在线预览与下载共用同一鉴权接口：后端按 `can_download_resume` 校验，
 * 预览不会额外放开权限，也不会产生公开链接。
 */
export async function fetchResumeResponse(applicationId: string): Promise<Response> {
  const response = await fetch(`${API_BASE}/applications/${applicationId}/resume`, {
    method: 'GET',
    credentials: 'same-origin',
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return response;
}

/** 简历内容 → Blob（用于在线预览，不落盘、不产生可分享链接） */
export async function fetchResumeBlob(applicationId: string): Promise<Blob> {
  const response = await fetchResumeResponse(applicationId);
  return response.blob();
}

/** 浏览器触发简历下载（GET，无需 CSRF），失败抛 ApiError */
export async function downloadResumeFile(applicationId: string): Promise<void> {
  const response = await fetchResumeResponse(applicationId);
  const blob = await response.blob();
  const cd = response.headers.get('Content-Disposition') ?? '';
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  let filename = `简历-${applicationId}`;
  if (m) {
    try {
      filename = decodeURIComponent(m[1]);
    } catch {
      filename = m[1];
    }
  }
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
