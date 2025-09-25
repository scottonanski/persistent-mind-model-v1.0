'use client';

import { Navigation } from '@/components/layout/navigation';
import { EventsTable } from '@/components/ledger/events-table';
import { SQLConsole } from '@/components/ledger/sql-console';
import { useDeveloperMode } from '@/lib/developer-mode';

export default function LedgerPage() {
  const { isEnabled: devModeEnabled } = useDeveloperMode();
  
  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main className="container mx-auto px-4 py-8 h-[calc(100vh-4rem)] flex flex-col">
        <div className="flex-shrink-0 mb-6">
          <h1 className="text-3xl font-bold">Event Ledger</h1>
          <p className="text-muted-foreground">
            {devModeEnabled && ' • Developer Mode Enabled'}
          </p>
        </div>
        
        {devModeEnabled ? (
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 flex-1 min-h-0">
            <div className="xl:col-span-2 flex flex-col min-h-0">
              <EventsTable />
            </div>
            
            <div className="flex flex-col min-h-0">
              <SQLConsole />
            </div>
          </div>
        ) : (
          <div className="flex-1 min-h-0">
            <EventsTable />
          </div>
        )}
      </main>
    </div>
  );
}
