export interface CommitmentNode {
  id: string;
  text: string;
  status: 'open' | 'closed' | 'expired';
  priority: string;
  project?: string;
  timestamp: string;
  type: 'commitment' | 'project';
}
