import React, { useEffect, useState } from 'react';
import { usePravaha } from '../context/PravahaContext';
import ApproveReportDialog from '../components/ApproveReportDialog';
import CountBadge from '../components/CountBadge';
import { Download } from 'lucide-react';
import { downloadCsv } from '../lib/csv';
import { format } from 'date-fns';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// The officer types the measures taken against a report. Saved on the server (and written to the activity log).
// The box keeps what is being typed even though the table refreshes every few seconds.
function MeasuresCell({ report, onSave }: { report: any; onSave: (text: string) => Promise<void> }) {
  const saved: string = report.measures ?? '';
  const [text, setText] = useState(saved);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const dirty = text.trim() !== saved.trim();
  useEffect(() => { if (!dirty) setText(saved); }, [saved]);          // pick up changes made elsewhere, but never overwrite a draft

  const save = async () => {
    if (!dirty || busy) return;
    setBusy(true); setErr(null);
    try { await onSave(text.trim()); } catch (e: any) { setErr(e?.message ?? 'Could not save'); } finally { setBusy(false); }
  };

  return (
    <div className="w-60">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); save(); } }}
        rows={2}
        maxLength={1000}
        placeholder="Type the measures taken..."
        className="w-full bg-secondary border border-border rounded-lg px-2 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-teal-500 resize-y"
      />
      <div className="flex items-center justify-between mt-1 min-h-[20px]">
        <span className="text-[10px] text-muted-foreground">
          {report.measuresBy && !dirty ? `Saved by ${report.measuresBy}${report.measuresAt ? ', ' + format(new Date(report.measuresAt), 'PP p') : ''}` : (dirty ? 'Not saved yet' : '')}
        </span>
        {dirty && (
          <button onClick={save} disabled={busy} className="px-2 py-0.5 rounded bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-white text-[11px] font-medium">
            {busy ? 'Saving...' : 'Save'}
          </button>
        )}
      </div>
      {err && <div className="text-[10px] text-red-400">{err}</div>}
    </div>
  );
}

export default function Reports() {
  const { reports, nodes, approveReport, rejectReport, saveMeasures } = usePravaha();
  const [approving, setApproving] = useState<any | null>(null);
  const pending = reports.filter(r => r.status === 'PENDING').length;

  const exportCsv = () => {
    const rows = reports.map(r => [
      r.id, format(new Date(r.timestamp), 'yyyy-MM-dd HH:mm:ss'), r.name, r.phone, r.location, r.description, r.status,
      (r as any).matchedNodeId ?? '', r.measures ?? '', r.measuresBy ?? '', r.measuresAt ? format(new Date(r.measuresAt), 'yyyy-MM-dd HH:mm:ss') : '',
    ]);
    downloadCsv(`meghsync-citizen-reports-${format(new Date(), 'yyyy-MM-dd')}.csv`,
      ['Report ID', 'Reported At', 'Reporter', 'Phone', 'Location', 'Description', 'Status', 'Node', 'Measures Taken', 'Measures By', 'Measures Updated'], rows);
  };

  return (
    <div className="w-full h-full p-6 overflow-y-auto">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold text-foreground flex items-center gap-3">CITIZEN REPORT <CountBadge count={pending} className="!h-5 !min-w-[20px] !text-xs" /></h1>
          <button onClick={exportCsv} disabled={reports.length === 0} title="Download all reports, including measures taken, as a CSV file"
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold border border-border text-foreground hover:bg-secondary/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
            <Download size={14} /> Export CSV
          </button>
        </div>
        
        <div className="bg-card backdrop-blur-md rounded-xl border border-border overflow-hidden shadow-2xl">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="font-medium">Report ID</TableHead>
                <TableHead className="font-medium">Reporter</TableHead>
                <TableHead className="font-medium">Location</TableHead>
                <TableHead className="font-medium">Description</TableHead>
                <TableHead className="font-medium">Status</TableHead>
                <TableHead className="font-medium">Measures</TableHead>
                <TableHead className="font-medium text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reports.map(report => (
                <TableRow key={report.id} className="border-border hover:bg-secondary/50">
                  <TableCell>
                    <div className="font-bold text-foreground">{report.id}</div>
                    <div className="text-[10px] text-muted-foreground">{format(new Date(report.timestamp), 'PP')}</div>
                  </TableCell>
                  <TableCell>
                    <div className="text-foreground">{report.name}</div>
                    <div className="text-xs text-muted-foreground">{report.phone}</div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{report.location}</TableCell>
                  <TableCell>
                    <div className="max-w-[200px] truncate text-muted-foreground italic">"{report.description}"</div>
                  </TableCell>
                  <TableCell>
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                      report.status === 'PENDING' ? 'bg-orange-500/20 text-orange-400' :
                      report.status === 'APPROVED' ? 'bg-green-500/20 text-green-400' :
                      report.status === 'REJECTED' ? 'bg-red-500/20 text-red-400' :
                      'bg-secondary text-muted-foreground border border-border'
                    }`}>{report.status}</span>
                  </TableCell>
                  <TableCell>
                    <MeasuresCell report={report} onSave={(t) => saveMeasures(report.id, t)} />
                  </TableCell>
                  <TableCell className="text-right">
                    {report.status === 'PENDING' && (
                      <div className="flex gap-2 justify-end">
                        <button 
                          onClick={() => rejectReport(report.id).catch((e: any) => window.alert(e?.message ?? 'Could not reject'))}
                          className="px-3 py-1 rounded bg-secondary hover:bg-destructive/20 hover:text-destructive text-foreground font-medium text-xs transition border border-border"
                        >
                          Reject
                        </button>
                        <button 
                          onClick={() => setApproving(report)} 
                          className="px-3 py-1 rounded bg-teal-600 hover:bg-teal-500 text-foreground font-medium text-xs transition shadow-lg shadow-teal-500/20"
                        >
                          Approve
                        </button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {reports.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">
                    No reports to display.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
      {approving && (
        <ApproveReportDialog
          report={approving}
          nodes={nodes}
          onCancel={() => setApproving(null)}
          onConfirm={async (nodeId) => { await approveReport(approving.id, nodeId); setApproving(null); }}
        />
      )}
    </div>
  );
}
