import { clsx } from 'clsx';
import { Download, ExternalLink, FileText, Maximize2, Minimize2, RotateCcw } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { ResumeFile } from '@/domain/models';
import { repo } from '@/data';
import { fileSizeLabel } from '@/domain/validation';
import { docxToHtml } from '@/lib/docxHtml';
import { Button } from '@/components/ui/Button';
import { toast } from '@/stores/toast';

type Phase = 'loading' | 'ready' | 'unsupported' | 'error';

type ResumeKind = 'pdf' | 'docx' | 'doc' | 'other';

function detectKind(file: ResumeFile): ResumeKind {
  const byType = file.type.toLowerCase();
  if (byType === 'pdf' || byType === 'docx' || byType === 'doc') return byType;
  const dot = file.fileName.lastIndexOf('.');
  const ext = dot >= 0 ? file.fileName.slice(dot + 1).toLowerCase() : '';
  if (ext === 'pdf' || ext === 'docx' || ext === 'doc') return ext;
  return 'other';
}

interface ResumePreviewProps {
  applicationId: string;
  file: ResumeFile;
  canDownload: boolean;
}

/**
 * 简历在线预览（类微信的「直接看内容」体验，不下载、不产生公开链接）。
 *
 * - PDF：用浏览器内置阅读器内嵌展示；
 * - DOCX：浏览器端解析成 HTML 排版展示；
 * - DOC：浏览器无法渲染旧版二进制格式，降级提示下载查看。
 *
 * 预览与下载走同一个鉴权接口，能否预览由 `can_download_resume` 决定。
 */
export function ResumePreview({ applicationId, file, canDownload }: ResumePreviewProps) {
  const [phase, setPhase] = useState<Phase>('loading');
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unsupportedHint, setUnsupportedHint] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [downloading, setDownloading] = useState(false);

  const kind = detectKind(file);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;

    setPhase('loading');
    setError(null);
    setHtml(null);
    setPdfUrl(null);

    if (!canDownload) {
      setUnsupportedHint('当前申请状态不允许查看简历内容。');
      setPhase('unsupported');
      return;
    }

    const load = async () => {
      try {
        const blob = await repo.applications.resumeBlob(applicationId);
        if (cancelled) return;

        if (kind === 'pdf') {
          objectUrl = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
          if (cancelled) {
            URL.revokeObjectURL(objectUrl);
            return;
          }
          setPdfUrl(objectUrl);
          setPhase('ready');
          return;
        }

        if (kind === 'docx' || kind === 'doc') {
          if (typeof DecompressionStream === 'undefined') {
            setUnsupportedHint('当前浏览器不支持在线解析 DOCX，请升级浏览器或下载后查看。');
            setPhase('unsupported');
            return;
          }
          try {
            // 有些 .doc 实际是 OOXML 包，先按 DOCX 试解析，失败再走旧格式提示
            const rendered = await docxToHtml(await blob.arrayBuffer());
            if (cancelled) return;
            setHtml(rendered);
            setPhase('ready');
          } catch (e) {
            if (cancelled) return;
            if (/DOCX|压缩/.test(e instanceof Error ? e.message : '')) {
              setUnsupportedHint(
                kind === 'doc'
                  ? '旧版 .doc 需下载后用 Word 打开；如需在线查看，请另存为 PDF 或 DOCX 后重新提交。'
                  : 'DOCX 文件结构不完整或已损坏，请下载后查看。',
              );
              setPhase('unsupported');
              return;
            }
            throw e;
          }
          return;
        }

        setUnsupportedHint('该文件格式无法在页面内预览，请下载后查看。');
        setPhase('unsupported');
      } catch (e) {
        if (cancelled) return;
        const message = e instanceof Error ? e.message : '简历加载失败';
        setError(message);
        if (/DOCX|压缩/.test(message)) {
          setUnsupportedHint('DOCX 文件结构不完整或已损坏，请下载后查看。');
          setPhase('unsupported');
          return;
        }
        setPhase('error');
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [applicationId, kind, attempt, canDownload]);

  const download = async () => {
    setDownloading(true);
    try {
      await repo.applications.downloadResume(applicationId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '下载失败');
    } finally {
      setDownloading(false);
    }
  };

  const viewerHeight = expanded ? 'h-[74vh]' : 'h-[52vh]';

  return (
    <section className="flex flex-col gap-3">
      <header className="flex flex-wrap items-center gap-3 rounded-md border border-line bg-page px-4 py-3">
        <FileText className="h-6 w-6 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink" title={file.fileName}>
            {file.fileName}
          </p>
          <p className="text-xs text-ink2">
            {fileSizeLabel(file.size)} · {kind === 'pdf' ? 'PDF' : kind === 'docx' ? 'DOCX' : 'DOC'}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {phase === 'ready' && kind === 'pdf' && pdfUrl && (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1 rounded-md border border-line bg-surface px-3 text-[13px] font-medium text-ink transition-colors hover:border-primary/40 hover:text-primary"
            >
              <ExternalLink size={14} /> 新窗口
            </a>
          )}
          {phase === 'ready' && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setExpanded((v) => !v)}
              title={expanded ? '收起预览' : '放大预览'}
            >
              {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              {expanded ? '收起' : '放大'}
            </Button>
          )}
          {canDownload && (
            <Button size="sm" variant="secondary" loading={downloading} onClick={download}>
              <Download size={14} /> 下载
            </Button>
          )}
        </div>
      </header>

      <div
        className={clsx(
          'relative overflow-hidden rounded-md border border-line bg-muted-soft',
          viewerHeight,
        )}
      >
        {phase === 'loading' && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-ink2">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            正在加载简历…
          </div>
        )}

        {phase === 'ready' && kind === 'pdf' && pdfUrl && (
          <iframe src={pdfUrl} title="简历预览" className="h-full w-full bg-surface" />
        )}

        {phase === 'ready' && kind === 'docx' && html && (
          <div className="h-full overflow-auto bg-muted-soft px-2 py-3 sm:px-4">
            <div className="docx-page" dangerouslySetInnerHTML={{ __html: html }} />
          </div>
        )}

        {phase === 'unsupported' && (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <FileText className="h-8 w-8 text-muted" />
            <p className="text-sm font-medium text-ink">该格式暂不支持在线预览</p>
            <p className="max-w-sm text-xs leading-relaxed text-ink2">{unsupportedHint}</p>
          </div>
        )}

        {phase === 'error' && (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="text-sm font-medium text-ink">简历加载失败</p>
            <p className="max-w-sm text-xs leading-relaxed text-ink2">{error}</p>
            <Button size="sm" variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
              <RotateCcw size={14} /> 重试
            </Button>
          </div>
        )}
      </div>

      <p className="text-xs text-muted">简历仅发布者与申请人本人可见。</p>
    </section>
  );
}
