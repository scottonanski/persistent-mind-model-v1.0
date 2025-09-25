'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CheckCircle, Circle, Zap, RefreshCw } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';

const STAGES = [
  { id: 'S0', name: 'Initialization', color: '#6b7280' },
  { id: 'S1', name: 'Basic Learning', color: '#3b82f6' },
  { id: 'S2', name: 'Pattern Recognition', color: '#10b981' },
  { id: 'S3', name: 'Advanced Reasoning', color: '#f59e0b' },
  { id: 'S4', name: 'Autonomous Operation', color: '#8b5cf6' }
];

export function StageLadder() {
  const { selectedDb } = useDatabase();
  const queryClient = useQueryClient();

  const { data: metrics, isLoading } = useQuery({
    queryKey: ['stage-metrics', selectedDb],
    queryFn: () => apiClient.getMetrics(selectedDb),
    refetchInterval: 30000,
  });

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['stage-metrics', selectedDb] });
  };

  // Use the raw stage string (e.g., 'S4m') for display
  const rawStage = metrics?.metrics.stage.current || 'S0';
  // Normalize to base stage (S0..S4) for visualization/progress
  const baseStage = (rawStage.match(/^S[0-4]/)?.[0] || 'S0') as 'S0' | 'S1' | 'S2' | 'S3' | 'S4';
  const currentStageIndex = STAGES.findIndex(s => s.id === baseStage);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Stage Ladder</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="w-full h-80" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex justify-between items-center">
          <div>
            <CardTitle className="text-lg">Stage Progress</CardTitle>
            <CardDescription>Currently at {rawStage}</CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            title="Refresh stage data"
          >
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Compact horizontal progress bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Progress</span>
            <span className="font-medium">{Math.round(((currentStageIndex + 1) / STAGES.length) * 100)}%</span>
          </div>
          <div className="w-full bg-muted rounded-full h-3">
            <motion.div
              className="bg-gradient-to-r from-blue-500 to-purple-500 h-3 rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${((currentStageIndex + 1) / STAGES.length) * 100}%` }}
              transition={{ duration: 1 }}
            />
          </div>
        </div>

        {/* Compact stage indicators */}
        <div className="flex justify-between items-center pt-2">
          {STAGES.map((stage, index) => {
            const isCompleted = index < currentStageIndex;
            const isCurrent = index === currentStageIndex;

            return (
              <div key={stage.id} className="flex flex-col items-center gap-1">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                  isCurrent ? 'bg-blue-500 text-white shadow-lg' : 
                  isCompleted ? 'bg-green-500 text-white' :
                  'bg-muted text-muted-foreground'
                }`}>
                  {isCurrent ? (
                    <motion.div animate={{ scale: [1, 1.1, 1] }} transition={{ duration: 2, repeat: Infinity }}>
                      {stage.id}
                    </motion.div>
                  ) : (
                    stage.id
                  )}
                </div>
                <span className="text-xs text-center leading-tight max-w-[60px]">
                  {stage.name.split(' ')[0]}
                </span>
              </div>
            );
          })}
        </div>

        {/* Current stage info */}
        {currentStageIndex >= 0 && (
          <div className="mt-3 p-2 bg-muted/50 rounded text-center">
            <Badge style={{ backgroundColor: STAGES[currentStageIndex].color }} className="text-white">
              {STAGES[currentStageIndex].name}
            </Badge>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
