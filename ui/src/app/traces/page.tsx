'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle, Brain, Network, Clock, TrendingUp } from 'lucide-react';
import { Navigation } from '@/components/layout/navigation';
import { TraceList } from '@/components/traces/trace-list';
import { TraceStats } from '@/components/traces/trace-stats';
import { useDatabase } from '@/lib/database-context';
import { apiClient } from '@/lib/api';

export default function TracesPage() {
  const { selectedDb } = useDatabase();

  // Fetch trace stats
  const { data: statsData, isLoading: statsLoading, error: statsError } = useQuery({
    queryKey: ['trace-stats', selectedDb],
    queryFn: () => apiClient.getTraceStats(selectedDb),
    refetchInterval: 30000, // Refresh every 30s
  });

  // Fetch recent traces
  const { data: tracesData, isLoading: tracesLoading, error: tracesError } = useQuery({
    queryKey: ['traces', selectedDb],
    queryFn: () => apiClient.getTraces(selectedDb, 20),
    refetchInterval: 30000,
  });

  const stats = statsData?.stats;
  const traces = tracesData?.traces || [];

  if (statsError || tracesError) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <div className="container mx-auto p-6">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              Failed to load reasoning traces. Make sure the API server is running and traces are enabled.
            </AlertDescription>
          </Alert>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <Brain className="h-8 w-8" />
          Reasoning Traces
        </h1>
        <p className="text-muted-foreground mt-2">
          Explore PMM's internal reasoning process - node traversal, confidence levels, and decision paths
        </p>
      </div>

      {/* Stats Overview */}
      {statsLoading ? (
        <div className="grid gap-4 md:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : stats ? (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-1">
                <Network className="h-4 w-4" />
                Total Traces
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_traces.toLocaleString()}</div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-1">
                <Brain className="h-4 w-4" />
                Nodes Visited
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_nodes_visited.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground mt-1">
                Avg: {stats.avg_nodes_per_trace.toLocaleString()} per trace
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                Avg Duration
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.avg_duration_ms.toFixed(0)}ms</div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-1">
                <TrendingUp className="h-4 w-4" />
                Performance
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                {stats.avg_duration_ms < 100 ? 'Excellent' : stats.avg_duration_ms < 500 ? 'Good' : 'Fair'}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                &lt;1ms overhead
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {/* Node Type Distribution */}
      {stats && <TraceStats stats={stats} />}

      {/* Recent Traces */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Reasoning Sessions</CardTitle>
          <CardDescription>
            Latest queries and their reasoning traces
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tracesLoading ? (
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-3/4" />
                </div>
              ))}
            </div>
          ) : traces.length > 0 ? (
            <TraceList traces={traces} />
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Brain className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No reasoning traces found.</p>
              <p className="text-sm mt-2">
                Traces are created when PMM processes queries. Try interacting with the system.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
      </div>
    </div>
  );
}
