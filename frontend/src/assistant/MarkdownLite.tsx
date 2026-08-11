/* Rendu minimal et sûr (pas de dangerouslySetInnerHTML) du sous-ensemble
   Markdown produit par le prompt système du chat (backend/app/api/routes/chat.py) :
   listes à puces "- "/"* " (avec sous-puces indentées de 2 espaces) et **gras**.
   Tout le reste est affiché tel quel. */

function renderInline(text: string, keyPrefix: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>;
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>;
  });
}

export function MarkdownLite({ text }: { text: string }) {
  const lines = text.split('\n');
  const blocks: ReactBlock[] = [];

  lines.forEach((rawLine, i) => {
    const match = rawLine.match(/^(\s*)[-*]\s+(.*)$/);
    if (match) {
      const indent = match[1].length;
      blocks.push({ kind: 'bullet', nested: indent >= 2, content: match[2], key: `l${i}` });
      return;
    }
    if (rawLine.trim() === '') {
      blocks.push({ kind: 'space', content: '', key: `l${i}` });
      return;
    }
    blocks.push({ kind: 'text', content: rawLine, key: `l${i}` });
  });

  return (
    <div className="mascot-md">
      {blocks.map((b) => {
        if (b.kind === 'bullet') {
          return (
            <div key={b.key} className={b.nested ? 'mascot-md-bullet mascot-md-bullet-nested' : 'mascot-md-bullet'}>
              <span className="mascot-md-bullet-dot">{b.nested ? '·' : '•'}</span>
              <span>{renderInline(b.content, b.key)}</span>
            </div>
          );
        }
        if (b.kind === 'space') return null;
        return (
          <p key={b.key} className="mascot-md-p">
            {renderInline(b.content, b.key)}
          </p>
        );
      })}
    </div>
  );
}

type ReactBlock = { kind: 'bullet' | 'text' | 'space'; nested?: boolean; content: string; key: string };
