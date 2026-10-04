export type RiskLevel = 'Critical' | 'High' | 'Moderate' | 'Low' | 'Safe';
export type NodeStatus = 'FLOODED' | 'PASSABLE' | 'SURCHARGE';
export type ReportStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'RESOLVED';

export interface Node {
  id: string;
  location: string;
  coordinates: [number, number]; // [lat, lng]
  depth: number;
  risk: RiskLevel;
  status: NodeStatus;
  suggestedAction: string;
  elevation: number;
  imperviousness: number;
  blocked?: boolean;              // an official (or an approved report) has blocked this node
  blockSource?: string | null;    // 'manual' | 'report' (officials only)
}

export interface Report {
  id: string;
  name: string;
  phone: string;
  location: string;
  description: string;
  status: ReportStatus;
  timestamp: string;
  lat?: number | null;            // pin dropped by the citizen (if any)
  lon?: number | null;
  matchedNodeId?: string | null;  // node the server matched automatically (within 150 m of the pin)
  measures?: string | null;       // what the municipal officer did about it (free text)
  measuresBy?: string | null;
  measuresAt?: string | null;
}

export interface Log {
  timestamp: string;
  officialId: string;
  refId: string;
  action: string;
  description: string;
  status?: 'PENDING' | 'COMPLETED' | 'REJECTED';
  measures?: string | null;       // measures currently recorded on the report this entry refers to (report entries only)
}

export interface BlockInfo {
  nodeId: string;
  source: 'manual' | 'report';
  note?: string | null;
  reportRef?: string | null;
  createdBy: string;
  createdAt: string;
}
