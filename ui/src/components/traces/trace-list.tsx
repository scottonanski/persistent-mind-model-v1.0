'use client';

import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronDown, ChevronRight, Clock, Network, TrendingUp } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface Trace {
  id: number;
  timestamp: string;
  session_id: string;
  query: string;
  total_nodes_visited: number;
  node_type_distribution: Record<string, number>;
  high_confidence_count: number;
  high_confidence_paths: Array<{
    node_type: string;
    confidence: number;
    edge_label?: string;
    reasoning?: string;
  }>;
  sampled_count: number;
  reasoning_steps: string[];
  duration_ms: number;
}

interface TraceListProps {
  traces: Trace[];
}

export function TraceList({ traces }: TraceListProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const formatTimestamp = (ts: string) => {
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  const getNodeTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      commitment: 'bg-blue-500/10 text-blue-700 dark:text-blue-300',
      reflection: 'bg-purple-500/10 text-purple-700 dark:text-purple-300',
      identity: 'bg-green-500/10 text-green-700 dark:text-green-300',
      policy: 'bg-orange-500/10 text-orange-700 dark:text-orange-300',
      stage: 'bg-pink-500/10 text-pink-700 dark:text-pink-300',
      bandit: 'bg-yellow-500/10 text-yellow-700 dark:text-yellow-300',
      event: 'bg-gray-500/10 text-gray-700 dark:text-gray-300',
    };
    return colors[type] || 'bg-gray-500/10 text-gray-700 dark:text-gray-300';
  };

  return (
    <div className="space-y-3">
      {traces.map((trace, index) => {
        const isExpanded = expandedId === trace.id;
        const topNodeTypes = Object.entries(trace.node_type_distribution)
          .sort(([, a], [, b]) => b - a)
          .slice(0, 3);

        return (
          <motion.div
            key={trace.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
          >
            <Card className="p-4 hover:shadow-md transition-shadow">
              <div className="space-y-3">
                {/* Header */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0"
                        onClick={() => toggleExpand(trace.id)}
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </Button>
                      <span className="text-sm text-muted-foreground">
                        {formatTimestamp(trace.timestamp)}
                      </span>
                    </div>
                    <p className="font-medium truncate">{trace.query}</p>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    <Badge variant="outline" className="flex items-center gap-1">
                      <Network className="h-3 w-3" />
                      {trace.total_nodes_visited.toLocaleString()}
                    </Badge>
                    <Badge variant="outline" className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {trace.duration_ms}ms
                    </Badge>
                    {trace.high_confidence_count > 0 && (
                      <Badge variant="outline" className="flex items-center gap-1 bg-green-500/10">
                        <TrendingUp className="h-3 w-3" />
                        {trace.high_confidence_count}
                      </Badge>
                    )}
                  </div>
                </div>

                {/* Top Node Types */}
                <div className="flex flex-wrap gap-2">
                  {topNodeTypes.map(([type, count]) => (
                    <Badge key={type} className={getNodeTypeColor(type)}>
                      {type}: {count.toLocaleString()}
                    </Badge>
                  ))}
                </div>

                {/* Expanded Details */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.2 }}
                      className="space-y-4 pt-4 border-t"
                    >
                      {/* Reasoning Steps */}
                      {trace.reasoning_steps.length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold mb-2">Reasoning Steps</h4>
                          <ol className="text-sm space-y-1 list-decimal list-inside text-muted-foreground">
                            {trace.reasoning_steps.map((step, i) => (
                              <li key={i}>{step}</li>
                            ))}
                          </ol>
                        </div>
                      )}

                      {/* High Confidence Paths */}
                      {trace.high_confidence_paths.length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold mb-2">
                            High-Confidence Paths ({trace.high_confidence_paths.length})
                          </h4>
                          <div className="space-y-2">
                            {trace.high_confidence_paths.slice(0, 5).map((path, i) => (
                              <div
                                key={i}
                                className="text-sm p-2 rounded bg-muted/50 flex items-center justify-between"
                              >
                                <div className="flex items-center gap-2">
                                  <Badge className={getNodeTypeColor(path.node_type)}>
                                    {path.node_type}
                                  </Badge>
                                  {path.edge_label && (
                                    <span className="text-muted-foreground">
                                      via <code className="text-xs">{path.edge_label}</code>
                                    </span>
                                  )}
                                </div>
                                <Badge variant="outline" className="bg-green-500/10">
                                  {(path.confidence * 100).toFixed(0)}%
                                </Badge>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Full Node Distribution */}
                      <div>
                        <h4 className="text-sm font-semibold mb-2">Complete Node Distribution</h4>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                          {Object.entries(trace.node_type_distribution)
                            .sort(([, a], [, b]) => b - a)
                            .map(([type, count]) => (
                              <div
                                key={type}
                                className="flex items-center justify-between p-2 rounded bg-muted/30 text-sm"
                              >
                                <span className="font-medium">{type}</span>
                                <span className="text-muted-foreground">{count.toLocaleString()}</span>
                              </div>
                            ))}
                        </div>
                      </div>

                      {/* Metadata */}
                      <div className="text-xs text-muted-foreground space-y-1">
                        <p>Session ID: <code className="text-xs">{trace.session_id.slice(0, 8)}</code></p>
                        <p>Sampled Nodes: {trace.sampled_count}</p>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </Card>
          </motion.div>
        );
      })}
    </div>
  );
}
