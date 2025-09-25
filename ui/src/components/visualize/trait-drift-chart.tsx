'use client';

import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { apiClient } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';

const TRAIT_COLORS = {
  openness: '#3b82f6',
  conscientiousness: '#10b981',
  extraversion: '#f59e0b',
  agreeableness: '#8b5cf6',
  neuroticism: '#ef4444'
};

export function TraitDriftChart() {
  const { selectedDb } = useDatabase();

  // Get current metrics data (for now, we'll show current state as a single point)
  const { data: metrics, isLoading } = useQuery({
    queryKey: ['trait-drift', selectedDb],
    queryFn: () => apiClient.getMetrics(selectedDb),
    refetchInterval: 30000,
  });

  // Transform current metrics into chart data for bar chart
  const chartData = metrics?.metrics.traits ? [
    { trait: 'Openness', value: metrics.metrics.traits.openness || 0, color: TRAIT_COLORS.openness },
    { trait: 'Conscientiousness', value: metrics.metrics.traits.conscientiousness || 0, color: TRAIT_COLORS.conscientiousness },
    { trait: 'Extraversion', value: metrics.metrics.traits.extraversion || 0, color: TRAIT_COLORS.extraversion },
    { trait: 'Agreeableness', value: metrics.metrics.traits.agreeableness || 0, color: TRAIT_COLORS.agreeableness },
    { trait: 'Neuroticism', value: metrics.metrics.traits.neuroticism || 0, color: TRAIT_COLORS.neuroticism }
  ] : [];

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-background border rounded-lg p-3 shadow-lg">
          <p className="font-medium">{data.trait}</p>
          <p style={{ color: data.color }}>
            Value: {(data.value * 100).toFixed(1)}%
          </p>
          {metrics?.metrics && (
            <div className="mt-2 pt-2 border-t text-xs text-muted-foreground">
              <p>IAS: {(metrics.metrics.ias * 100).toFixed(1)}%</p>
              <p>GAS: {(metrics.metrics.gas * 100).toFixed(1)}%</p>
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>OCEAN Trait Drift</CardTitle>
          <CardDescription>Personality trait evolution over time</CardDescription>
        </CardHeader>
        <CardContent>
          <Skeleton className="w-full h-64" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">OCEAN Traits</CardTitle>
        <CardDescription>Current personality profile</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {chartData.length > 0 ? (
          <div className="space-y-3">
            {chartData.map((trait) => (
              <div key={trait.trait} className="space-y-1">
                <div className="flex justify-between items-center text-sm">
                  <span className="font-medium">{trait.trait.charAt(0)}</span>
                  <span className="text-xs text-muted-foreground">
                    {(trait.value * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="w-full bg-muted rounded-full h-2">
                  <div
                    className="h-2 rounded-full transition-all duration-500"
                    style={{
                      width: `${trait.value * 100}%`,
                      backgroundColor: trait.color
                    }}
                  />
                </div>
              </div>
            ))}
            
            {/* IAS/GAS summary */}
            {metrics?.metrics && (
              <div className="mt-4 pt-3 border-t space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Identity Stability</span>
                  <span className="font-medium">{(metrics.metrics.ias * 100).toFixed(0)}%</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Goal Alignment</span>
                  <span className="font-medium">{(metrics.metrics.gas * 100).toFixed(0)}%</span>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-4 text-muted-foreground">
            <p className="text-sm">No trait data available</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
