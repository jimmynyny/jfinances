import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { cx } from "../lib/format";

interface FieldChrome {
  label?: ReactNode;
  help?: ReactNode;
  error?: ReactNode;
  className?: string;
}

function Chrome({ id, label, help, error, className, children }: FieldChrome & { id: string; children: ReactNode }) {
  return (
    <div className={cx("mu-field", className)}>
      {label && (
        <label className="mu-label" htmlFor={id}>
          {label}
        </label>
      )}
      {children}
      {error ? <div className="mu-help mu-help--error">{error}</div> : help ? <div className="mu-help">{help}</div> : null}
    </div>
  );
}

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "className">, FieldChrome {
  mono?: boolean;
  inputClassName?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, help, error, className, mono, inputClassName, id: idProp, ...rest },
  ref,
) {
  const auto = useId();
  const id = idProp ?? auto;
  return (
    <Chrome id={id} label={label} help={help} error={error} className={className}>
      <input
        ref={ref}
        id={id}
        className={cx("mu-input", mono && "mu-input--mono", inputClassName)}
        aria-invalid={error ? true : undefined}
        {...rest}
      />
    </Chrome>
  );
});

export interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "className">, FieldChrome {}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, help, error, className, id: idProp, ...rest },
  ref,
) {
  const auto = useId();
  const id = idProp ?? auto;
  return (
    <Chrome id={id} label={label} help={help} error={error} className={className}>
      <textarea ref={ref} id={id} className="mu-textarea" aria-invalid={error ? true : undefined} {...rest} />
    </Chrome>
  );
});

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

/** A labelled run of options: a native <optgroup>, for long lists that sort into kinds. */
export interface SelectGroup {
  group: string;
  options: SelectOption[];
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "className">, FieldChrome {
  /** Options, or labelled groups of them. */
  options: Array<SelectOption | SelectGroup>;
  placeholder?: string;
}

function renderOption(o: SelectOption) {
  return (
    <option key={o.value} value={o.value} disabled={o.disabled}>
      {o.label}
    </option>
  );
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, help, error, className, options, placeholder, id: idProp, ...rest },
  ref,
) {
  const auto = useId();
  const id = idProp ?? auto;
  return (
    <Chrome id={id} label={label} help={help} error={error} className={className}>
      <select ref={ref} id={id} className="mu-select" aria-invalid={error ? true : undefined} {...rest}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) =>
          "group" in o ? (
            <optgroup key={`group:${o.group}`} label={o.group}>
              {o.options.map(renderOption)}
            </optgroup>
          ) : (
            renderOption(o)
          ),
        )}
      </select>
    </Chrome>
  );
});

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "className"> {
  label: ReactNode;
  className?: string;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox({ label, className, ...rest }, ref) {
  return (
    <label className={cx("mu-check", className)}>
      <input ref={ref} type="checkbox" {...rest} />
      <span>{label}</span>
    </label>
  );
});
