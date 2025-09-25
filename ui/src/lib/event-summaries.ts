import { PMMEvent } from './api';

/**
 * Generate a meaningful summary for an event based on its kind and metadata
 * Following the fallback summary rules for timeline tooltips
 */
export function generateEventSummary(event: PMMEvent): string {
  const { kind, content, meta } = event;
  
  // If content exists and is meaningful, use it (but keep it short)
  if (content && content.trim() && content.trim() !== '{}' && content.trim() !== 'null') {
    return content.length > 100 ? content.substring(0, 100) + '...' : content;
  }
  
  // Parse meta if it's a string
  let metaObj: any = {};
  try {
    metaObj = typeof meta === 'string' ? JSON.parse(meta) : (meta || {});
  } catch {
    metaObj = {};
  }
  
  // Generate summary based on event kind
  switch (kind) {
    // Identity-related
    case 'identity_adopt':
      return `Adopted identity: ${metaObj.name || 'unknown'} (confidence ${metaObj.confidence || 'unknown'})`;
    
    case 'identity_checkpoint':
      return `Identity: ${metaObj.name || 'unknown'}, stage=${metaObj.stage || 'unknown'}`;
    
    case 'name_updated':
      return `Name updated: ${metaObj.old_name || 'unknown'} → ${metaObj.new_name || 'unknown'}`;
    
    case 'name_attempt_user':
    case 'name_attempt_system':
      return `Name attempt: ${metaObj.reason || content || 'no reason provided'}`;
    
    // Commitments
    case 'commitment_open':
      return `Commitment opened: ${metaObj.intent || metaObj.project || 'unknown commitment'}`;
    
    case 'commitment_close':
      return `Commitment closed: ${metaObj.intent || metaObj.project || 'unknown commitment'}`;
    
    case 'commitment_expire':
      return `Commitment expired: ${metaObj.intent || metaObj.project || 'unknown commitment'}`;
    
    case 'commitment_priority':
      return `Commitment priority: ${metaObj.priority || 'unknown'}`;
    
    case 'priority_update':
      return `Priority updated: ${metaObj.old || 'unknown'} → ${metaObj.new || 'unknown'}`;
    
    // Reflections
    case 'reflection':
      return `Reflection: ${metaObj.digest || metaObj.reason || 'reflection event'}`;
    
    case 'meta_reflection':
      return `Meta Reflection: ${metaObj.digest || metaObj.reason || 'meta reflection event'}`;
    
    case 'reflection_action':
      return `Reflection Action: ${metaObj.summary || metaObj.reason || 'action taken'}`;
    
    case 'reflection_check':
      return 'Reflection Check';
    
    case 'reflection_skipped':
      return `Reflection Skipped: ${metaObj.reason || 'no reason provided'}`;
    
    case 'reflection_forced':
      return `Reflection Forced: ${metaObj.reason || 'no reason provided'}`;
    
    case 'reflection_rejected':
      return `Reflection Rejected: ${metaObj.reason || 'no reason provided'}`;
    
    case 'reflection_quality':
      return `Reflection Quality: ${metaObj.quality || 'unknown'}`;
    
    case 'reflection_discarded':
      return `Reflection Discarded: ${metaObj.reason || 'no reason provided'}`;
    
    // Metrics / Traits / Stages
    case 'metrics_update':
      return `Metrics: IAS=${metaObj.IAS || 'unknown'}, GAS=${metaObj.GAS || 'unknown'}`;
    
    case 'trait_update':
      return `Trait update: ${metaObj.trait || 'unknown'} ${metaObj.delta || ''}`;
    
    case 'stage_progress':
      return `Stage progress: ${metaObj.stage || 'unknown'}, ${metaObj.progress || 'unknown'}%`;
    
    case 'stage_transition':
      return `Stage transition: ${metaObj.from || 'unknown'} → ${metaObj.to || 'unknown'}`;
    
    case 'stage_update':
      return `Stage update: ${metaObj.stage || 'unknown'}`;
    
    case 'stage_reflection':
      return `Stage reflection: ${metaObj.stage || 'unknown'}`;
    
    // Learning / Evaluation
    case 'curriculum_update':
      return `Curriculum update: ${metaObj.summary || 'curriculum modified'}`;
    
    case 'policy_update':
      return `Policy update: ${metaObj.summary || 'policy modified'}`;
    
    case 'evaluation_report':
      return `Evaluation report: ${metaObj.score || metaObj.summary || 'evaluation completed'}`;
    
    case 'evaluation_summary':
      return `Evaluation summary: ${metaObj.summary || 'evaluation summary'}`;
    
    case 'evidence_candidate':
      return `Evidence candidate: ${metaObj.digest || 'evidence identified'}`;
    
    case 'insight_ready':
      return `Insight ready: ${metaObj.summary || 'insight available'}`;
    
    case 'introspection_query':
      return `Introspection query: ${metaObj.query || 'introspection performed'}`;
    
    // Bandit / Guidance
    case 'bandit_arm_chosen':
      return `Bandit arm chosen: ${metaObj.arm || 'unknown arm'}`;
    
    case 'bandit_reward':
      return `Bandit reward: ${metaObj.reward || 'unknown reward'}`;
    
    case 'bandit_guidance_bias':
      return `Guidance bias: ${metaObj.bias || 'unknown bias'}`;
    
    // Other system events
    case 'audit_report':
      return `Audit report: ${metaObj.summary || 'audit completed'}`;
    
    case 'embedding_indexed':
      return `Embedding indexed: ${metaObj.digest || 'embedding processed'}`;
    
    case 'knowledge_assert':
      return `Knowledge assert: ${metaObj.summary || 'knowledge assertion'}`;
    
    case 'semantic_growth_report':
      return `Semantic growth report: ${metaObj.summary || 'semantic growth tracked'}`;
    
    case 'self_suggestion':
      return `Self suggestion: ${metaObj.summary || 'suggestion made'}`;
    
    case 'response':
      return `Response: ${metaObj.summary || metaObj.digest || 'response generated'}`;
    
    case 'invariant_violation':
      return `Invariant violation: ${metaObj.reason || 'violation detected'}`;
    
    case 'user':
      return `User event: ${metaObj.summary || 'user interaction'}`;
    
    case 'llm_latency':
      return `LLM latency: ${metaObj.ms || 'unknown'}ms`;
    
    case 'scene_compact':
      return `Scene compacted: ${metaObj.summary || 'scene compaction'}`;
    
    case 'recall_suggest':
      return `Recall suggest: ${metaObj.summary || 'recall suggestion'}`;
    
    // Fallback rule
    default:
      return `Structured data event: ${kind.replace('_', ' ')}`;
  }
}

/**
 * Generate a tooltip content string for an event
 */
export function generateTooltipContent(event: PMMEvent): string {
  const summary = generateEventSummary(event);
  const timestamp = new Date(event.ts).toLocaleString();
  
  return `${event.kind.replace('_', ' ').toUpperCase()}\n${timestamp}\n\n${summary}`;
}
