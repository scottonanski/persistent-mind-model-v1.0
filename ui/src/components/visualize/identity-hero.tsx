'use client';

import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Brain, TrendingUp, Activity } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';

const STAGE_COLORS = {
  S0: { bg: 'bg-blue-500', text: 'text-blue-600', glow: 'shadow-blue-500/25' },
  S1: { bg: 'bg-green-500', text: 'text-green-600', glow: 'shadow-green-500/25' },
  S2: { bg: 'bg-yellow-500', text: 'text-yellow-600', glow: 'shadow-yellow-500/25' },
  S3: { bg: 'bg-orange-500', text: 'text-orange-600', glow: 'shadow-orange-500/25' },
  S4: { bg: 'bg-purple-500', text: 'text-purple-600', glow: 'shadow-purple-500/25' },
};

const STAGE_DESCRIPTIONS = {
  S0: 'Initialization',
  S1: 'Pattern Recognition',
  S2: 'Learning & Adaptation',
  S3: 'Autonomous Operation',
  S4: 'Self-Actualization'
};

export function IdentityHero() {
  const { selectedDb } = useDatabase();

  const { data: metrics } = useQuery({
    queryKey: ['identity-hero', selectedDb],
    queryFn: () => apiClient.getMetrics(selectedDb),
    refetchInterval: 10000, // Update every 10 seconds
  });

  if (!metrics?.metrics) {
    return (
      <Card className="mb-6">
        <CardContent className="p-8">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-muted rounded w-1/4"></div>
            <div className="h-8 bg-muted rounded w-1/2"></div>
            <div className="h-4 bg-muted rounded w-3/4"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  const { stage, ias, gas, traits } = metrics.metrics;
  const stageColor = STAGE_COLORS[stage.current as keyof typeof STAGE_COLORS] || STAGE_COLORS.S0;
  const stageDescription = STAGE_DESCRIPTIONS[stage.current as keyof typeof STAGE_DESCRIPTIONS] || 'Unknown Stage';

  // Get dominant traits for personality summary
  const sortedTraits = Object.entries(traits).sort(([,a], [,b]) => b - a);
  const topTraits = sortedTraits.slice(0, 2);
  const personalitySummary = topTraits.length > 0
    ? `High ${topTraits[0][0]} • Moderate ${topTraits[1][0]}`
    : 'Balanced personality';

  return (
    <motion.div
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
    >
      <Card className={`mb-6 border-2 ${stageColor.glow}`}>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            {/* Left side - Identity */}
            <div className="flex items-center space-x-4">
              <motion.div
                className={`p-3 rounded-full ${stageColor.bg} shadow-lg`}
                animate={{ scale: [1, 1.05, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
              >
                <Brain className="h-6 w-6 text-white" />
              </motion.div>

              <div>
                <motion.h2
                  className="text-xl font-bold mb-1"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  Persistent Mind Model
                </motion.h2>
                <motion.div
                  className="flex items-center space-x-2 mb-1"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.3 }}
                >
                  <Badge
                    className={`${stageColor.bg} text-white border-0 px-2 py-0.5 text-xs font-medium`}
                  >
                    Stage {stage.current}: {stageDescription}
                  </Badge>
                </motion.div>
                <motion.p
                  className="text-sm font-medium text-muted-foreground"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.4 }}
                >
                  {personalitySummary}
                </motion.p>
              </div>
            </div>

            {/* Right side - Metrics */}
            <div className="flex space-x-6">
              {/* IAS */}
              <motion.div
                className="text-center"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.5 }}
              >
                <div className="flex items-center space-x-1 mb-1">
                  <Activity className="h-3 w-3 text-blue-500" />
                  <span className="text-xs font-medium text-muted-foreground">IAS</span>
                </div>
                <div className="text-lg font-bold text-blue-600">
                  {(ias * 100).toFixed(1)}%
                </div>
                <div className="w-16 h-0.5 bg-muted rounded-full mt-1">
                  <motion.div
                    className="h-0.5 bg-blue-500 rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${ias * 100}%` }}
                    transition={{ duration: 1, delay: 0.7 }}
                  />
                </div>
              </motion.div>

              {/* GAS */}
              <motion.div
                className="text-center"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.6 }}
              >
                <div className="flex items-center space-x-1 mb-1">
                  <TrendingUp className="h-3 w-3 text-green-500" />
                  <span className="text-xs font-medium text-muted-foreground">GAS</span>
                </div>
                <div className="text-lg font-bold text-green-600">
                  {(gas * 100).toFixed(1)}%
                </div>
                <div className="w-16 h-0.5 bg-muted rounded-full mt-1">
                  <motion.div
                    className="h-0.5 bg-green-500 rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${gas * 100}%` }}
                    transition={{ duration: 1, delay: 0.8 }}
                  />
                </div>
              </motion.div>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
