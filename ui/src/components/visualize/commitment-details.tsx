'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CommitmentNode } from '@/types/commitment';

interface CommitmentDetailsProps {
  selectedNode: CommitmentNode | null;
}

export function CommitmentDetails({ selectedNode }: CommitmentDetailsProps) {
  return (
    <Card className="flex flex-col flex-1 max-h-96 min-h-[180px]">
      <CardHeader className="pb-2 flex-shrink-0">
        <CardTitle className="text-sm">Commitment Details</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden p-4">
        {selectedNode ? (
          <div className="h-full flex flex-col space-y-3">
            <div className="flex items-center gap-1 flex-shrink-0">
              <Badge variant={selectedNode.type === 'project' ? 'default' : 'outline'} className="text-xs">
                {selectedNode.type}
              </Badge>
              {selectedNode.type === 'commitment' && (
                <Badge variant={selectedNode.status === 'open' ? 'default' : 'secondary'} className="text-xs">
                  {selectedNode.status}
                </Badge>
              )}
            </div>
            <div className="flex-1 overflow-y-auto min-h-0">
              <div className="space-y-2">
                <h4 className="font-medium text-sm leading-tight">{selectedNode.text}</h4>
                {selectedNode.type === 'commitment' && (
                  <div className="text-xs text-muted-foreground space-y-1">
                    <p>Priority: {selectedNode.priority}</p>
                    <p>Project: {selectedNode.project}</p>
                    <p>Timestamp: {new Date(selectedNode.timestamp).toLocaleString()}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-center">
            <p className="text-sm text-muted-foreground leading-relaxed">
              Select a commitment from the network for more information
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
