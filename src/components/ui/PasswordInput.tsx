import { clsx } from 'clsx';
import { Eye, EyeOff } from 'lucide-react';
import type { InputHTMLAttributes } from 'react';
import { useState } from 'react';
import { inputBase } from './Field';

interface PasswordInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  invalid?: boolean;
}

/**
 * 密码输入框：右侧「小眼睛」常驻。
 *
 * 之前只在输入过程中渲染按钮，一旦失焦（切换输入格）按钮就消失，
 * 回到密码格继续输入、甚至全选替换都不会重新出现，只能清空重来。
 * 这里把按钮做成始终存在的元素，只根据是否聚焦/有内容调整颜色，
 * 因此切换、粘贴、浏览器自动填充、全选替换都能保持可见。
 */
export function PasswordInput({ invalid, className, ...rest }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const [focused, setFocused] = useState(false);

  const hasValue = String(rest.value ?? '').length > 0;
  const emphasized = focused || hasValue;

  return (
    <div className="relative">
      <input
        {...rest}
        type={visible ? 'text' : 'password'}
        className={clsx(inputBase, 'pr-11', invalid && 'border-danger', className)}
        onFocus={(e) => {
          setFocused(true);
          rest.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          rest.onBlur?.(e);
        }}
      />
      <button
        type="button"
        // 阻止默认的焦点转移：点眼睛不会让输入框失焦，光标位置也保持不变
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? '隐藏密码' : '显示密码'}
        aria-pressed={visible}
        title={visible ? '隐藏密码' : '显示密码'}
        className={clsx(
          'absolute inset-y-0 right-1 my-auto flex h-8 w-8 items-center justify-center rounded-md transition-colors',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
          emphasized ? 'text-ink2 hover:bg-muted-soft hover:text-ink' : 'text-muted/60 hover:text-ink2',
        )}
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}
