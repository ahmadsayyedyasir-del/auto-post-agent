import React, { useState, FormEvent } from 'react';
import { ResearchRequest } from '../../types';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Sparkles, Compass, Zap } from 'lucide-react';

export interface WorkflowFormProps {
  onSubmit: (data: ResearchRequest) => Promise<void>;
  isLoading?: boolean;
}

export const WorkflowForm: React.FC<WorkflowFormProps> = ({ onSubmit, isLoading = false }) => {
  const [niche, setNiche] = useState('');
  const [autoDiscover, setAutoDiscover] = useState(false);
  const [platform, setPlatform] = useState('linkedin');
  const [audience, setAudience] = useState('Tech Founders & Engineers');
  const [language, setLanguage] = useState('English');
  const [maxTrends, setMaxTrends] = useState(3);
  const [daysBack, setDaysBack] = useState(7);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!autoDiscover && !niche.trim()) {
      setError('Please provide a research niche/topic, or enable AI auto-discovery.');
      return;
    }
    setError(null);

    await onSubmit({
      niche: niche.trim() || undefined,
      auto_discover: autoDiscover,
      platform,
      audience: audience.trim(),
      language,
      max_trends: Number(maxTrends),
      days_back: Number(daysBack),
    });
  };

  return (
    <Card header={<h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Configure Generation Workflow</h3>}>
      <form onSubmit={handleSubmit}>
        <Input
          label="Research Niche / Topic Keywords"
          placeholder={autoDiscover ? 'Optional — AI will discover a trending topic' : 'e.g., Autonomous AI Agents in Enterprise Software'}
          value={niche}
          onChange={(e) => setNiche(e.target.value)}
          error={error || undefined}
          helperText={autoDiscover
            ? 'Leave empty for AI auto-discovery, or enter a topic to focus the research.'
            : 'The Research Agent will search real-time web trends and grounding sources for this niche.'
          }
          leftIcon={<Compass size={18} />}
          required={!autoDiscover}
        />

        {/* Auto-discovery toggle */}
        <label
          htmlFor="auto-discover-toggle"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-3)',
            cursor: 'pointer',
            padding: 'var(--space-3) var(--space-4)',
            marginTop: 'var(--space-2)',
            marginBottom: 'var(--space-4)',
            background: autoDiscover ? 'rgba(99, 102, 241, 0.08)' : 'var(--bg-secondary)',
            border: autoDiscover ? '1px solid rgba(99, 102, 241, 0.3)' : '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)',
            transition: 'all var(--transition-fast)',
          }}
        >
          <input
            id="auto-discover-toggle"
            type="checkbox"
            checked={autoDiscover}
            onChange={(e) => {
              setAutoDiscover(e.target.checked);
              if (e.target.checked) setError(null);
            }}
            style={{ accentColor: 'var(--accent-primary)', width: '18px', height: '18px' }}
          />
          <Zap size={18} color={autoDiscover ? 'var(--accent-primary)' : 'var(--text-muted)'} />
          <div>
            <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>
              Let AI discover a trending topic automatically
            </span>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              The Research Agent will search current trends based on your platform, audience, and language to find the best topic.
            </p>
          </div>
        </label>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-4)' }}>
          <Select
            label="Target Social Platform"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            options={[
              { label: 'LinkedIn (Professional Post)', value: 'linkedin' },
              { label: 'Twitter / X (Short Post)', value: 'twitter' },
            ]}
          />

          <Select
            label="Content Language"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            options={[
              { label: 'English', value: 'English' },
              { label: 'Spanish', value: 'Spanish' },
              { label: 'German', value: 'German' },
              { label: 'French', value: 'French' },
            ]}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-4)', marginTop: 'var(--space-3)' }}>
          <Input
            label="Target Audience Persona"
            value={audience}
            onChange={(e) => setAudience(e.target.value)}
            placeholder="e.g., Marketing Leaders, Founders"
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
            <Select
              label="Max Trends"
              value={String(maxTrends)}
              onChange={(e) => setMaxTrends(Number(e.target.value))}
              options={[
                { label: '1 Trend', value: '1' },
                { label: '2 Trends', value: '2' },
                { label: '3 Trends', value: '3' },
                { label: '5 Trends', value: '5' },
              ]}
            />
            <Select
              label="Search Window"
              value={String(daysBack)}
              onChange={(e) => setDaysBack(Number(e.target.value))}
              options={[
                { label: 'Past 24 Hours', value: '1' },
                { label: 'Past 7 Days', value: '7' },
                { label: 'Past 14 Days', value: '14' },
                { label: 'Past 30 Days', value: '30' },
              ]}
            />
          </div>
        </div>

        <div style={{ marginTop: 'var(--space-6)', display: 'flex', justifyContent: 'flex-end' }}>
          <Button type="submit" variant="primary" isLoading={isLoading} leftIcon={<Sparkles size={18} />}>
            {autoDiscover && !niche.trim() ? 'Discover & Generate' : 'Launch Multi-Agent Pipeline'}
          </Button>
        </div>
      </form>
    </Card>
  );
};
