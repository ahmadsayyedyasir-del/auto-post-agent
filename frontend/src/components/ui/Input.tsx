import React, { InputHTMLAttributes, TextareaHTMLAttributes, SelectHTMLAttributes, ReactNode } from 'react';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: ReactNode;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  helperText,
  leftIcon,
  className = '',
  id,
  ...props
}) => {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className="form-group">
      {label && (
        <label htmlFor={inputId} className="form-label">
          {label}
        </label>
      )}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
        {leftIcon && (
          <div
            style={{
              position: 'absolute',
              left: '12px',
              color: 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              pointerEvents: 'none',
            }}
          >
            {leftIcon}
          </div>
        )}
        <input
          id={inputId}
          className={`form-input ${className}`}
          style={{
            width: '100%',
            paddingLeft: leftIcon ? '38px' : '0.9rem',
            borderColor: error ? 'var(--error)' : undefined,
          }}
          {...props}
        />
      </div>
      {error && <span style={{ color: 'var(--error)', fontSize: '0.8rem' }}>{error}</span>}
      {helperText && !error && (
        <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{helperText}</span>
      )}
    </div>
  );
};

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Textarea: React.FC<TextareaProps> = ({
  label,
  error,
  helperText,
  className = '',
  id,
  ...props
}) => {
  const textareaId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className="form-group">
      {label && (
        <label htmlFor={textareaId} className="form-label">
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        className={`form-textarea ${className}`}
        style={{
          width: '100%',
          borderColor: error ? 'var(--error)' : undefined,
        }}
        {...props}
      />
      {error && <span style={{ color: 'var(--error)', fontSize: '0.8rem' }}>{error}</span>}
      {helperText && !error && (
        <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{helperText}</span>
      )}
    </div>
  );
};

export interface SelectOption {
  label: string;
  value: string;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: SelectOption[];
  error?: string;
  helperText?: string;
}

export const Select: React.FC<SelectProps> = ({
  label,
  options,
  error,
  helperText,
  className = '',
  id,
  ...props
}) => {
  const selectId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className="form-group">
      {label && (
        <label htmlFor={selectId} className="form-label">
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={`form-select ${className}`}
        style={{
          width: '100%',
          borderColor: error ? 'var(--error)' : undefined,
        }}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && <span style={{ color: 'var(--error)', fontSize: '0.8rem' }}>{error}</span>}
      {helperText && !error && (
        <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{helperText}</span>
      )}
    </div>
  );
};
