import React, { useState } from 'react';
import { usePravaha } from '../context/PravahaContext';
import { format, isToday, isYesterday } from 'date-fns';
import { Download } from 'lucide-react';
import { downloadCsv } from '../lib/csv';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type LogTab = 'ALL' | 'PENDING' | 'COMPLETED' | 'REJECTED';
type Section = 'REPORTS' | 'SYSTEM';

// APPROVE_REPORT -> Approve Report (the server keeps the code, people see words)
const actionLabel = (a: string) => a.toLowerCase().split('_').filter(Boolean).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

export default function Logs() {
  const { logs } = usePravaha();
  const [activeTab, setActiveTab] = useState<LogTab>('ALL');

  const [section, setSection] = useState<Section>('REPORTS');

  // Report decisions (approve / reject / resolve) are kept apart from simulation, block and settings actions.
  const isReportLog = (l: { action: string }) => l.action.includes('REPORT');
  const sectionLogs = logs.filter(l => (section === 'REPORTS' ? isReportLog(l) : !isReportLog(l)));
  const tab: LogTab = section === 'REPORTS' ? activeTab : 'ALL';       // status filter only applies to report decisions
  const filteredLogs = tab === 'ALL' ? sectionLogs : sectionLogs.filter(log => log.status === tab);

  // Exports exactly what is on screen: this section, with the status filter applied, newest first.
  const exportCsv = () => {
    const name = section === 'REPORTS' ? 'report-log' : 'system-log';
    const withMeasures = section === 'REPORTS';
    const rows = [...filteredLogs].reverse().map(l => [
      format(new Date(l.timestamp), 'yyyy-MM-dd HH:mm:ss'), l.officialId, l.refId, actionLabel(l.action), l.status ?? '', l.description,
      ...(withMeasures ? [l.measures ?? ''] : []),
    ]);
    downloadCsv(`meghsync-${name}-${format(new Date(), 'yyyy-MM-dd')}.csv`,
      ['Timestamp', 'Official ID', 'Ref ID', 'Action', 'Status', 'Description', ...(withMeasures ? ['Measures'] : [])], rows);
  };

  const cols = section === 'REPORTS' ? 6 : 5;

  const dayLabel = (iso: string) => {
    const d = new Date(iso);
    return isToday(d) ? 'Today' : isYesterday(d) ? 'Yesterday' : format(d, 'EEEE, d MMM yyyy');
  };

  return (
    <div className="w-full h-full p-6 overflow-y-auto">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-end mb-6">
          <div>
            <h1 className="text-xl font-bold text-foreground mb-3">{section === 'REPORTS' ? 'ACTIVITY LOG' : 'SYSTEM & SIMULATION LOG'}</h1>
            <div className="flex gap-2">
              {([['REPORTS', 'Citizen Report'], ['SYSTEM', 'System & Simulation']] as [Section, string][]).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setSection(key)}
                  className={`px-4 py-1.5 rounded-lg text-xs font-bold border transition-colors ${section === key ? 'bg-teal-600 text-white border-teal-600' : 'text-muted-foreground border-border hover:text-foreground hover:bg-secondary/80'}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
          <button
            onClick={exportCsv}
            disabled={filteredLogs.length === 0}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold border border-border text-foreground hover:bg-secondary/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Download the entries shown below as a CSV file"
          >
            <Download size={14} /> Export CSV
          </button>
          {section === 'REPORTS' && <div className="flex gap-2 bg-card border border-border p-1 rounded-xl shadow-sm">
            {(['ALL', 'PENDING', 'COMPLETED', 'REJECTED'] as LogTab[]).map(tab => (
              <button 
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                  activeTab === tab 
                    ? tab === 'ALL' ? 'bg-teal-500/20 text-teal-400' :
                      tab === 'PENDING' ? 'bg-orange-500/20 text-orange-400' :
                      tab === 'COMPLETED' ? 'bg-green-500/20 text-green-400' :
                      'bg-red-500/20 text-red-400'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary/80'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>}
          </div>
        </div>
        
        <div className="bg-card backdrop-blur-md rounded-xl border border-border overflow-hidden shadow-2xl">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="font-medium">Timestamp</TableHead>
                <TableHead className="font-medium">ID</TableHead>
                <TableHead className="font-medium">Ref ID</TableHead>
                <TableHead className="font-medium">Action</TableHead>
                <TableHead className="font-medium">Description</TableHead>
                {section === 'REPORTS' && <TableHead className="font-medium">Measures</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredLogs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={cols} className="text-center py-8 text-muted-foreground">
                    No {tab === 'ALL' ? '' : tab.toLowerCase() + ' '}entries in this log.
                  </TableCell>
                </TableRow>
              )}
              {[...filteredLogs].reverse().map((log, i, arr) => (
                <React.Fragment key={i}>
                {(i === 0 || dayLabel(arr[i - 1].timestamp) !== dayLabel(log.timestamp)) && (
                  <TableRow className="border-border bg-secondary/40 hover:bg-secondary/40">
                    <TableCell colSpan={cols} className="py-2 text-xs font-bold uppercase tracking-wider text-teal-400">{dayLabel(log.timestamp)}</TableCell>
                  </TableRow>
                )}
                <TableRow className="border-border hover:bg-secondary/50 transition">
                  <TableCell className="font-mono text-muted-foreground text-xs">{format(new Date(log.timestamp), 'yyyy-MM-dd HH:mm:ss')}</TableCell>
                  <TableCell className="font-mono text-foreground">{log.officialId}</TableCell>
                  <TableCell className="font-mono text-teal-400">{log.refId}</TableCell>
                  <TableCell><span className="px-2 py-0.5 rounded bg-secondary border border-border text-xs font-bold text-foreground">{actionLabel(log.action)}</span></TableCell>
                  <TableCell className="text-muted-foreground">{log.description}</TableCell>
                  {section === 'REPORTS' && (
                    <TableCell className="text-foreground text-sm max-w-xs whitespace-pre-wrap break-words">
                      {log.measures ? log.measures : <span className="text-muted-foreground">-</span>}
                    </TableCell>
                  )}
                </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
