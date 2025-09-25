'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as d3 from 'd3';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { apiClient, PMMEvent } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';
import { useWebSocket } from '@/hooks/use-websocket';
import { generateEventSummary, generateTooltipContent } from '@/lib/event-summaries';
import { Play, Pause, Wifi, WifiOff } from 'lucide-react';
import { format, parseISO } from 'date-fns';

// Group events into meaningful categories
const EVENT_CATEGORIES: Record<string, string[]> = {
  'Identity & Learning': [
    'identity_adopt', 'identity_checkpoint', 'name_updated', 'name_attempt_user', 'name_attempt_system',
    'curriculum_update', 'policy_update', 'evaluation_report', 'evaluation_summary'
  ],
  'Commitments': [
    'commitment_open', 'commitment_close', 'commitment_expire', 'commitment_priority', 'priority_update'
  ],
  'Reflections': [
    'reflection', 'meta_reflection', 'reflection_action', 'reflection_check', 'reflection_skipped',
    'reflection_forced', 'reflection_rejected', 'reflection_quality', 'reflection_discarded'
  ],
  'System Progress': [
    'metrics_update', 'trait_update', 'stage_progress', 'stage_transition', 'stage_update', 'stage_reflection'
  ],
  'Other Activity': ['bandit_arm_chosen', 'bandit_reward', 'audit_report', 'embedding_indexed', 'knowledge_assert', 'semantic_growth_report', 'self_suggestion', 'response', 'invariant_violation', 'user', 'llm_latency', 'scene_compact', 'recall_suggest']
};

const CATEGORY_COLORS = {
  'Identity & Learning': '#3b82f6',
  'Commitments': '#10b981', 
  'Reflections': '#8b5cf6',
  'System Progress': '#f59e0b',
  'Other Activity': '#6b7280'
};

function categorizeEvent(eventKind: string): string {
  for (const [category, kinds] of Object.entries(EVENT_CATEGORIES)) {
    if (kinds.includes(eventKind)) {
      return category;
    }
  }
  return 'Other Activity';
}

export function EventTimeline() {
  const { selectedDb } = useDatabase();
  const svgRef = useRef<SVGSVGElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<PMMEvent | null>(null);
  const { isConnected, lastMessage } = useWebSocket(isPlaying);

  const { data: events, isLoading, refetch } = useQuery({
    queryKey: ['events-timeline', selectedDb],
    queryFn: () => apiClient.getEvents({ db: selectedDb, limit: 500 }),
    refetchInterval: isPlaying && !isConnected ? 5000 : false,
  });

  // Handle WebSocket messages
  useEffect(() => {
    if (lastMessage?.type === 'event' && isPlaying) {
      // Refetch events when new event arrives
      refetch();
    }
  }, [lastMessage, isPlaying, refetch]);

  useEffect(() => {
    if (!events?.events || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = 1200;
    const height = 300; // Compact height since we have fewer categories
    const margin = { top: 40, right: 40, bottom: 80, left: 180 };

    const timeExtent = d3.extent(events.events, d => new Date(d.ts)) as [Date, Date];
    const xScale = d3.scaleTime()
      .domain(timeExtent)
      .range([margin.left, width - margin.right]);

    // Use categories instead of individual event kinds
    const categories = Object.keys(CATEGORY_COLORS);
    const yScale = d3.scaleBand()
      .domain(categories)
      .range([margin.top, height - margin.bottom])
      .padding(0.2);

    // Create tooltip div
    const tooltip = d3.select('body').selectAll('.event-tooltip')
      .data([0])
      .enter()
      .append('div')
      .attr('class', 'event-tooltip')
      .style('position', 'absolute')
      .style('visibility', 'hidden')
      .style('background', 'rgba(0, 0, 0, 0.9)')
      .style('color', 'white')
      .style('padding', '12px')
      .style('border-radius', '8px')
      .style('font-size', '14px')
      .style('font-family', 'monospace')
      .style('max-width', '400px')
      .style('white-space', 'pre-line')
      .style('z-index', '1000')
      .style('pointer-events', 'none')
      .style('box-shadow', '0 4px 12px rgba(0, 0, 0, 0.3)');

    // Add axes with better formatting
    svg.append('g')
      .attr('transform', `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(xScale)
        .tickFormat((d) => d3.timeFormat('%H:%M')(d as Date))
        .ticks(8))
      .selectAll('text')
      .style('font-size', '14px')
      .style('font-weight', '500');

    svg.append('g')
      .attr('transform', `translate(${margin.left},0)`)
      .call(d3.axisLeft(yScale))
      .selectAll('text')
      .style('font-size', '14px')
      .style('font-weight', '600')
      .style('fill', '#374151');

    // Add event dots grouped by category
    svg.selectAll('.event-dot')
      .data(events.events)
      .enter()
      .append('circle')
      .attr('class', 'event-dot')
      .attr('cx', d => xScale(new Date(d.ts)))
      .attr('cy', d => {
        const category = categorizeEvent(d.kind);
        return (yScale(category) || 0) + yScale.bandwidth() / 2;
      })
      .attr('r', 6)
      .attr('fill', d => {
        const category = categorizeEvent(d.kind);
        return CATEGORY_COLORS[category as keyof typeof CATEGORY_COLORS];
      })
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .style('opacity', 0.8)
      .on('mouseover', function(event, d) {
        d3.select(this).attr('r', 8).style('opacity', 1);
        const tooltipContent = generateTooltipContent(d);
        d3.select('.event-tooltip')
          .style('visibility', 'visible')
          .html(tooltipContent)
          .style('left', (event.pageX + 10) + 'px')
          .style('top', (event.pageY - 10) + 'px');
      })
      .on('mousemove', function(event) {
        d3.select('.event-tooltip')
          .style('left', (event.pageX + 10) + 'px')
          .style('top', (event.pageY - 10) + 'px');
      })
      .on('mouseout', function() {
        d3.select(this).attr('r', 6).style('opacity', 0.8);
        d3.select('.event-tooltip').style('visibility', 'hidden');
      })
      .on('click', (event, d) => setSelectedEvent(d));

    // Cleanup function to remove tooltip when component unmounts
    return () => {
      d3.select('.event-tooltip').remove();
    };

  }, [events]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Event Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="w-full h-40" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-center">
          <div>
            <CardTitle>Event Timeline</CardTitle>
            <CardDescription className="flex items-center gap-2">
              {events?.events.length} events
              {isPlaying && (
                <Badge variant={isConnected ? 'default' : 'outline'} className="text-xs">
                  {isConnected ? <Wifi className="h-3 w-3 mr-1" /> : <WifiOff className="h-3 w-3 mr-1" />}
                  {isConnected ? 'Live Stream' : 'Auto Refresh'}
                </Badge>
              )}
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsPlaying(!isPlaying)}
          >
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="w-full overflow-x-auto bg-background border rounded-lg p-4">
          <svg ref={svgRef} width="1200" height="300" className="min-w-full" />
        </div>
        
        {/* Category Legend */}
        <div className="mt-4 flex flex-wrap gap-4">
          {Object.entries(CATEGORY_COLORS).map(([category, color]) => (
            <div key={category} className="flex items-center gap-2 text-sm">
              <div 
                className="w-4 h-4 rounded-full border-2 border-white" 
                style={{ backgroundColor: color }}
              />
              <span className="font-medium">{category}</span>
            </div>
          ))}
        </div>
        
        {selectedEvent && (
          <div className="mt-4 p-4 border rounded-lg bg-muted/50">
            <div className="flex items-center gap-2 mb-2">
              <div 
                className="w-3 h-3 rounded-full" 
                style={{ backgroundColor: CATEGORY_COLORS[categorizeEvent(selectedEvent.kind) as keyof typeof CATEGORY_COLORS] }}
              />
              <h4 className="font-semibold capitalize">{selectedEvent.kind.replace('_', ' ')}</h4>
            </div>
            <p className="text-sm text-muted-foreground mb-2">
              {format(parseISO(selectedEvent.ts), 'MMMM dd, yyyy at HH:mm:ss')}
            </p>
            <p className="text-sm bg-background p-3 rounded border font-mono">
              {generateEventSummary(selectedEvent)}
            </p>
            {selectedEvent.meta && (
              <details className="mt-2">
                <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
                  View Raw Metadata
                </summary>
                <pre className="text-xs bg-muted p-2 rounded mt-1 overflow-x-auto">
                  {typeof selectedEvent.meta === 'string' ? selectedEvent.meta : JSON.stringify(selectedEvent.meta, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
