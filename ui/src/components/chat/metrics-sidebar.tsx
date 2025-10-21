'use client';

import { useQuery } from '@tanstack/react-query';
import { Activity, TrendingUp } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { ScrollArea } from '@/components/ui/scroll-area';

const STAGES = [
  { id: 'S0', name: 'Initialization' },
  { id: 'S1', name: 'Basic' },
  { id: 'S2', name: 'Pattern' },
  { id: 'S3', name: 'Advanced' },
  { id: 'S4', name: 'Autonomous' }
];

const TRAIT_COLORS = {
  openness: '#3b82f6',      // Blue
  conscientiousness: '#10b981', // Green
  extraversion: '#f59e0b',  // Orange
  agreeableness: '#8b5cf6', // Purple
  neuroticism: '#ef4444',   // Red
};

const TRAIT_LABELS = {
  openness: 'O',
  conscientiousness: 'C',
  extraversion: 'E',
  agreeableness: 'A',
  neuroticism: 'N',
};

export function MetricsSidebar() {
  const { data: metrics, isLoading } = useQuery({
    queryKey: ['chat-metrics'],
    queryFn: () => apiClient.getMetrics(),
    refetchInterval: 5000,
    refetchOnMount: true,
    refetchOnWindowFocus: true,
  });

  if (isLoading || !metrics?.metrics) {
    return (
      <aside className="flex w-80 flex-col gap-4">
        {/* Loading skeleton */}
        <div className="rounded-3xl border border-border/40 bg-[#202125] p-4 shadow-lg">
          <div className="h-20 animate-pulse rounded bg-[#26272c]" />
        </div>
        <div className="rounded-3xl border border-border/40 bg-[#202125] p-4 shadow-lg">
          <div className="h-48 animate-pulse rounded bg-[#26272c]" />
        </div>
      </aside>
    );
  }

  const { ias, gas, stage, traits } = metrics.metrics;
  const rawStage = stage.current || 'S0';
  const baseStage = (rawStage.match(/^S[0-4]/)?.[0] || 'S0') as 'S0' | 'S1' | 'S2' | 'S3' | 'S4';
  const currentStageIndex = STAGES.findIndex(s => s.id === baseStage);
  const progress = Math.round(((currentStageIndex + 1) / STAGES.length) * 100);

  return (
    <aside className="flex w-80 flex-col gap-4">
      {/* IAS & GAS Card */}
      <div className="rounded-t-3xl border border-border/40 bg-[#202125] p-4 shadow-lg">
        <div className="flex items-center justify-around">
          {/* IAS */}
          <div className="flex flex-col items-center">
            <div className="mb-1 flex items-center gap-1">
              <Activity className="h-3 w-3 text-blue-500" />
              <span className="text-xs font-medium text-muted-foreground">IAS</span>
            </div>
            <div className="text-2xl font-bold text-blue-500">
              {(ias * 100).toFixed(1)}%
            </div>
          </div>

          {/* Divider */}
          <div className="h-12 w-px bg-border/40" />

          {/* GAS */}
          <div className="flex flex-col items-center">
            <div className="mb-1 flex items-center gap-1">
              <TrendingUp className="h-3 w-3 text-green-500" />
              <span className="text-xs font-medium text-muted-foreground">GAS</span>
            </div>
            <div className="text-2xl font-bold text-green-500">
              {(gas * 100).toFixed(1)}%
            </div>
          </div>
        </div>
      </div>

      {/* Stage Progress Card */}
      <div className="border border-border/40 bg-[#202125] shadow-lg">
        <div className="border-b border-border/40 px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Stage Progress</h3>
          <p className="text-xs text-muted-foreground">Currently at {rawStage}</p>
        </div>
        
        <div className="p-4 space-y-3">
          {/* Progress Bar */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Progress</span>
              <span className="font-medium text-foreground">{progress}%</span>
            </div>
            <div className="w-full rounded-full bg-[#2c2d32] h-2">
              <div
                className="h-2 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* Stage Indicators */}
          <div className="flex justify-between items-center pt-2">
            {STAGES.map((stg, index) => {
              const isCompleted = index < currentStageIndex;
              const isCurrent = index === currentStageIndex;

              return (
                <div key={stg.id} className="flex flex-col items-center gap-1">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                      isCurrent
                        ? 'bg-blue-500 text-white shadow-lg'
                        : isCompleted
                        ? 'bg-green-500 text-white'
                        : 'bg-[#2c2d32] text-muted-foreground'
                    }`}
                  >
                    {stg.id}
                  </div>
                  <span className="text-xs text-center leading-tight text-muted-foreground max-w-[60px]">
                    {stg.name}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Current Stage Badge */}
          {currentStageIndex >= 0 && (
            <div className="mt-3 rounded-lg bg-[#26272c] p-2 text-center">
              <span className="text-xs font-medium text-foreground">
                {STAGES[currentStageIndex].name}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* OCEAN Traits Card */}
      <div className="flex flex-col rounded-b-3xl border border-border/40 bg-[#202125] shadow-lg">
        <div className="border-b border-border/40 px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">OCEAN Traits</h3>
          <p className="text-xs text-muted-foreground">Current personality profile</p>
        </div>

        <div className="p-4 space-y-3">
          {Object.entries(traits).map(([trait, value]) => {
            const percentage = Math.round((value as number) * 100);
            const color = TRAIT_COLORS[trait as keyof typeof TRAIT_COLORS];
            const label = TRAIT_LABELS[trait as keyof typeof TRAIT_LABELS];

            return (
              <div key={trait} className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-foreground">
                    {label}
                  </span>
                  <span className="text-xs text-muted-foreground">{percentage}%</span>
                </div>
                <div className="w-full rounded-full bg-[#2c2d32] h-2">
                  <div
                    className="h-2 rounded-full transition-all duration-500"
                    style={{
                      width: `${percentage}%`,
                      backgroundColor: color,
                    }}
                  />
                </div>
              </div>
            );
          })}

          {/* Additional metrics */}
          <div className="mt-4 space-y-2 border-t border-border/30 pt-3">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Identity Stability</span>
              <span className="font-medium text-foreground">8%</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Goal Alignment</span>
              <span className="font-medium text-foreground">3%</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
