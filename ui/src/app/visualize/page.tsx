'use client';

import { useState } from 'react';
import { Navigation } from '@/components/layout/navigation';
import { IdentityHero } from '@/components/visualize/identity-hero';
import { EventTimeline } from '@/components/visualize/event-timeline';
import { TraitDriftChart } from '@/components/visualize/trait-drift-chart';
import { CommitmentCluster } from '@/components/visualize/commitment-cluster';
import { StageLadder } from '@/components/visualize/stage-ladder';
import { CommitmentDetails } from '@/components/visualize/commitment-details';
import { CommitmentNode } from '@/types/commitment';

export default function VisualizePage() {
  const [selectedCommitment, setSelectedCommitment] = useState<CommitmentNode | null>(null);

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main className="container mx-auto px-6 py-6">
        <div className="space-y-4">
          {/* Compact Identity Header */}
          <IdentityHero />

          {/* Main Visualization Grid */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 min-h-[600px]">
            {/* Left Column - Timeline and Network */}
            <div className="xl:col-span-2 flex flex-col space-y-4 h-full">
              <EventTimeline />
              <div className="flex-1">
                <CommitmentCluster onNodeSelect={setSelectedCommitment} />
              </div>
            </div>
            
            {/* Right Column - Compact widgets stack */}
            <div className="flex flex-col space-y-4 h-full">
              <StageLadder />
              <TraitDriftChart />
              <CommitmentDetails selectedNode={selectedCommitment} />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
