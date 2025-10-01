'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface TraceStatsProps {
  stats: {
    total_traces: number;
    total_nodes_visited: number;
    avg_nodes_per_trace: number;
    avg_duration_ms: number;
    node_type_distribution: Record<string, number>;
  };
}

export function TraceStats({ stats }: TraceStatsProps) {
  // Prepare data for chart
  const chartData = Object.entries(stats.node_type_distribution)
    .map(([type, count]) => ({
      type,
      count,
      percentage: ((count / stats.total_nodes_visited) * 100).toFixed(1),
    }))
    .sort((a, b) => b.count - a.count);

  const getNodeTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      commitment: '#3b82f6',
      reflection: '#a855f7',
      identity: '#22c55e',
      policy: '#f97316',
      stage: '#ec4899',
      bandit: '#eab308',
      event: '#6b7280',
    };
    return colors[type] || '#6b7280';
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Node Type Distribution</CardTitle>
        <CardDescription>
          Breakdown of nodes visited across all reasoning sessions
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis 
              dataKey="type" 
              className="text-xs"
              tick={{ fill: 'currentColor' }}
            />
            <YAxis 
              className="text-xs"
              tick={{ fill: 'currentColor' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'hsl(var(--background))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '6px',
              }}
              formatter={(value: number, name: string, props: any) => [
                `${value.toLocaleString()} nodes (${props.payload.percentage}%)`,
                'Count',
              ]}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={getNodeTypeColor(entry.type)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        {/* Legend */}
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2">
          {chartData.map((item) => (
            <div key={item.type} className="flex items-center gap-2 text-sm">
              <div
                className="w-3 h-3 rounded"
                style={{ backgroundColor: getNodeTypeColor(item.type) }}
              />
              <span className="font-medium">{item.type}</span>
              <span className="text-muted-foreground ml-auto">
                {item.percentage}%
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
