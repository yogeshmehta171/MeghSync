import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { LegalDoc } from '../lib/legal';

// The text of a legal document: a heading and a paragraph per section.
export function LegalBody({ doc }: { doc: LegalDoc }) {
  return (
    <div className="space-y-6">
      {doc.sections.map(s => (
        <section key={s.heading}>
          <h3 className="text-base font-bold text-slate-800 mb-1.5">{s.heading}</h3>
          <p className="text-sm text-slate-600 leading-relaxed">{s.body}</p>
        </section>
      ))}
    </div>
  );
}

// Pop-up that scrolls inside itself. Closes with the X, the Close button, a click outside, or Esc.
export default function LegalModal({ doc, onClose }: { doc: LegalDoc; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';   // page behind does not scroll
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[3000] flex items-center justify-center bg-black/60 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label={doc.title} className="w-full max-w-2xl max-h-[85vh] flex flex-col bg-white rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 shrink-0">
          <h2 className="text-xl font-extrabold text-slate-800">{doc.title}</h2>
          <button onClick={onClose} aria-label="Close" className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800 transition-colors"><X size={20} /></button>
        </div>
        <div className="px-6 py-5 overflow-y-auto">
          <LegalBody doc={doc} />
        </div>
        <div className="px-6 py-3 border-t border-slate-200 flex justify-end shrink-0 bg-slate-50">
          <button onClick={onClose} className="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium transition-colors">Close</button>
        </div>
      </div>
    </div>
  );
}
