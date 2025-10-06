'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import config from '@/lib/config';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { MetricsSidebar } from './metrics-sidebar';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pending?: boolean;
  model?: string;
}

interface ModelInfo {
  name: string;
  provider: string;
  max_tokens: number;
  temperature: number;
  cost_per_1k_tokens: number;
  description?: string;
}

interface ModelsResponse {
  version: string;
  models: ModelInfo[];
  current?: {
    model: string;
    provider: string;
  };
  default?: string;
}

const API_BASE_URL = config.api.baseUrl;
const STORAGE_MESSAGES_KEY = 'pmm.chat.messages';
const STORAGE_MODEL_KEY = 'pmm.chat.model';

const createMessageId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
};

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const assistantIndexRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const hasMessages = messages.length > 0;
  const canSend = Boolean(!isStreaming && input.trim() && selectedModel && !modelsLoading);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    try {
      const storedMessages = window.localStorage.getItem(STORAGE_MESSAGES_KEY);
      if (storedMessages) {
        const parsed = JSON.parse(storedMessages);
        if (Array.isArray(parsed)) {
          setMessages(parsed as ChatMessage[]);
        }
      }
    } catch (err) {
      console.warn('Failed to restore chat messages', err);
    }

    try {
      const storedModel = window.localStorage.getItem(STORAGE_MODEL_KEY);
      if (storedModel) {
        setSelectedModel(storedModel);
      }
    } catch (err) {
      console.warn('Failed to restore chat model', err);
    }

    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    try {
      if (messages.length) {
        window.localStorage.setItem(STORAGE_MESSAGES_KEY, JSON.stringify(messages));
      } else {
        window.localStorage.removeItem(STORAGE_MESSAGES_KEY);
      }
    } catch (err) {
      console.warn('Failed to persist chat messages', err);
    }
  }, [messages]);

  useEffect(() => {
    if (!input.trim() && !isStreaming && inputRef.current) {
      inputRef.current.focus();
    }
  }, [input, isStreaming]);

  useEffect(() => {
    const loadModels = async () => {
      setModelsLoading(true);
      setModelError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/models`);
        if (!response.ok) {
          throw new Error(`Failed to load models (${response.status})`);
        }
        const data = (await response.json()) as ModelsResponse;
        setModels(data.models ?? []);
        const candidate =
          selectedModel ||
          data.current?.model ||
          data.default ||
          data.models?.[0]?.name ||
          '';

        // If the current model is not available in the runtime, find a suitable Ollama model
        if (candidate && data.models) {
          const modelExists = data.models.some(model => model.name === candidate);
          if (!modelExists) {
            // Try to find an Ollama model as fallback
            const ollamaModel = data.models.find(model => model.provider === 'ollama')?.name;
            if (ollamaModel) {
              setSelectedModel(ollamaModel);
              if (typeof window !== 'undefined') {
                try {
                  window.localStorage.setItem(STORAGE_MODEL_KEY, ollamaModel);
                } catch (err) {
                  console.warn('Failed to persist model selection', err);
                }
              }
              return;
            }
          }
        }

        setSelectedModel(candidate);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unable to load models';
        setModelError(message);
      } finally {
        setModelsLoading(false);
      }
    };

    loadModels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const historyPayload = useMemo(
    () => messages.map(({ role, content }) => ({ role, content })),
    [messages],
  );

  const appendAssistantContent = useCallback((delta: string) => {
    setMessages((prev) => {
      const idx = assistantIndexRef.current;
      if (idx === null || idx < 0 || idx >= prev.length) {
        return prev;
      }
      const next = [...prev];
      const current = next[idx];
      next[idx] = {
        ...current,
        pending: false,
        content: `${current.content}${delta}`,
      };
      return next;
    });
  }, []);

  const finalizeAssistant = useCallback(() => {
    setMessages((prev) => {
      const idx = assistantIndexRef.current;
      if (idx === null || idx < 0 || idx >= prev.length) {
        return prev;
      }
      const next = [...prev];
      next[idx] = { ...next[idx], pending: false };
      assistantIndexRef.current = null;
      return next;
    });
  }, []);

  const parseStreamChunk = useCallback(
    (chunk: string) => {
      const lines = chunk.split('\n');
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line || !line.startsWith('data:')) {
          continue;
        }
        const payload = line.replace(/^data:\s*/, '');
        if (!payload || payload === '[DONE]') {
          finalizeAssistant();
          continue;
        }
        try {
          const json = JSON.parse(payload);
          const delta = json?.choices?.[0]?.delta;
          if (typeof delta?.content === 'string') {
            appendAssistantContent(delta.content);
          }
        } catch (err) {
          console.warn('Failed to parse stream payload', err);
        }
      }
    },
    [appendAssistantContent, finalizeAssistant],
  );

  const resetAbortController = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
  }, []);

  const handleSend = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt || isStreaming || !selectedModel) {
      return;
    }

    resetAbortController();
    inputRef.current?.focus();
    setInput('');
    setError(null);

    const userMessage: ChatMessage = {
      id: createMessageId(),
      role: 'user',
      content: prompt,
    };
    const assistantPlaceholder: ChatMessage = {
      id: createMessageId(),
      role: 'assistant',
      content: '',
      pending: true,
      model: selectedModel,
    };

    setMessages((prev) => {
      const next = [...prev, userMessage, assistantPlaceholder];
      assistantIndexRef.current = next.length - 1;
      return next;
    });

    setIsStreaming(true);

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: selectedModel,
          messages: [...historyPayload, { role: 'user', content: prompt }],
          stream: true,
        }),
        signal: abortControllerRef.current?.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`Chat request failed (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const segments = buffer.split('\n\n');
        buffer = segments.pop() ?? '';
        for (const segment of segments) {
          parseStreamChunk(segment);
        }
      }

      if (buffer) {
        parseStreamChunk(buffer);
      }
    } catch (err) {
      const aborted = abortControllerRef.current?.signal.aborted;
      if (!aborted) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        setError(message);
        appendAssistantContent(`\n⚠️ ${message}`);
        finalizeAssistant();
      }
    } finally {
      setIsStreaming(false);
    }
  }, [appendAssistantContent, finalizeAssistant, historyPayload, input, isStreaming, parseStreamChunk, resetAbortController, selectedModel]);

  const handleStop = useCallback(() => {
    if (isStreaming) {
      abortControllerRef.current?.abort();
      finalizeAssistant();
      setIsStreaming(false);
      inputRef.current?.focus();
    }
  }, [finalizeAssistant, isStreaming]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <div className="flex h-full gap-4">
      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {modelError && (
          <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {modelError}
          </div>
        )}

        <div className="flex-1 p-4 overflow-hidden rounded-3xl border border-border/40 bg-[#202125] shadow-lg">
        <ScrollArea className="h-full">
          <div className="flex flex-col gap-6 p-6">
            {!hasMessages && (
              <div className="rounded-2xl border border-border/30 bg-[#2c2d32] p-6 text-sm text-muted-foreground shadow-inner">
                Start a conversation with PMM.
              </div>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  'mx-auto flex w-full max-w-3xl gap-3',
                  message.role === 'user' ? 'justify-end' : 'justify-start',
                )}
              >
                <div className="flex flex-col gap-1">
                  {message.role === 'assistant' && message.model && (
                    <div className="px-1 text-xs text-muted-foreground">
                      {message.model}
                    </div>
                  )}
                  <div
                    className={cn(
                      'max-w-3xl rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm',
                      message.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-card text-card-foreground ring-1 ring-border',
                    )}
                  >
                    {message.content || (message.pending ? '…' : '')}
                  </div>
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      </div>

      <div className="mt-4 space-y-2">
        {error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}
        <div className="rounded-2xl border border-border/40 bg-[#202125] shadow-lg">
          <Textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            className="min-h-[120px] resize-none border-0 bg-transparent px-4 py-3 text-base focus-visible:ring-0 focus-visible:ring-offset-0"
            disabled={isStreaming}
            ref={inputRef}
          />
          <div className="flex items-center justify-between border-t border-border/40 px-4 py-3">
            <div className="text-xs text-muted-foreground">
              {isStreaming ? 'Streaming response…' : 'Powered by PMM Runtime'}
            </div>
            <div className="flex gap-2">
              {isStreaming && (
                <Button variant="outline" size="sm" onClick={handleStop}>
                  Stop
                </Button>
              )}
              <Button size="sm" onClick={handleSend} disabled={!canSend}>
                Send
              </Button>
            </div>
          </div>
        </div>
      </div>
      </div>

      {/* Right sidebar with model list */}
      <aside className="flex w-72 flex-col rounded-3xl border border-border/40 bg-[#202125] shadow-lg">
        <div className="border-b border-border/40 px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Available Models</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Select a runtime model
          </p>
        </div>
        
        <ScrollArea className="flex-1">
          <div className="p-2">
            {modelsLoading && (
              <div className="px-3 py-6 text-center text-xs text-muted-foreground">
                Loading models…
              </div>
            )}
            
            {!modelsLoading && models.length === 0 && (
              <div className="px-3 py-6 text-center text-xs text-muted-foreground">
                No models available
              </div>
            )}
            
            {models.map((model) => (
              <button
                key={model.name}
                onClick={() => {
                  setSelectedModel(model.name);
                  if (typeof window !== 'undefined') {
                    try {
                      window.localStorage.setItem(STORAGE_MODEL_KEY, model.name);
                    } catch (err) {
                      console.warn('Failed to persist model selection', err);
                    }
                  }
                }}
                disabled={isStreaming}
                className={cn(
                  'w-full rounded-lg px-3 py-2.5 text-left transition-colors',
                  'hover:bg-[#26272c] disabled:opacity-50 disabled:cursor-not-allowed',
                  selectedModel === model.name
                    ? 'bg-[#26272c] ring-1 ring-border'
                    : 'bg-transparent'
                )}
              >
                <div className="flex flex-col gap-1">
                  <span className="text-sm font-medium text-foreground">
                    {model.name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {model.provider}
                  </span>
                  {model.description && (
                    <span className="mt-0.5 text-xs text-muted-foreground/80">
                      {model.description}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </ScrollArea>
      </aside>

      {/* Metrics sidebar */}
      <MetricsSidebar />
    </div>
  );
}
