import React, { useState } from 'react';
import { RevisionResponse } from '../../types';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Select } from '../ui/Select';
import { diffWords } from 'diff';
import { History, GitCompare } from 'lucide-react';

export interface RevisionDiffProps {
  revisions: RevisionResponse[];
}

export const RevisionDiff: React.FC<RevisionDiffProps> = ({ revisions }) => {
  if (!revisions || revisions.length === 0) {
    return (
      <Card header={<h3 style={{ fontSize: '0.95rem', fontWeight: 700 }}>Revision History</h3>}>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          No historical revisions recorded.
        </div>
      </Card>
    );
  }

  const [fromRevIndex, setFromRevIndex] = useState<number>(0);
  const [toRevIndex, setToRevIndex] = useState<number>(Math.max(0, revisions.length - 1));

  const fromRev = revisions[fromRevIndex];
  const toRev = revisions[toRevIndex];

  const diffChunks = fromRev && toRev ? diffWords(fromRev.content, toRev.content) : [];

  const revisionOptions = revisions.map((r, idx) => ({
    label: `Rev #${r.revision_number} (${r.revision_source})`,
    value: String(idx),
  }));

  return (
    <Card
      header={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <History size={18} color="var(--accent-light)" />
            <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>
              Revision History & Diff ({revisions.length} versions)
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <GitCompare size={16} color="var(--text-muted)" />
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Compare Versions</span>
          </div>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {/* Revision Selectors */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
          <Select
            label="Base Version (Original)"
            value={String(fromRevIndex)}
            onChange={(e) => setFromRevIndex(Number(e.target.value))}
            options={revisionOptions}
          />
          <Select
            label="Target Version (Updated)"
            value={String(toRevIndex)}
            onChange={(e) => setToRevIndex(Number(e.target.value))}
            options={revisionOptions}
          />
        </div>

        {/* Selected revision metadata */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
          <div>
            Comparing <strong>Rev #{fromRev?.revision_number}</strong> with{' '}
            <strong>Rev #{toRev?.revision_number}</strong>
          </div>
          {toRev && (
            <Badge variant={toRev.revision_source === 'HUMAN' ? 'info' : 'default'}>
              Source: {toRev.revision_source}
            </Badge>
          )}
        </div>

        {/* Diff Result Box */}
        <div className="diff-container">
          {diffChunks.map((part, index) => {
            if (part.added) {
              return (
                <span key={index} className="diff-added">
                  {part.value}
                </span>
              );
            }
            if (part.removed) {
              return (
                <span key={index} className="diff-removed">
                  {part.value}
                </span>
              );
            }
            return <span key={index}>{part.value}</span>;
          })}
        </div>

        {/* Target Revision Feedback */}
        {toRev?.revision_feedback && toRev.revision_feedback.length > 0 && (
          <div style={{ background: 'var(--bg-tertiary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem' }}>
            <strong>Addressed Feedback:</strong>
            <ul style={{ paddingLeft: 'var(--space-4)', marginTop: 'var(--space-1)' }}>
              {toRev.revision_feedback.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
};
