import { Navigation } from '@/components/layout/navigation';
import { Chat } from '@/components/chat/chat';

export default function ChatPage() {
  return (
    <div className="min-h-screen bg-[#1c1c1f]">
      <Navigation />
      <main className="container mx-auto px-4 py-6">
        <div className="mb-6 space-y-2">
          <h1 className="text-3xl font-bold">Chat</h1>
          <p className="text-sm text-muted-foreground">
            Converse with the Persistent Mind Model using a LibreChat-inspired interface. Conversations persist in the PMM ledger.
          </p>
        </div>
        <div className="h-[calc(100vh-220px)] min-h-[520px]">
          <Chat />
        </div>
      </main>
    </div>
  );
}
