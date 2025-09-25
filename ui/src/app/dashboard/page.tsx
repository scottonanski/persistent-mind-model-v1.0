'use client';

import { Navigation } from '@/components/layout/navigation';
import { IdentityOverview } from '@/components/dashboard/identity-overview';
import { MetricsPanel } from '@/components/dashboard/metrics-panel';
import { ReflectionsFeed } from '@/components/dashboard/reflections-feed';
import { CommitmentsTracker } from '@/components/dashboard/commitments-tracker';
import { StageLog } from '@/components/dashboard/stage-log';

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main className="container mx-auto px-4 py-8 h-[calc(100vh-4rem)] flex flex-col">
        <div className="flex-shrink-0 mb-6">
          <h1 className="text-3xl font-bold">PMM Dashboard</h1>
          <p className="text-muted-foreground">
            Real-time view of the Persistent Mind Model state and activity
          </p>
        </div>
        
        {/* Two Column Layout - Feeds are focal points */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 flex-1 min-h-0">
          {/* Left Column - Activity Feeds (Focal Points) */}
          <div className="lg:col-span-3 flex flex-col space-y-6 min-h-0">
            <div className="flex-shrink-0">
              <ReflectionsFeed />
            </div>
            <div className="flex-1 min-h-0">
              <CommitmentsTracker />
            </div>
          </div>
          
          {/* Right Column - Compact Status Cards */}
          <div className="lg:col-span-2 space-y-4 overflow-y-auto">
            <IdentityOverview />
            <MetricsPanel />
            <StageLog />
          </div>
        </div>
      </main>
    </div>
  );
}
