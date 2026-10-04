// Builds a CSV file in the browser and downloads it. Opens correctly in Excel (UTF-8 BOM).
// Cells that start with = + - @ are prefixed with ' so Excel never runs citizen-typed text as a formula.
const cell = (v: unknown): string => {
  let s = v == null ? '' : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function downloadCsv(filename: string, headers: string[], rows: unknown[][]) {
  const text = [headers, ...rows].map(r => r.map(cell).join(',')).join('\r\n');
  const blob = new Blob(['\uFEFF' + text], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
