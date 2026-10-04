import React, { useMemo, useState } from 'react';
import { Node } from '../types';

export interface PickedPlace {
  text: string;                    // what goes into the input box after picking
  label: string;                   // what the list shows
  coords: [number, number];        // [lat, lng]
  nodeId: string;
}

interface Props {
  nodes: Node[];
  mode: 'node' | 'location';       // node: search by node ID or street; location: search by street/place name
  value: string;
  onChange: (text: string) => void;
  onPick: (p: PickedPlace) => void;
  onFocus?: () => void;
  placeholder?: string;
  inputClassName: string;
  variant?: 'light' | 'dark';
}

const MAX_ROWS = 60;

// Text box with a drop-down list: type to filter, or open the list and click an entry.
export default function PlacePicker({ nodes, mode, value, onChange, onPick, onFocus, placeholder, inputClassName, variant = 'light' }: Props) {
  const [open, setOpen] = useState(false);
  const q = value.trim().toLowerCase();

  const options = useMemo(() => {
    const out: PickedPlace[] = [];
    const seen = new Set<string>();
    for (const n of nodes) {
      const loc = (n.location || '').trim();
      if (mode === 'node') {
        if (q && !n.id.toLowerCase().includes(q) && !loc.toLowerCase().includes(q)) continue;
        out.push({ text: n.id, label: loc ? `${n.id}  -  ${loc}` : n.id, coords: n.coordinates, nodeId: n.id });
      } else {
        const key = loc.toLowerCase();
        if (!loc || seen.has(key)) continue;
        if (q && !key.includes(q)) continue;
        seen.add(key);
        out.push({ text: loc, label: loc, coords: n.coordinates, nodeId: n.id });
      }
      if (out.length >= 400) break;
    }
    if (mode === 'location') out.sort((a, b) => a.label.localeCompare(b.label));
    return out.slice(0, MAX_ROWS);
  }, [nodes, mode, q]);

  const listCls = variant === 'light'
    ? 'bg-white border border-slate-200 text-slate-700'
    : 'bg-popover border border-border text-popover-foreground';
  const itemCls = variant === 'light' ? 'hover:bg-teal-50' : 'hover:bg-secondary';

  return (
    <div className="relative">
      <input
        type="text"
        autoComplete="off"
        placeholder={placeholder}
        className={inputClassName}
        value={value}
        onChange={(e) => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => { setOpen(true); onFocus?.(); }}
        onBlur={() => setOpen(false)}
      />
      {open && (
        <ul className={`absolute left-0 right-0 mt-1 max-h-52 overflow-y-auto rounded-lg shadow-xl z-[1000] text-sm ${listCls}`}>
          {options.length === 0 && <li className="px-3 py-2 opacity-60">No match</li>}
          {options.map((o) => (
            <li
              key={o.nodeId + o.label}
              className={`px-3 py-2 cursor-pointer truncate ${itemCls}`}
              onMouseDown={(e) => { e.preventDefault(); onPick(o); setOpen(false); }}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
