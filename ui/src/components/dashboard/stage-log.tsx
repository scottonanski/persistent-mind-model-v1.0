'use client';

import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { CheckCircle, Circle, Zap } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';

const STAGES = [
  { id: 'S0', name: 'Initialization', description: 'Basic setup and identity adoption' },
  { id: 'S1', name: 'Basic Learning', description: 'Learning fundamental patterns' },
  { id: 'S2', name: 'Pattern Recognition', description: 'Identifying and using patterns' },
  { id: 'S3', name: 'Advanced Reasoning', description: 'Complex problem solving' },
  { id: 'S4', name: 'Autonomous Operation', description: 'Self-directed operation' },
];

interface StageItemProps {
  stage: typeof STAGES[0];
  isCompleted: boolean;
  isCurrent: boolean;
  index: number;
}

function StageItem({ stage, isCompleted, isCurrent, index }: StageItemProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.1 }}
      className="flex items-center gap-3 p-2.5 rounded-lg border"
    >
      <div className="relative">
        {isCompleted ? (
          <CheckCircle className="h-4 w-4 text-green-500" />
        ) : isCurrent ? (
          <motion.div
            animate={{ scale: [1, 1.1, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <Zap className="h-4 w-4 text-blue-500" />
          </motion.div>
        ) : (
          <Circle className="h-4 w-4 text-muted-foreground" />
        )}
        
        {index < STAGES.length - 1 && (
          <div 
            className={`absolute top-5 left-2 w-0.5 h-7 ${
              isCompleted ? 'bg-green-500' : 'bg-muted-foreground/20'
            }`}
          />
        )}
      </div>
      
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{stage.id}</span>
          <Badge 
            variant={isCurrent ? 'default' : isCompleted ? 'secondary' : 'outline'}
            className={`text-xs ${isCurrent ? 'bg-blue-500 text-white' : ''}`}
          >
            {stage.name}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">
          {stage.description}
        </p>
      </div>
      
      {isCurrent && (
        <motion.div
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 2, repeat: Infinity }}
          className="text-xs text-blue-500 font-medium"
        >
          CURRENT
        </motion.div>
      )}
    </motion.div>
  );
}

export function StageLog() {
  const { selectedDb } = useDatabase();

  const { data: metrics, isLoading, error } = useQuery({
    queryKey: ['metrics', selectedDb],
    queryFn: () => apiClient.getMetrics(selectedDb),
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            Stage Progression
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {STAGES.map((_, i) => (
              <div key={i} className="flex items-center gap-4 p-3 rounded-lg border">
                <Skeleton className="h-6 w-6 rounded-full" />
                <div className="flex-1 space-y-2">
                  <div className="flex gap-2">
                    <Skeleton className="h-4 w-8" />
                    <Skeleton className="h-4 w-24" />
                  </div>
                  <Skeleton className="h-3 w-full" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            Stage Progression
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-destructive text-sm">Failed to load stage data</p>
        </CardContent>
      </Card>
    );
  }

  const currentStage = metrics?.metrics.stage.current || 'S0';
  const currentStageIndex = STAGES.findIndex(s => s.id === currentStage);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Zap className="h-4 w-4" />
          Stage Progression
        </CardTitle>
        <CardDescription className="text-xs">
          Current development stage: {currentStage}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2.5">
        {STAGES.map((stage, index) => (
          <StageItem
            key={stage.id}
            stage={stage}
            isCompleted={index < currentStageIndex}
            isCurrent={index === currentStageIndex}
            index={index}
          />
        ))}
        
        <div className="mt-3 p-2 bg-muted rounded-lg">
          <div className="text-xs">
            <strong>Progress:</strong> {currentStageIndex + 1} of {STAGES.length} stages completed
          </div>
          <div className="w-full bg-background rounded-full h-1.5 mt-1">
            <motion.div
              className="bg-blue-500 h-1.5 rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${((currentStageIndex + 1) / STAGES.length) * 100}%` }}
              transition={{ duration: 1, ease: "easeOut" }}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
