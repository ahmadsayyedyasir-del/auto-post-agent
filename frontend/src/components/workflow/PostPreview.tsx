import React, { useState } from 'react';
import { PostResponse } from '../../types';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Copy, Check, ExternalLink, Hash, MessageSquare, Linkedin, Twitter } from 'lucide-react';

export interface PostPreviewProps {
  post: PostResponse;
}

export const PostPreview: React.FC<PostPreviewProps> = ({ post }) => {
  const [copied, setCopied] = useState(false);

  const charLimit = post.platform.toLowerCase() === 'twitter' ? 280 : 3000;
  const charCount = post.content.length;
  const isOverLimit = charCount > charLimit;

  const handleCopy = async () => {
    let fullText = post.content;
    if (post.cta) fullText += `\n\n${post.cta}`;
    if (post.hashtags && post.hashtags.length > 0) {
      const tags = post.hashtags.map((h) => (h.startsWith('#') ? h : `#${h}`)).join(' ');
      fullText += `\n\n${tags}`;
    }

    await navigator.clipboard.writeText(fullText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card
      header={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            {post.platform.toLowerCase() === 'linkedin' ? (
              <Linkedin size={18} color="#0a66c2" />
            ) : (
              <Twitter size={18} color="#1d9bf0" />
            )}
            <span style={{ fontWeight: 700, fontSize: '0.95rem', textTransform: 'capitalize' }}>
              {post.platform} Post Draft
            </span>
          </div>
          <button
            onClick={handleCopy}
            className="btn btn-secondary btn-sm"
            style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}
            title="Copy formatted post to clipboard"
          >
            {copied ? <Check size={14} color="var(--success)" /> : <Copy size={14} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {/* Post Topic */}
        {post.topic && (
          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            <strong>Angle:</strong> {post.topic}
          </div>
        )}

        {/* Post Content Body */}
        <div
          style={{
            background: 'var(--bg-primary)',
            padding: 'var(--space-4)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-subtle)',
            whiteSpace: 'pre-wrap',
            lineHeight: 1.6,
            fontSize: '0.95rem',
            color: 'var(--text-primary)',
          }}
        >
          {post.content}
        </div>

        {/* CTA */}
        {post.cta && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              padding: 'var(--space-3)',
              background: 'var(--bg-tertiary)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.875rem',
            }}
          >
            <MessageSquare size={16} color="var(--info)" />
            <span>
              <strong>Call to Action:</strong> {post.cta}
            </span>
          </div>
        )}

        {/* Hashtags */}
        {post.hashtags && post.hashtags.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}>
            <Hash size={14} color="var(--text-muted)" />
            {post.hashtags.map((tag, i) => (
              <Badge key={i} variant="info">
                {tag.startsWith('#') ? tag : `#${tag}`}
              </Badge>
            ))}
          </div>
        )}

        {/* Character Count & Meter */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.8rem', color: isOverLimit ? 'var(--error)' : 'var(--text-muted)' }}>
          <span>
            {charCount} / {charLimit} characters
          </span>
          {isOverLimit && <span style={{ fontWeight: 600 }}>Exceeds platform maximum!</span>}
        </div>

        {/* Grounding Source References */}
        {post.source_references && post.source_references.length > 0 && (
          <div style={{ marginTop: 'var(--space-2)', borderTop: '1px solid var(--border-subtle)', paddingTop: 'var(--space-3)' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 'var(--space-2)' }}>
              VERIFIED GROUNDING SOURCES:
            </div>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              {post.source_references.map((url, idx) => (
                <li key={idx} style={{ fontSize: '0.8rem' }}>
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)', color: 'var(--accent-light)' }}
                  >
                    <ExternalLink size={12} />
                    <span style={{ textDecoration: 'underline' }}>{url}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
};
