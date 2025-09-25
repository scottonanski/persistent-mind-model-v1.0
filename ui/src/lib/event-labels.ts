/**
 * Event label generation utilities for PMM Companion UI
 */

/**
 * Generate a human-readable label for an event based on its kind and meta data
 * @param event - The PMM event object
 * @returns A meaningful label string
 */
export function getEventLabel(event: {
  id: number;
  kind: string;
  content?: string;
  meta?: Record<string, unknown>;
  ts: string;
}): string {
  // If content exists and is meaningful, use it
  if (event.content && event.content.trim() && event.content !== '—') {
    return event.content;
  }

  // Otherwise, generate label from kind and meta
  const meta = event.meta || {};
  const kind = event.kind;

  switch (kind) {
    // Identity events
    case 'identity_adopt':
      return `Identity Adopt – ${meta.name || 'Unknown'}`;

    case 'identity_checkpoint':
      return `Identity Checkpoint – ${meta.name || 'Unknown'}, stage=${meta.stage || 'S0'}`;

    case 'name_updated':
      return `Name Updated – ${meta.new_name || meta.name || 'Unknown'}`;

    case 'name_attempt_user':
      return `Name Attempt (user) – ${event.content || meta.suggestion || 'Unknown'}`;

    case 'name_attempt_system':
      return `Name Attempt (system) – ${event.content || meta.suggestion || 'Unknown'}`;

    case 'naming_intent_classified':
      return `Naming Intent – ${meta.intent || 'Unknown'}`;

    // Reflection events
    case 'reflection':
      return `Reflection – reason: ${meta.reason || 'Unknown'}`;

    case 'meta_reflection':
      return `Meta Reflection – ${meta.summary || meta.reason || 'Unknown'}`;

    case 'reflection_action':
      return `Reflection Action – ${meta.action || 'Unknown'}`;

    case 'reflection_check':
      return `Reflection Check – ${meta.result || 'Unknown'}`;

    case 'reflection_discarded':
      return `Reflection Discarded – ${meta.reason || 'Unknown'}`;

    case 'reflection_forced':
      return `Forced Reflection – ${meta.trigger || 'Unknown'}`;

    case 'reflection_quality':
      return `Reflection Quality – ${meta.quality || 'Unknown'}`;

    case 'reflection_rejected':
      return `Reflection Rejected – ${meta.reason || 'Unknown'}`;

    case 'reflection_skipped':
      return 'Reflection Skipped';

    // Commitment events
    case 'commitment_open':
      return `Commitment (open) – ${meta.intent || meta.project || meta.text || 'Unknown'}`;

    case 'commitment_close':
      return `Commitment (closed) – ${meta.intent || meta.project || meta.text || 'Unknown'}`;

    case 'commitment_expire':
      return `Commitment (expired) – ${meta.intent || meta.project || meta.text || 'Unknown'}`;

    case 'commitment_priority':
      return `Commitment Priority – ${meta.priority || 'Unknown'}`;

    // Stage events
    case 'stage_progress':
      return `Stage Progress – ${meta.stage || 'Unknown'}`;

    case 'stage_reflection':
      return `Stage Reflection – ${meta.summary || 'Unknown'}`;

    case 'stage_transition':
      return `Stage Transition – ${meta.from || 'S0'} → ${meta.to || 'Unknown'}`;

    case 'stage_update':
      return `Stage Update – now ${meta.stage || 'Unknown'}`;

    // Metrics events
    case 'metrics_update':
      const ias = meta.IAS ?? meta.ias;
      const gas = meta.GAS ?? meta.gas;
      return `Metrics Update – IAS=${ias ?? '?.??'}, GAS=${gas ?? '?.??'}`;

    case 'metrics':
      return `Metrics – ${meta.snapshot_summary || 'snapshot'}`;

    case 'trait_update':
      return `Trait Update – ${meta.trait}=${meta.value}`;

    // Curriculum and policy
    case 'curriculum_update':
      return `Curriculum Update – ${meta.summary || 'Unknown'}`;

    case 'policy_update':
      return `Policy Update – ${meta.summary || 'Unknown'}`;

    // Evaluation
    case 'evaluation_report':
      return `Evaluation Report – ${meta.score || 'Unknown'}`;

    case 'evaluation_summary':
      return `Evaluation Summary – ${meta.headline || 'Unknown'}`;

    // Bandit
    case 'bandit_arm_chosen':
      return `Bandit Arm Chosen – ${meta.arm || 'Unknown'}`;

    case 'bandit_guidance_bias':
      return `Bandit Guidance Bias – ${meta.bias || 'Unknown'}`;

    case 'bandit_reward':
      return `Bandit Reward – ${meta.value || 'Unknown'}`;

    // Introspection
    case 'introspection_query':
      return `Introspection Query – ${meta.query || 'Unknown'}`;

    case 'insight_ready':
      return `Insight Ready – ${meta.topic || 'Unknown'}`;

    case 'self_suggestion':
      return `Self Suggestion – ${meta.suggestion || 'Unknown'}`;

    case 'knowledge_assert':
      return `Knowledge Assert – ${meta.claim || 'Unknown'}`;

    case 'semantic_growth_report':
      return `Semantic Growth Report – ${meta.summary || 'Unknown'}`;

    case 'embedding_indexed':
      return `Embedding Indexed – ${meta.digest || meta.keywords || 'Unknown'}`;

    // Autonomy
    case 'autonomy_tick':
      return `Autonomy Tick – ${meta.tick || 'Unknown'}`;

    case 'audit_report':
      return `Audit Report – ${meta.result || 'Unknown'}`;

    case 'invariant_violation':
      return `Invariant Violation – ${meta.message || 'Unknown'}`;

    case 'llm_latency':
      return `LLM Latency – ${meta.ms || 'Unknown'}`;

    case 'evolution':
      const changes = meta.changes;
      if (changes && typeof changes === 'object') {
        const changeKeys = Object.keys(changes);
        return `Evolution – ${changeKeys.length > 0 ? changeKeys.join(', ') : 'Unknown'}`;
      }
      return 'Evolution – changes';

    case 'response':
      return `Response – ${event.content || meta.excerpt || 'Unknown'}`;

    case 'scene_compact':
      return `Scene Compact – ${meta.scene_id || 'Unknown'}`;

    case 'recall_suggest':
      return `Recall Suggest – ${meta.suggestion || 'Unknown'}`;

    case 'user':
      return `User Event – ${event.content || 'Unknown'}`;

    // Default fallback
    default:
      // Try to extract any meaningful text from meta
      if (meta && typeof meta === 'object') {
        const metaKeys = Object.keys(meta);
        if (metaKeys.length > 0) {
          const firstKey = metaKeys[0];
          const firstValue = meta[firstKey];
          if (typeof firstValue === 'string' && firstValue.length > 0) {
            return `${kind} – ${firstValue}`;
          }
          if (typeof firstValue === 'number') {
            return `${kind} – ${firstValue}`;
          }
        }
      }
      return 'Structured Data';
  }
}
