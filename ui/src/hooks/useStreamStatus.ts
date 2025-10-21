"use client";

import { useEffect, useState } from "react";

/**
 * Tracks whether text is still streaming in.
 * Returns [isStreaming, setStreaming] so you can override if needed.
 */
export function useStreamStatus(text: string, delayMs = 300): [boolean, (v: boolean) => void] {
  const [isStreaming, setStreaming] = useState(true);

  useEffect(() => {
    if (!text) return;
    const timeout = setTimeout(() => setStreaming(false), delayMs);
    return () => clearTimeout(timeout);
  }, [text]);

  return [isStreaming, setStreaming];
}
