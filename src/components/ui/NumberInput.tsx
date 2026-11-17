import { clsx } from 'clsx';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useEffect, useState } from 'react';
import { inputBase } from './Field';

interface NumberInputProps {
  value: number | null;
  onChange: (value: number | null) => void;
  min?: number;
  max?: number;
  placeholder?: string;
  invalid?: boolean;
  disabled?: boolean;
  className?: string;
  id?: string;
  'aria-label'?: string;
}

/** 只保留数字并去掉前导零：`01111` → `1111`，`0` → `0` */
function sanitize(raw: string): string {
  const digits = raw.replace(/\D/g, '');
  return digits.replace(/^0+(?=\d)/, '');
}

/**
 * 整数输入框（人数、数量一类）。
 *
 * 原生 `type="number"` 在删除全部内容时会强制回填 0，导致「0 删不掉」，
 * 且允许输入 `01`、`02` 这样的前导零，观感不好。这里用受控的文本输入：
 * - 允许完全清空（对外表现为 null），不会自动变 0；
 * - 非法字符（e、+、-、小数点、中文）直接忽略；
 * - 前导零实时去掉；
 * - 失焦时把小于下限的值收敛到下限，超过上限则保留原值交给校验提示。
 */
export function NumberInput({
  value,
  onChange,
  min,
  max,
  placeholder,
  invalid,
  disabled,
  className,
  id,
  'aria-label': ariaLabel,
}: NumberInputProps) {
  const [text, setText] = useState(() => (value == null ? '' : String(value)));

  // 外部值变化（编辑页回填、表单重置）时同步文本；用户输入过程中不回写，避免光标跳动
  useEffect(() => {
    const current = text === '' ? null : Number(text);
    if (current !== value) setText(value == null ? '' : String(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const emit = (next: string) => {
    setText(next);
    onChange(next === '' ? null : Number(next));
  };

  const clampOnBlur = () => {
    if (text === '') return;
    const parsed = Number(text);
    // 过小的值收敛到下限，避免留下 0；超过上限时保留用户输入，由校验提示具体限制
    if (min != null && parsed < min) emit(String(min));
  };

  const step = (delta: number) => {
    if (disabled) return;
    const base = text === '' ? (min != null ? min - delta : 0) : Number(text);
    let next = base + delta;
    if (min != null) next = Math.max(min, next);
    if (max != null) next = Math.min(max, next);
    emit(String(next));
  };

  return (
    <div className={clsx('relative', className)}>
      <input
        id={id}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        aria-label={ariaLabel}
        value={text}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => emit(sanitize(e.target.value))}
        onBlur={clampOnBlur}
        className={clsx(inputBase, 'pr-10', invalid && 'border-danger')}
      />
      {!disabled && (
        <div className="absolute inset-y-1 right-1 flex w-6 flex-col overflow-hidden rounded-sm border border-line bg-surface">
          <button
            type="button"
            tabIndex={-1}
            aria-label="增加"
            onClick={() => step(1)}
            className="flex flex-1 items-center justify-center text-muted transition-colors hover:bg-muted-soft hover:text-ink"
          >
            <ChevronUp size={12} />
          </button>
          <button
            type="button"
            tabIndex={-1}
            aria-label="减少"
            onClick={() => step(-1)}
            className="flex flex-1 items-center justify-center border-t border-line text-muted transition-colors hover:bg-muted-soft hover:text-ink"
          >
            <ChevronDown size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
