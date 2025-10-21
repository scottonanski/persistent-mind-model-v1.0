'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as d3 from 'd3';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import { getEventLabel } from '@/lib/event-labels';
import { apiClient } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';
import { CommitmentNode as BaseCommitmentNode } from '@/types/commitment';

interface CommitmentNode extends d3.SimulationNodeDatum, BaseCommitmentNode {}

const STATUS_COLORS = {
  open: '#10b981',
  closed: '#6b7280', 
  expired: '#ef4444'
};

interface CommitmentClusterProps {
  onNodeSelect?: (node: CommitmentNode | null) => void;
}

export function CommitmentCluster({ onNodeSelect }: CommitmentClusterProps) {
  const { selectedDb } = useDatabase();
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedNode, setSelectedNode] = useState<CommitmentNode | null>(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  const { data: commitments, isLoading } = useQuery({
    queryKey: ['commitments-cluster', selectedDb],
    queryFn: () => apiClient.getCommitments({ db: selectedDb, limit: 100 }),
    refetchInterval: 30000,
  });

  useEffect(() => {
    if (!commitments?.commitments || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = 600;
    const height = Math.max(400, svgRef.current.clientHeight || 400); // Dynamic height with minimum

    // Create main group for zooming
    const g = svg.append('g');

    // Transform commitments into nodes
    const commitmentNodes: CommitmentNode[] = commitments.commitments.map((c: any) => ({
      id: c.id.toString(),
      text: getEventLabel(c),
      status: c.kind === 'commitment_open' ? 'open' : 
              c.kind === 'commitment_close' ? 'closed' : 'expired',
      priority: (c.meta?.priority as string) || 'medium',
      project: (c.meta?.project_id as string) || 'general',
      timestamp: c.ts,
      type: 'commitment'
    }));

    // Create project nodes
    const projects = Array.from(new Set(commitmentNodes.map(n => n.project)));
    const projectNodes: CommitmentNode[] = projects.map(project => ({
      id: `project-${project}`,
      text: project || 'General',
      status: 'open' as const,
      priority: 'high',
      project: project,
      timestamp: '',
      type: 'project'
    }));

    const nodes = [...projectNodes, ...commitmentNodes];

    // Create links between commitments and their projects
    const links = commitmentNodes.map(commitment => ({
      source: commitment.id,
      target: `project-${commitment.project}`
    }));

    // Create force simulation with stronger centering and boundaries
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((d: any) => d.id).distance(50).strength(0.5))
      .force('charge', d3.forceManyBody().strength(-150))
      .force('center', d3.forceCenter(width / 2, height / 2).strength(0.1))
      .force('collision', d3.forceCollide().radius(15))
      .force('x', d3.forceX(width / 2).strength(0.05))
      .force('y', d3.forceY(height / 2).strength(0.05));

    // Add links to the main group
    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', '#999')
      .attr('stroke-opacity', 0.3)
      .attr('stroke-width', 1);

    // Add nodes to the main group
    const node = g.append('g')
      .selectAll('circle')
      .data(nodes)
      .enter()
      .append('circle')
      .attr('r', d => d.type === 'project' ? 10 : 6)
      .attr('fill', d => d.type === 'project' ? '#3b82f6' : 
        STATUS_COLORS[d.status as keyof typeof STATUS_COLORS])
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .call(d3.drag<SVGCircleElement, CommitmentNode>()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }))
      .on('click', (event, d) => {
        setSelectedNode(d);
        onNodeSelect?.(d);
      })
      .on('mouseover', function(event, d) {
        // Add hover effect
        d3.select(this).attr('stroke-width', 3);
        
        // Create tooltip
        const tooltip = d3.select('body').selectAll('.commitment-tooltip')
          .data([0])
          .enter()
          .append('div')
          .attr('class', 'commitment-tooltip')
          .style('position', 'absolute')
          .style('visibility', 'hidden')
          .style('background', 'rgba(0, 0, 0, 0.9)')
          .style('color', 'white')
          .style('padding', '8px')
          .style('border-radius', '4px')
          .style('font-size', '12px')
          .style('z-index', '1000')
          .style('pointer-events', 'none');

        d3.select('.commitment-tooltip')
          .style('visibility', 'visible')
          .html(`<strong>${d.type === 'project' ? 'Project' : 'Commitment'}</strong><br/>${d.text}`)
          .style('left', (event.pageX + 10) + 'px')
          .style('top', (event.pageY - 10) + 'px');
      })
      .on('mouseout', function() {
        d3.select(this).attr('stroke-width', 2);
        d3.select('.commitment-tooltip').style('visibility', 'hidden');
      });

    // Remove text labels from the visualization for cleaner look
    // Text will be shown in tooltip or selection panel instead

    // Set up zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
        setZoomLevel(event.transform.k);
      });

    zoomRef.current = zoom;
    svg.call(zoom);

    // Update positions on simulation tick with boundary constraints
    simulation.on('tick', () => {
      // Constrain nodes within bounds
      nodes.forEach(d => {
        const radius = d.type === 'project' ? 10 : 6;
        d.x = Math.max(radius + 20, Math.min(width - radius - 20, d.x!));
        d.y = Math.max(radius + 20, Math.min(height - radius - 20, d.y!));
      });

      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      node
        .attr('cx', d => d.x!)
        .attr('cy', d => d.y!);
    });

  }, [commitments]);

  // Zoom control functions
  const handleZoomIn = () => {
    console.log('Zoom In clicked, current level:', zoomLevel);
    if (zoomRef.current && svgRef.current) {
      const svg = d3.select(svgRef.current);
      svg.transition()
        .duration(300)
        .call(zoomRef.current.scaleBy, 1.5);
    } else {
      console.log('Zoom ref or svg ref not available');
    }
  };

  const handleZoomOut = () => {
    console.log('Zoom Out clicked, current level:', zoomLevel);
    if (zoomRef.current && svgRef.current) {
      const svg = d3.select(svgRef.current);
      svg.transition()
        .duration(300)
        .call(zoomRef.current.scaleBy, 1 / 1.5);
    } else {
      console.log('Zoom ref or svg ref not available');
    }
  };

  const handleResetZoom = () => {
    console.log('Reset Zoom clicked');
    if (zoomRef.current && svgRef.current) {
      const svg = d3.select(svgRef.current);
      svg.transition()
        .duration(500)
        .call(zoomRef.current.transform, d3.zoomIdentity);
    } else {
      console.log('Zoom ref or svg ref not available');
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Commitment Clusters</CardTitle>
          <CardDescription>Force-directed graph of commitments by project</CardDescription>
        </CardHeader>
        <CardContent>
          <Skeleton className="w-full h-96" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col h-full">
      <CardHeader className="pb-3 flex-shrink-0">
        <div className="flex justify-between items-center">
          <div>
            <CardTitle className="text-lg">Commitment Network</CardTitle>
            <CardDescription className="text-sm">
              {commitments?.commitments.length} commitments
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleResetZoom}
            title="Reset Zoom"
          >
            <RotateCcw className="h-3 w-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col space-y-3">
        <div className="flex-1 bg-background border rounded-lg p-4 min-h-[300px]">
          <svg ref={svgRef} width="600" height="100%" className="w-full h-full" />
        </div>
        
        {/* Compact Legend */}
        <div className="flex justify-center gap-3 text-xs">
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-blue-500" />
            <span>Projects</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
            <span>Open</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-gray-500" />
            <span>Closed</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-red-500" />
            <span>Expired</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
