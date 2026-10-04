import React, { useState, useMemo } from 'react';
import { usePravaha } from '../context/PravahaContext';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ChevronUp, ChevronDown, Filter, ShieldCheck, AlertTriangle, AlertCircle, AlertOctagon } from 'lucide-react';

type SortCol = 'id' | 'location' | 'depth' | 'predicted' | 'risk' | null;
type SortDir = 'asc' | 'desc' | null;
type RiskFilter = 'Any' | 'Low' | 'Moderate' | 'High' | 'Critical';

export default function Nodes() {
  const { nodes } = usePravaha();
  
  const [sortCol, setSortCol] = useState<SortCol>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('Any');
  const [predTime, setPredTime] = useState<number>(0.5); // 0.5, 1, 2, 3

  const riskWeight: Record<string, number> = {
    'Critical': 5,
    'High': 4,
    'Moderate': 3,
    'Low': 2,
    'Safe': 1
  };

  const handleSort = (col: SortCol) => {
    if (sortCol === col) {
      if (sortDir === 'asc') setSortDir('desc');
      else if (sortDir === 'desc') {
        setSortCol(null);
        setSortDir(null);
      }
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  };

  const SortIcon = ({ col }: { col: SortCol }) => {
    if (sortCol !== col || sortDir === null) return <div className="w-4 h-4 opacity-20 flex flex-col items-center justify-center -space-y-1"><ChevronUp size={12} /><ChevronDown size={12} /></div>;
    return sortDir === 'asc' ? <ChevronUp size={14} className="text-teal-500" /> : <ChevronDown size={14} className="text-teal-500" />;
  };

  // Mock predicted depth based on time
  const getPredictedDepth = (depth: number, risk: string, time: number) => {
    const rate = risk === 'Critical' ? 0.3 : risk === 'High' ? 0.2 : risk === 'Moderate' ? 0.1 : 0.05;
    return depth + (rate * time);
  };

  const processedNodes = useMemo(() => {
    let filtered = nodes;
    
    // Filter
    if (riskFilter !== 'Any') {
      filtered = filtered.filter(n => n.risk === riskFilter);
    }

    // Sort
    if (!sortCol || !sortDir) return filtered;

    return [...filtered].sort((a, b) => {
      let valA: any = a.id;
      let valB: any = b.id;

      if (sortCol === 'id') {
        valA = a.id; valB = b.id;
      } else if (sortCol === 'location') {
        valA = a.location; valB = b.location;
      } else if (sortCol === 'depth') {
        valA = a.depth; valB = b.depth;
      } else if (sortCol === 'predicted') {
        valA = getPredictedDepth(a.depth, a.risk, predTime);
        valB = getPredictedDepth(b.depth, b.risk, predTime);
      } else if (sortCol === 'risk') {
        valA = riskWeight[a.risk] || 0;
        valB = riskWeight[b.risk] || 0;
      }

      if (valA < valB) return sortDir === 'asc' ? -1 : 1;
      if (valA > valB) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [nodes, sortCol, sortDir, riskFilter, predTime]);

  const riskIcon = (risk: string) => {
    if (risk === 'Critical') return <AlertOctagon size={14} className="text-red-500 inline mr-1" />;
    if (risk === 'High') return <AlertTriangle size={14} className="text-orange-500 inline mr-1" />;
    if (risk === 'Moderate') return <AlertCircle size={14} className="text-yellow-500 inline mr-1" />;
    return <ShieldCheck size={14} className="text-blue-500 inline mr-1" />;
  };

  return (
    <div className="w-full h-full p-6 overflow-y-auto">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-xl font-bold text-foreground mb-6">NODE MONITOR</h1>
        
        <div className="bg-card backdrop-blur-md rounded-xl border border-border overflow-hidden shadow-2xl">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="font-medium cursor-pointer select-none" onClick={() => handleSort('id')}>
                  <div className="flex items-center gap-1">Node ID <SortIcon col="id" /></div>
                </TableHead>
                <TableHead className="font-medium cursor-pointer select-none" onClick={() => handleSort('location')}>
                  <div className="flex items-center gap-1">Location <SortIcon col="location" /></div>
                </TableHead>
                <TableHead className="font-medium cursor-pointer select-none" onClick={() => handleSort('depth')}>
                  <div className="flex items-center gap-1">Current Depth <SortIcon col="depth" /></div>
                </TableHead>
                <TableHead className="font-medium select-none min-w-[200px]">
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1 cursor-pointer" onClick={() => handleSort('predicted')}>
                      Predicted Depth <SortIcon col="predicted" />
                    </div>
                    <select 
                      className="bg-secondary border border-border rounded px-1 py-0.5 text-xs text-foreground cursor-pointer focus:outline-none focus:border-teal-500"
                      value={predTime}
                      onChange={(e) => setPredTime(Number(e.target.value))}
                    >
                      <option value={0.5}>30 min</option>
                      <option value={1}>1 hour</option>
                      <option value={2}>2 hours</option>
                      <option value={3}>3 hours</option>
                    </select>
                  </div>
                </TableHead>
                <TableHead className="font-medium select-none">
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1 cursor-pointer" onClick={() => handleSort('risk')}>
                      Risk Level <SortIcon col="risk" />
                    </div>
                    <div className="relative flex items-center bg-secondary border border-border rounded p-1 cursor-pointer hover:bg-secondary/80 transition-colors">
                      <Filter size={14} className={riskFilter !== 'Any' ? 'text-teal-400' : 'text-muted-foreground'} />
                      <select 
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                        style={{ colorScheme: 'dark' }}
                        value={riskFilter}
                        onChange={(e) => setRiskFilter(e.target.value as RiskFilter)}
                      >
                        <option className="bg-card text-foreground" value="Any">All Risks</option>
                        <option className="bg-card text-foreground" value="Low">Low</option>
                        <option className="bg-card text-foreground" value="Moderate">Moderate</option>
                        <option className="bg-card text-foreground" value="High">High</option>
                        <option className="bg-card text-foreground" value="Critical">Critical</option>
                      </select>
                    </div>
                  </div>
                </TableHead>
                <TableHead className="font-medium">Node Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {processedNodes.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No nodes match the selected filters.</TableCell>
                </TableRow>
              )}
              {processedNodes.map((node, i) => (
                <TableRow key={node.id} className="border-border hover:bg-secondary/50">
                  <TableCell className="font-mono text-muted-foreground">{node.id}</TableCell>
                  <TableCell className="text-foreground">{node.location}</TableCell>
                  <TableCell className="font-mono text-foreground font-semibold">{node.depth.toFixed(2)} m</TableCell>
                  <TableCell className="font-mono text-teal-500 font-semibold">{getPredictedDepth(node.depth, node.risk, predTime).toFixed(2)} m</TableCell>
                  <TableCell>
                    <span className={`font-medium ${
                      node.risk === 'Critical' ? 'text-red-500' :
                      node.risk === 'High' ? 'text-orange-500' :
                      node.risk === 'Moderate' ? 'text-yellow-500' : 'text-blue-500'
                    }`}>
                      {riskIcon(node.risk)}{node.risk}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className={`font-medium ${
                      node.status === 'FLOODED' ? 'text-red-500' :
                      node.status === 'SURCHARGE' ? 'text-orange-500' : 'text-green-500'
                    }`}>{node.status}</span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
