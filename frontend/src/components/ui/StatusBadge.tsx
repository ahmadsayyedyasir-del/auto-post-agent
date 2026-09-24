import React from 'react';
import { Badge } from './Badge';
import { WorkflowStatus } from '../../types';
import { CheckCircle2, Clock, PlayCircle, AlertCircle, XCircle, FileEdit, Eye } from 'lucide-react';

export interface StatusBadgeProps {
  status: WorkflowStatus | string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  const normStatus = status.toUpperCase();

  switch (normStatus) {
    case 'APPROVED':
    case 'PUBLISHED':
    case 'COMPLETED':
      return (
        <Badge variant="success" icon={<CheckCircle2 size={13} />} className={className}>
          {normStatus}
        </Badge>
      );
    case 'WAITING_FOR_HUMAN_REVIEW':
    case 'HUMAN_REVIEW':
      return (
        <Badge variant="warning" icon={<Eye size={13} />} className={className}>
          REVIEW REQUIRED
        </Badge>
      );
    case 'RESEARCHING':
    case 'PLANNING':
    case 'WRITING':
    case 'CRITIQUING':
    case 'STARTING':
    case 'PUBLISHING':
    case 'RUNNING':
      return (
        <Badge variant="info" icon={<PlayCircle size={13} />} className={className}>
          {normStatus}
        </Badge>
      );
    case 'SCHEDULED':
      return (
        <Badge variant="info" icon={<Clock size={13} />} className={className}>
          SCHEDULED
        </Badge>
      );
    case 'REVISE':
    case 'DRAFT':
    case 'IN_REVIEW':
      return (
        <Badge variant="warning" icon={<FileEdit size={13} />} className={className}>
          {normStatus}
        </Badge>
      );
    case 'REJECTED':
    case 'FAILED':
    case 'CANCELLED':
      return (
        <Badge variant="error" icon={<XCircle size={13} />} className={className}>
          {normStatus}
        </Badge>
      );
    default:
      return (
        <Badge variant="default" icon={<AlertCircle size={13} />} className={className}>
          {normStatus}
        </Badge>
      );
  }
};
