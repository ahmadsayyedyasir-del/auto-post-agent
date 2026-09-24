import React, { HTMLAttributes, ReactNode } from 'react';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  glass?: boolean;
  header?: ReactNode;
  footer?: ReactNode;
}

export const Card: React.FC<CardProps> = ({
  children,
  glass = false,
  header,
  footer,
  className = '',
  ...props
}) => {
  const cardClass = glass ? 'card-glass' : 'card';

  return (
    <div className={`${cardClass} ${className}`} {...props}>
      {header && (
        <div style={{ paddingBottom: 'var(--space-4)', borderBottom: '1px solid var(--border-subtle)', marginBottom: 'var(--space-4)' }}>
          {header}
        </div>
      )}
      <div>{children}</div>
      {footer && (
        <div style={{ paddingTop: 'var(--space-4)', borderTop: '1px solid var(--border-subtle)', marginTop: 'var(--space-4)' }}>
          {footer}
        </div>
      )}
    </div>
  );
};
