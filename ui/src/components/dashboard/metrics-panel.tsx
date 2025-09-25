'use client';

import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Activity, Gauge, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';
import { useState, useEffect } from 'react';

interface MetricGaugeProps {
  label: string;
  value: number;
  previousValue?: number;
  color: string;
  icon: React.ReactNode;
}

function MetricGauge({ label, value, previousValue, color, icon }: MetricGaugeProps) {
  const percentage = Math.round(value * 100);
  const prevPercentage = previousValue ? Math.round(previousValue * 100) : null;
  
  let trend: 'up' | 'down' | 'stable' | null = null;
  if (prevPercentage !== null) {
    if (percentage > prevPercentage) trend = 'up';
    else if (percentage < prevPercentage) trend = 'down';
    else trend = 'stable';
  }

  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-green-500' : trend === 'down' ? 'text-red-500' : 'text-muted-foreground';

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      className="space-y-2"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-medium">{label}</span>
        </div>
        {trend && (
          <div className="flex items-center gap-1">
            <TrendIcon className={`h-3 w-3 ${trendColor}`} />
            {prevPercentage !== null && (
              <span className={`text-xs ${trendColor}`}>
                {percentage - prevPercentage > 0 ? '+' : ''}{percentage - prevPercentage}%
              </span>
            )}
          </div>
        )}
      </div>
      
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <motion.span
            key={percentage}
            initial={{ scale: 1.2, color: color }}
            animate={{ scale: 1, color: 'inherit' }}
            transition={{ duration: 0.3 }}
            className="text-lg font-bold"
          >
            {percentage}%
          </motion.span>
          <Badge variant="outline" className="text-xs">
            {value.toFixed(3)}
          </Badge>
        </div>
        
        <div className="relative">
          <Progress value={percentage} className="h-2" />
          <motion.div
            className={`absolute top-0 left-0 h-2 rounded-full ${color}`}
            initial={{ width: 0 }}
            animate={{ width: `${percentage}%` }}
            transition={{ duration: 1, ease: "easeOut" }}
          />
        </div>
      </div>
    </motion.div>
  );
}

export function MetricsPanel() {
  const { selectedDb } = useDatabase();
  const [previousMetrics, setPreviousMetrics] = useState<{ ias: number; gas: number } | null>(null);

  const { data: metrics, isLoading, error } = useQuery({
    queryKey: ['metrics', selectedDb],
    queryFn: () => apiClient.getMetrics(selectedDb),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Store previous values for trend calculation
  useEffect(() => {
    if (metrics?.metrics && !previousMetrics) {
      // Only set previous metrics on first load to avoid constant updates
      setPreviousMetrics({
        ias: metrics.metrics.ias,
        gas: metrics.metrics.gas,
      });
    }
  }, [metrics, previousMetrics]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            System Metrics
          </CardTitle>
          <CardDescription>Identity and Goal Alignment Scores</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3">
            <div className="flex justify-between">
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-4 w-12" />
            </div>
            <Skeleton className="h-3 w-full" />
          </div>
          <div className="space-y-3">
            <div className="flex justify-between">
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-4 w-12" />
            </div>
            <Skeleton className="h-3 w-full" />
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
            <Activity className="h-5 w-5" />
            System Metrics
          </CardTitle>
          <CardDescription>Identity and Goal Alignment Scores</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-destructive text-sm">Failed to load metrics data</p>
        </CardContent>
      </Card>
    );
  }

  const { ias, gas } = metrics?.metrics || { ias: 0, gas: 0 };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4" />
          System Metrics
        </CardTitle>
        <CardDescription className="text-xs">Identity and Goal Alignment Scores</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <MetricGauge
          label="IAS"
          value={ias}
          previousValue={previousMetrics?.ias}
          color="bg-blue-500"
          icon={<Gauge className="h-4 w-4 text-blue-500" />}
        />
        
        <MetricGauge
          label="GAS"
          value={gas}
          previousValue={previousMetrics?.gas}
          color="bg-green-500"
          icon={<Gauge className="h-4 w-4 text-green-500" />}
        />

        <div className="text-xs text-muted-foreground">
          <p><strong>IAS:</strong> Identity Stability • <strong>GAS:</strong> Goal Alignment</p>
          <p className="pt-1">
            Last updated: {metrics?.metrics.last_updated ? 
              new Date(metrics.metrics.last_updated).toLocaleString() : 
              'Unknown'
            }
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
