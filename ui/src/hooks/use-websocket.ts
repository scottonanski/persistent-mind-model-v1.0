import { useEffect, useRef, useState } from 'react';
import { useDatabase } from '@/lib/database-context';

export interface WebSocketMessage {
  type: 'event' | 'heartbeat';
  data?: any;
  timestamp: string;
}

export function useWebSocket(enabled: boolean = true) {
  const { selectedDb } = useDatabase();
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const wsUrl = `ws://localhost:8001/stream${selectedDb ? `?db=${encodeURIComponent(selectedDb)}` : ''}`;
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      wsRef.current.onclose = () => {
        console.log('WebSocket disconnected - falling back to polling');
        setIsConnected(false);
        
        // Don't attempt to reconnect if WebSocket endpoint doesn't exist
        // The UI will gracefully fall back to polling
      };

      wsRef.current.onerror = (error) => {
        // Suppress WebSocket errors when endpoint doesn't exist - this is expected
        // The UI gracefully falls back to polling mode
        setIsConnected(false);
      };
    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
    }
  };

  const disconnect = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setIsConnected(false);
  };

  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [enabled, selectedDb]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    isConnected,
    lastMessage,
    connect,
    disconnect
  };
}
