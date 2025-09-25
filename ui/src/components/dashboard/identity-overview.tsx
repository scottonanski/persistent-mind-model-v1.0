'use client';

import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { User, Brain, TrendingUp } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';

const OCEAN_TRAITS = [
  { key: 'openness', label: 'Openness', color: 'bg-blue-500' },
  { key: 'conscientiousness', label: 'Conscientiousness', color: 'bg-green-500' },
  { key: 'extraversion', label: 'Extraversion', color: 'bg-yellow-500' },
  { key: 'agreeableness', label: 'Agreeableness', color: 'bg-purple-500' },
  { key: 'neuroticism', label: 'Neuroticism', color: 'bg-red-500' },
];

const STAGE_COLORS = {
  S0: 'bg-gray-500',
  S1: 'bg-blue-500',
  S2: 'bg-green-500',
  S3: 'bg-yellow-500',
  S4: 'bg-purple-500',
};

const STAGE_DESCRIPTIONS = {
  S0: 'Initialization',
  S1: 'Basic Learning',
  S2: 'Pattern Recognition',
  S3: 'Advanced Reasoning',
  S4: 'Autonomous Operation',
};

export function IdentityOverview() {
  const { selectedDb } = useDatabase();

  const { data: metrics, isLoading, error } = useQuery({
    queryKey: ['metrics', selectedDb],
    queryFn: () => apiClient.getMetrics(selectedDb),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Identity Overview
          </CardTitle>
          <CardDescription>Current identity state and traits</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-6 w-16" />
          </div>
          <div className="space-y-3">
            {OCEAN_TRAITS.map((trait) => (
              <div key={trait.key} className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>{trait.label}</span>
                  <Skeleton className="h-4 w-12" />
                </div>
                <Skeleton className="h-2 w-full" />
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
            <User className="h-5 w-5" />
            Identity Overview
          </CardTitle>
          <CardDescription>Current identity state and traits</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-destructive text-sm">Failed to load identity data</p>
        </CardContent>
      </Card>
    );
  }

  const stage = metrics?.metrics.stage.current || 'S0';
  const traits = metrics?.metrics.traits || {};

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <User className="h-4 w-4" />
          Identity Overview
        </CardTitle>
        <CardDescription className="text-xs">Current identity state and traits</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Stage and Name */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Stage:</span>
          </div>
          <Badge 
            className={`${STAGE_COLORS[stage as keyof typeof STAGE_COLORS]} text-white text-xs`}
          >
            {stage}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {STAGE_DESCRIPTIONS[stage as keyof typeof STAGE_DESCRIPTIONS]}
          </span>
        </div>

        {/* OCEAN Traits */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-3 w-3 text-muted-foreground" />
            <span className="text-xs font-medium">OCEAN Personality Traits</span>
          </div>
          
          <div className="space-y-2">
            {OCEAN_TRAITS.map((trait, index) => {
              const value = (traits as any)[trait.key] || 0;
              const percentage = Math.round(value * 100);
              
              return (
                <motion.div
                  key={trait.key}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.1 }}
                  className="space-y-1"
                >
                  <div className="flex justify-between text-xs">
                    <span className="font-medium">{trait.label}</span>
                    <motion.span
                      key={percentage}
                      initial={{ scale: 1.2, color: '#3b82f6' }}
                      animate={{ scale: 1, color: 'inherit' }}
                      transition={{ duration: 0.3 }}
                      className="text-muted-foreground"
                    >
                      {percentage}%
                    </motion.span>
                  </div>
                  <div className="relative">
                    <Progress value={percentage} className="h-1.5" />
                    <motion.div
                      className={`absolute top-0 left-0 h-1.5 rounded-full ${trait.color}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${percentage}%` }}
                      transition={{ duration: 0.8, ease: "easeOut" }}
                    />
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Last Updated */}
        <div className="text-xs text-muted-foreground">
          Last updated: {metrics?.metrics.last_updated ? 
            new Date(metrics.metrics.last_updated).toLocaleString() : 
            'Unknown'
          }
        </div>
      </CardContent>
    </Card>
  );
}
