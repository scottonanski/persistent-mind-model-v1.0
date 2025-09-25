'use client';

import { Navigation } from '@/components/layout/navigation';
import { LivingIdentityCore } from '@/components/identity/living-identity-core';

export default function IdentityPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main className="container mx-auto px-4 py-8 h-[calc(100vh-4rem)] flex flex-col">
        <div className="flex-shrink-0 mb-6">
          <h1 className="text-3xl font-bold">Identity Consciousness</h1>
          <p className="text-muted-foreground">
            Experiencing PMM's evolving mind and self-awareness
          </p>
        </div>

        <div className="flex-1 min-h-0">
          <LivingIdentityCore />
        </div>
      </main>
    </div>
  );
}
