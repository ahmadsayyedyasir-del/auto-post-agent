import React, { HTMLAttributes, ReactNode } from 'react';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'info' | 'success' | 'warning' | 'error' | 'default';
  icon?: ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  icon,
  className = '',
  ...props
}) => {
  return (
    <span className={`badge badge-${variant} ${className}`} {...props}>
      {icon}
      <span>{children}</span>
    </span>
  );
};
