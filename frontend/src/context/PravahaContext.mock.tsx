import React, { createContext, useContext, useState, ReactNode } from 'react';
import { Node, Report, Log, RiskLevel, NodeStatus } from '../types';

interface PravahaContextType {
  nodes: Node[];
  reports: Report[];
  logs: Log[];
  addReport: (report: Omit<Report, 'id' | 'status' | 'timestamp'>) => void;
  approveReport: (reportId: string, nodeId: string) => void;
  rejectReport: (reportId: string) => void;
  setRainfall: (mmHr: number) => void;
  rainfall: number;
  forecastHour: number;
  setForecastHour: (hour: number) => void;
}

const mockNodes: Node[] = [
  { id: 'N104', location: 'T. Nagar', coordinates: [13.0418, 80.2341], depth: 0.1, risk: 'Low', status: 'PASSABLE', suggestedAction: 'None', elevation: 6.5, imperviousness: 90 },
  { id: 'N231', location: 'T. Nagar 31', coordinates: [13.0425, 80.2355], depth: 0.2, risk: 'Moderate', status: 'PASSABLE', suggestedAction: 'Monitor', elevation: 6.2, imperviousness: 93 },
  { id: 'N087', location: 'T. Nagar', coordinates: [13.0432, 80.2330], depth: 0.05, risk: 'Safe', status: 'PASSABLE', suggestedAction: 'None', elevation: 6.8, imperviousness: 85 },
];

const mockReports: Report[] = [
  { id: 'R100', name: 'Ramesh', phone: '9876543210', location: 'Near N231', description: 'Water logging starting.', status: 'PENDING', timestamp: new Date().toISOString() },
];

const mockLogs: Log[] = [
  { timestamp: new Date().toISOString(), officialId: 'MUNI_01', refId: 'SYS', action: 'STARTUP', description: 'System initialized', status: 'COMPLETED' },
  { timestamp: new Date(Date.now() - 1000 * 60 * 5).toISOString(), officialId: 'MUNI_01', refId: 'R099', action: 'REVIEW_REPORT', description: 'Report under review', status: 'PENDING' },
];

const PravahaContext = createContext<PravahaContextType | undefined>(undefined);

export const PravahaProvider = ({ children }: { children: ReactNode }) => {
  const [nodes, setNodes] = useState<Node[]>(mockNodes);
  const [reports, setReports] = useState<Report[]>(mockReports);
  const [logs, setLogs] = useState<Log[]>(mockLogs);
  const [rainfall, setRainfallState] = useState(0);
  const [forecastHour, setForecastHourState] = useState(0);

  const addLog = (officialId: string, refId: string, action: string, description: string, status?: 'PENDING' | 'COMPLETED' | 'REJECTED') => {
    setLogs(prev => [...prev, { timestamp: new Date().toISOString(), officialId, refId, action, description, status }]);
  };

  const addReport = (reportData: Omit<Report, 'id' | 'status' | 'timestamp'>) => {
    const newReport: Report = {
      ...reportData,
      id: `R${Math.floor(Math.random() * 1000) + 100}`,
      status: 'PENDING',
      timestamp: new Date().toISOString(),
    };
    setReports(prev => [...prev, newReport]);
  };

  const approveReport = (reportId: string, nodeId: string) => {
    setReports(prev => prev.map(r => r.id === reportId ? { ...r, status: 'APPROVED' } : r));
    setNodes(prev => prev.map(n => n.id === nodeId ? { ...n, status: 'FLOODED', risk: 'Critical', depth: n.depth + 1.0, suggestedAction: 'Deploy pump' } : n));
    addLog('MUNI_01', reportId, 'APPROVE_REPORT', `Approved report ${reportId} and blocked node ${nodeId}`, 'COMPLETED');
  };

  const rejectReport = (reportId: string) => {
    setReports(prev => prev.map(r => r.id === reportId ? { ...r, status: 'REJECTED' } : r));
    addLog('MUNI_01', reportId, 'REJECT_REPORT', `Rejected report ${reportId}`, 'REJECTED');
  };

  const recalculateNodes = (rain: number, hour: number) => {
    setNodes(prev => prev.map(n => {
      const originalNode = mockNodes.find(m => m.id === n.id) || n;
      
      // Mock simulation: water depth increases over time based on rainfall rate
      let extraDepth = (rain / 150) * 1.5;
      if (hour > 0) {
        extraDepth = extraDepth * (hour * 1.5); // Multiply effect by future hours
        // If rain is low, simulate drainage over time
        if (rain < 20) extraDepth -= (hour * 0.2); 
      }

      let newDepth = Math.min(3.0, Math.max(0, originalNode.depth + extraDepth));
      
      let risk: RiskLevel = 'Safe';
      let status: NodeStatus = 'PASSABLE';
      if (newDepth > 1.2) { risk = 'Critical'; status = 'FLOODED'; }
      else if (newDepth > 0.8) { risk = 'High'; status = 'FLOODED'; }
      else if (newDepth > 0.4) { risk = 'Moderate'; status = 'SURCHARGE'; }
      else if (newDepth > 0.2) { risk = 'Low'; status = 'PASSABLE'; }
      
      return { ...n, depth: parseFloat(newDepth.toFixed(2)), risk, status };
    }));
  };

  const setRainfall = (mmHr: number) => {
    setRainfallState(mmHr);
    recalculateNodes(mmHr, forecastHour);
  };

  const setForecastHour = (hour: number) => {
    setForecastHourState(hour);
    recalculateNodes(rainfall, hour);
  };

  return (
    <PravahaContext.Provider value={{ nodes, reports, logs, addReport, approveReport, rejectReport, setRainfall, rainfall, forecastHour, setForecastHour }}>
      {children}
    </PravahaContext.Provider>
  );
};

export const usePravaha = () => {
  const context = useContext(PravahaContext);
  if (context === undefined) {
    throw new Error('usePravaha must be used within a PravahaProvider');
  }
  return context;
};
