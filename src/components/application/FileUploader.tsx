import { FileText, UploadCloud, X } from 'lucide-react';
import { useRef, useState } from 'react';
import { clsx } from 'clsx';
import { fileSizeLabel, validateResumeFile } from '@/domain/validation';

interface FileUploaderProps {
  value: File | null;
  onChange: (file: File | null) => void;
}

/** 拖拽 + 点击上传，选择瞬间即校验格式/大小 */
export function FileUploader({ value, onChange }: FileUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = (file: File | undefined | null) => {
    if (!file) return;
    const err = validateResumeFile(file);
    if (err) {
      setError(err);
      onChange(null);
      return;
    }
    setError(null);
    onChange(file);
  };

  return (
    <div className="flex flex-col gap-2">
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.doc,.docx"
        className="hidden"
        onChange={(e) => pick(e.target.files?.[0])}
      />

      {!value ? (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            pick(e.dataTransfer.files?.[0]);
          }}
          className={clsx(
            'flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors',
            dragOver ? 'border-primary bg-primary-soft' : 'border-line hover:border-primary hover:bg-page',
          )}
        >
          <UploadCloud className="h-8 w-8 text-muted" />
          <span className="text-sm font-medium text-ink">点击或拖拽上传简历文件</span>
          <span className="text-xs text-ink2">仅支持 PDF / DOC / DOCX，文件上限 10MB</span>
        </button>
      ) : (
        <div className="flex items-center gap-3 rounded-lg border border-line bg-page px-4 py-3">
          <FileText className="h-6 w-6 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-ink">{value.name}</p>
            <p className="text-xs text-ink2">{fileSizeLabel(value.size)}</p>
          </div>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="shrink-0 text-sm font-medium text-primary hover:underline"
          >
            更换文件
          </button>
          <button
            type="button"
            onClick={() => {
              onChange(null);
              setError(null);
            }}
            className="shrink-0 rounded p-1 text-muted hover:bg-surface hover:text-danger"
            aria-label="移除文件"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}
