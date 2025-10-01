/**
 * API client for PMM Companion backend
 */

import config from './config';

export interface PMMEvent {
  id: number;
  kind: string;
  ts: string;
  content?: string;
  meta?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  hash?: string;
  prev_hash?: string;
}

export interface EventsResponse {
  version: string;
  events: PMMEvent[];
  pagination: {
    limit: number;
    count: number;
    next_after_id?: number;
    has_more?: boolean;
  };
  identity?: {
    name?: string;
  };
}

export interface MetricsResponse {
  version: string;
  metrics: {
    ias: number;
    gas: number;
    traits: {
      openness: number;
      conscientiousness: number;
      extraversion: number;
      agreeableness: number;
      neuroticism: number;
    };
    stage: {
      current: string;
    };
    last_updated: string;
  };
}

export interface ReflectionsResponse {
  version: string;
  reflections: PMMEvent[];
  count: number;
}

export interface CommitmentsResponse {
  version: string;
  commitments: Array<{
    id: number;
    ts: string;
    kind: string;
    content: string;
    meta?: Record<string, unknown>;
  }>;
  count: number;
}

export interface SQLQueryResponse {
  version: string;
  results: unknown[];
  count: number;
  execution_time_ms: number;
}

export interface ConsciousnessResponse {
  version: string;
  consciousness: {
    identity: {
      name: string;
      stage: string;
      stage_progress: number;
      birth_timestamp: string;
      days_alive: number;
    };
    vital_signs: {
      ias: number;
      gas: number;
      autonomy_level: number;
      self_awareness: number;
    };
    personality: {
      traits: {
        openness: number;
        conscientiousness: number;
        extraversion: number;
        agreeableness: number;
        neuroticism: number;
      };
    };
    evolution_metrics: {
      total_events: number;
      reflection_count: number;
      commitment_count: number;
      stage_reached: string;
    };
    latest_insight?: {
      content: string;
      timestamp: string;
      kind: string;
    };
    consciousness_state: {
      is_self_aware: boolean;
      is_autonomous: boolean;
      is_evolving: boolean;
    };
  };
}

export interface TraceResponse {
  version: string;
  traces: Array<{
    id: number;
    timestamp: string;
    session_id: string;
    query: string;
    total_nodes_visited: number;
    node_type_distribution: Record<string, number>;
    high_confidence_count: number;
    high_confidence_paths: Array<{
      node_type: string;
      confidence: number;
      edge_label?: string;
      reasoning?: string;
    }>;
    sampled_count: number;
    reasoning_steps: string[];
    duration_ms: number;
  }>;
  count: number;
}

export interface TraceStatsResponse {
  version: string;
  stats: {
    total_traces: number;
    total_nodes_visited: number;
    avg_nodes_per_trace: number;
    avg_duration_ms: number;
    node_type_distribution: Record<string, number>;
  };
}

class APIClient {
  private baseUrl: string;

  constructor() {
    this.baseUrl = config.api.baseUrl;
  }

  private async request<T>(endpoint: string, params?: Record<string, string | undefined>): Promise<T> {
    const url = new URL(endpoint, this.baseUrl);
    
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, value);
        }
      });
    }

    const response = await fetch(url.toString());
    
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  async getEvents(params?: {
    db?: string;
    limit?: number;
    after_id?: number;
    kind?: string;
    since_ts?: string;
    until_ts?: string;
  }): Promise<EventsResponse> {
    return this.request<EventsResponse>('/events', {
      db: params?.db,
      limit: params?.limit?.toString(),
      after_id: params?.after_id?.toString(),
      kind: params?.kind,
      since_ts: params?.since_ts,
      until_ts: params?.until_ts,
    });
  }

  async getMetrics(db?: string): Promise<MetricsResponse> {
    return this.request<MetricsResponse>('/metrics', { db });
  }

  async getConsciousness(db?: string): Promise<ConsciousnessResponse> {
    return this.request<ConsciousnessResponse>('/consciousness', { db });
  }

  async getReflections(params?: {
    db?: string;
    limit?: number;
  }): Promise<ReflectionsResponse> {
    return this.request<ReflectionsResponse>('/reflections', {
      db: params?.db,
      limit: params?.limit?.toString(),
    });
  }

  async getCommitments(params?: {
    db?: string;
    status?: string;
    limit?: number;
  }): Promise<CommitmentsResponse> {
    return this.request<CommitmentsResponse>('/commitments', {
      db: params?.db,
      status: params?.status,
      limit: params?.limit?.toString(),
    });
  }

  async executeSQL(db: string, query: string): Promise<SQLQueryResponse> {
    const response = await fetch(`${this.baseUrl}/events/sql`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ db, query }),
    });

    if (!response.ok) {
      throw new Error(`SQL query failed: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  async getTraces(db?: string, limit?: number, queryFilter?: string): Promise<TraceResponse> {
    return this.request<TraceResponse>('/traces', {
      db,
      limit: limit?.toString(),
      query_filter: queryFilter,
    });
  }

  async getTraceStats(db?: string): Promise<TraceStatsResponse> {
    return this.request<TraceStatsResponse>('/traces/stats/overview', { db });
  }

  async getTraceDetails(sessionId: string, db?: string): Promise<{
    version: string;
    summary: any;
    samples: any[];
    sample_count: number;
  }> {
    return this.request(`/traces/${sessionId}`, { db });
  }
}

export const apiClient = new APIClient();
export default apiClient;
