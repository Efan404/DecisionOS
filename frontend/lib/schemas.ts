import { z } from 'zod'

export const directionIdSchema = z.enum(['A', 'B', 'C', 'D', 'E', 'F'])
export const pathIdSchema = z.enum(['pathA', 'pathB', 'pathC'])
export const prioritySchema = z.enum(['P0', 'P1', 'P2'])
export const OPPORTUNITY_MIN_COUNT = 1
export const OPPORTUNITY_MAX_COUNT = 6
export const OPPORTUNITY_DEFAULT_COUNT = 3

export const directionSchema = z.object({
  id: directionIdSchema,
  title: z.string().min(1),
  one_liner: z.string().min(1),
  pain_tags: z.array(z.string().min(1)),
})

export const opportunityInputSchema = z.object({
  idea_seed: z.string().min(1),
  count: z
    .number()
    .int()
    .min(OPPORTUNITY_MIN_COUNT)
    .max(OPPORTUNITY_MAX_COUNT)
    .default(OPPORTUNITY_DEFAULT_COUNT),
})

export const opportunityOutputSchema = z.object({
  directions: z.array(directionSchema).min(OPPORTUNITY_MIN_COUNT).max(OPPORTUNITY_MAX_COUNT),
})

export const pathOptionSchema = z.object({
  id: pathIdSchema,
  name: z.string().min(1),
  focus: z.string().min(1),
})

export const PATHS = [
  { id: 'pathA', name: 'Feature Definition Path', focus: 'What to build' },
  { id: 'pathB', name: 'Decision Compression Path', focus: 'What not to build' },
  { id: 'pathC', name: 'Rapid Validation Path', focus: 'Smallest demoable slice' },
] satisfies Array<z.infer<typeof pathOptionSchema>>

export const scoreBreakdownSchema = z.object({
  technical_feasibility: z.number().min(0).max(10),
  market_viability: z.number().min(0).max(10),
  execution_risk: z.number().min(0).max(10),
})

export const reasoningBreakdownSchema = z.object({
  technical_feasibility: z.string().min(1),
  market_viability: z.string().min(1),
  execution_risk: z.string().min(1),
})

export const feasibilityPlanSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  summary: z.string().min(1),
  score_overall: z.number().min(0).max(10),
  scores: scoreBreakdownSchema,
  reasoning: reasoningBreakdownSchema,
  recommended_positioning: z.string().min(1),
})

export const confirmedPathNodeSchema = z.object({
  id: z.string().min(1),
  content: z.string().min(1),
  expansion_pattern: z.string().nullable().optional(),
  edge_label: z.string().nullable().optional(),
  depth: z.number().int().nonnegative().optional(),
})

export const confirmedPathContextSchema = z.object({
  confirmed_path_id: z.string().min(1),
  confirmed_node_id: z.string().min(1),
  confirmed_node_content: z.string().min(1),
  confirmed_path_summary: z.string().min(1).optional(),
})

export const feasibilityInputSchema = z.object({
  idea_seed: z.string().min(1),
  confirmed_path_id: z.string().min(1),
  confirmed_node_id: z.string().min(1),
  confirmed_node_content: z.string().min(1),
  confirmed_path_summary: z.string().min(1).optional(),
})

export const feasibilityOutputSchema = z.object({
  plans: z.array(feasibilityPlanSchema).length(3),
})

export const inScopeItemSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  desc: z.string().min(1),
  priority: prioritySchema,
})

export const outScopeItemSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  desc: z.string().min(1),
  reason: z.string().min(1),
})

export const scopeInputSchema = z.object({
  idea_seed: z.string().min(1),
  confirmed_path_id: z.string().min(1),
  confirmed_node_id: z.string().min(1),
  confirmed_node_content: z.string().min(1),
  confirmed_path_summary: z.string().min(1).optional(),
  selected_plan_id: z.string().min(1),
  feasibility: feasibilityOutputSchema,
})

export const scopeOutputSchema = z.object({
  in_scope: z.array(inScopeItemSchema),
  out_scope: z.array(outScopeItemSchema),
})

export const scopeBaselineStatusSchema = z.enum(['draft', 'frozen', 'superseded'])
export const scopeBaselineLaneSchema = z.enum(['in', 'out'])

export const scopeBaselineItemSchema = z.object({
  id: z.string().min(1),
  baseline_id: z.string().min(1),
  lane: scopeBaselineLaneSchema,
  content: z.string().min(1),
  display_order: z.number().int().nonnegative(),
  created_at: z.string().min(1),
})

export const scopeBaselineSchema = z.object({
  id: z.string().min(1),
  idea_id: z.string().min(1),
  version: z.number().int().positive(),
  status: scopeBaselineStatusSchema,
  source_baseline_id: z.string().min(1).nullable().optional(),
  created_at: z.string().min(1),
  frozen_at: z.string().min(1).nullable().optional(),
})

export const scopeBaselineOutSchema = scopeBaselineSchema.extend({
  items: z.array(scopeBaselineItemSchema),
})

export const scopeBaselineResponseSchema = z.object({
  baseline: scopeBaselineSchema,
  items: z.array(scopeBaselineItemSchema),
})

export const scopeDraftResponseSchema = scopeBaselineResponseSchema.extend({
  readonly: z.boolean(),
})

export const scopeDraftItemInputSchema = z.object({
  lane: scopeBaselineLaneSchema,
  content: z.string().min(1),
  display_order: z.number().int().nonnegative(),
})

export const scopeDraftUpdateRequestSchema = z.object({
  version: z.number().int().nonnegative(),
  items: z.array(scopeDraftItemInputSchema),
})

export const scopeVersionedRequestSchema = z.object({
  version: z.number().int().nonnegative(),
})

export const prdSourceRefSchema = z.enum(['step2', 'step3', 'step4'])
export const prdBacklogTypeSchema = z.enum(['epic', 'story', 'task'])

export const prdSectionSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  content: z.string().min(1),
})

export const prdRequirementSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  description: z.string().min(1),
  rationale: z.string().min(1),
  acceptance_criteria: z.array(z.string().min(1)).min(2),
  source_refs: z.array(prdSourceRefSchema).min(1),
})

export const prdBacklogItemSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  requirement_id: z.string().min(1),
  priority: prioritySchema,
  type: prdBacklogTypeSchema,
  summary: z.string().min(1),
  acceptance_criteria: z.array(z.string().min(1)).min(2),
  source_refs: z.array(prdSourceRefSchema).min(1),
  depends_on: z.array(z.string().min(1)).default([]),
})

export const prdBacklogSchema = z.object({
  // commented out for demo – was: .min(8).max(15)
  items: z.array(prdBacklogItemSchema),
})

export const prdGenerationMetaSchema = z.object({
  provider_id: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  confirmed_path_id: z.string().min(1),
  selected_plan_id: z.string().min(1),
  baseline_id: z.string().min(1),
})

export const prdInputSchema = z.object({
  baseline_id: z.string().min(1),
})

export const prdOutputSchema = z.object({
  markdown: z.string().min(1),
  sections: z.array(prdSectionSchema).min(6),
  // commented out for demo – was: .min(6).max(12)
  requirements: z.array(prdRequirementSchema),
  backlog: prdBacklogSchema,
  generation_meta: prdGenerationMetaSchema,
})

export const prdBundleSchema = z.object({
  baseline_id: z.string().min(1),
  context_fingerprint: z.string().min(1),
  generated_at: z.string().min(1),
  generation_meta: prdGenerationMetaSchema,
  output: prdOutputSchema,
})

export const prdFeedbackDimensionsSchema = z.object({
  clarity: z.number().int().min(1).max(5),
  completeness: z.number().int().min(1).max(5),
  actionability: z.number().int().min(1).max(5),
  scope_fit: z.number().int().min(1).max(5),
})

export const prdFeedbackLatestSchema = z.object({
  baseline_id: z.string().min(1),
  submitted_at: z.string().min(1),
  rating_overall: z.number().int().min(1).max(5),
  rating_dimensions: prdFeedbackDimensionsSchema,
  comment: z.string().max(2000).nullable().optional(),
})

export const prdFeedbackRequestSchema = z.object({
  version: z.number().int().nonnegative(),
  baseline_id: z.string().min(1),
  rating_overall: z.number().int().min(1).max(5),
  rating_dimensions: prdFeedbackDimensionsSchema,
  comment: z.string().max(2000).optional(),
})

export const ideaStageSchema = z.enum(['idea_canvas', 'feasibility', 'scope_freeze', 'prd'])

export const ideaStatusSchema = z.enum(['draft', 'active', 'frozen', 'archived'])

export const ideaSummarySchema = z.object({
  id: z.string().min(1),
  workspace_id: z.string().min(1),
  title: z.string().min(1),
  idea_seed: z.string().nullable().optional(),
  stage: ideaStageSchema,
  status: ideaStatusSchema,
  version: z.number().int().nonnegative(),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  archived_at: z.string().nullable().optional(),
})

export const decisionContextSchema = z.object({
  session_id: z.string().min(1),
  created_at: z.string().min(1),
  context_schema_version: z.number().int().positive().optional(),
  idea_seed: z.string().min(1).optional(),
  opportunity: opportunityOutputSchema.optional(),
  feasibility: feasibilityOutputSchema.optional(),
  selected_plan_id: z.string().min(1).optional(),
  scope: scopeOutputSchema.optional(),
  scope_frozen: z.boolean().optional(),
  current_scope_baseline_id: z.string().min(1).optional(),
  current_scope_baseline_version: z.number().int().positive().optional(),
  prd: prdOutputSchema.optional(),
  prd_bundle: prdBundleSchema.optional(),
  prd_feedback_latest: prdFeedbackLatestSchema.optional(),
  confirmed_dag_path_id: z.string().optional(),
  confirmed_dag_node_id: z.string().optional(),
  confirmed_dag_node_content: z.string().optional(),
  confirmed_dag_path_summary: z.string().optional(),
})

export const ideaDetailSchema = ideaSummarySchema.extend({
  context: decisionContextSchema,
})

export const ideasListResponseSchema = z.object({
  items: z.array(ideaSummarySchema),
  next_cursor: z.string().nullable().optional(),
})

export const createIdeaRequestSchema = z.object({
  title: z.string().min(1),
  idea_seed: z.string().optional(),
})

export const patchIdeaRequestSchema = z.object({
  title: z.string().min(1).optional(),
  status: ideaStatusSchema.optional(),
  version: z.number().int().nonnegative(),
})

export const patchIdeaContextRequestSchema = z.object({
  context: decisionContextSchema,
  version: z.number().int().nonnegative(),
})

export const agentEnvelopeSchema = z.object({
  idea_id: z.string().min(1),
  idea_version: z.number().int().nonnegative(),
  data: z.unknown(),
})

export const aiProviderKindSchema = z.enum(['openai_compatible', 'anthropic'])

export const aiProviderConfigSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  kind: aiProviderKindSchema,
  base_url: z.string().min(1),
  api_key: z.string().optional(),
  model: z.string().optional(),
  enabled: z.boolean().default(true),
  timeout_seconds: z.number().min(1).max(120).default(20),
  temperature: z.number().min(0).max(2).default(0.2),
})

export const aiSettingsSchema = z.object({
  id: z.string().min(1),
  providers: z.array(aiProviderConfigSchema),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
})

export const patchAiSettingsRequestSchema = z.object({
  providers: z.array(aiProviderConfigSchema),
})

export const testAiProviderRequestSchema = z.object({
  provider: aiProviderConfigSchema,
})

export const testAiProviderResponseSchema = z.object({
  ok: z.boolean(),
  latency_ms: z.number().int().nonnegative(),
  message: z.string().min(1),
})

export const authUserSchema = z.object({
  id: z.string().min(1),
  username: z.string().min(1),
  role: z.enum(['admin', 'user']),
})

export const authLoginRequestSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
})

export const authLoginResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal('bearer'),
  expires_in: z.number().int().positive(),
  user: authUserSchema,
})

export type DirectionId = z.infer<typeof directionIdSchema>
export type PathId = z.infer<typeof pathIdSchema>
export type Priority = z.infer<typeof prioritySchema>
export type Direction = z.infer<typeof directionSchema>
export type OpportunityInput = z.infer<typeof opportunityInputSchema>
export type OpportunityOutput = z.infer<typeof opportunityOutputSchema>
export type PathOption = z.infer<typeof pathOptionSchema>
export type FeasibilityScores = z.infer<typeof scoreBreakdownSchema>
export type FeasibilityReasoning = z.infer<typeof reasoningBreakdownSchema>
export type FeasibilityPlan = z.infer<typeof feasibilityPlanSchema>
export type ConfirmedPathNode = z.infer<typeof confirmedPathNodeSchema>
export type ConfirmedPathContext = z.infer<typeof confirmedPathContextSchema>
export type FeasibilityInput = z.infer<typeof feasibilityInputSchema>
export type FeasibilityOutput = z.infer<typeof feasibilityOutputSchema>
export type InScopeItem = z.infer<typeof inScopeItemSchema>
export type OutScopeItem = z.infer<typeof outScopeItemSchema>
export type ScopeInput = z.infer<typeof scopeInputSchema>
export type ScopeOutput = z.infer<typeof scopeOutputSchema>
export type ScopeBaselineStatus = z.infer<typeof scopeBaselineStatusSchema>
export type ScopeBaselineLane = z.infer<typeof scopeBaselineLaneSchema>
export type ScopeBaselineItem = z.infer<typeof scopeBaselineItemSchema>
export type ScopeBaseline = z.infer<typeof scopeBaselineSchema>
export type ScopeBaselineOut = z.infer<typeof scopeBaselineOutSchema>
export type ScopeBaselineResponse = z.infer<typeof scopeBaselineResponseSchema>
export type ScopeDraftResponse = z.infer<typeof scopeDraftResponseSchema>
export type ScopeDraftItemInput = z.infer<typeof scopeDraftItemInputSchema>
export type ScopeDraftUpdateRequest = z.infer<typeof scopeDraftUpdateRequestSchema>
export type ScopeVersionedRequest = z.infer<typeof scopeVersionedRequestSchema>
export type PrdSourceRef = z.infer<typeof prdSourceRefSchema>
export type PrdBacklogType = z.infer<typeof prdBacklogTypeSchema>
export type PrdSection = z.infer<typeof prdSectionSchema>
export type PrdRequirement = z.infer<typeof prdRequirementSchema>
export type PrdBacklogItem = z.infer<typeof prdBacklogItemSchema>
export type PrdBacklog = z.infer<typeof prdBacklogSchema>
export type PrdGenerationMeta = z.infer<typeof prdGenerationMetaSchema>
export type PrdInput = z.infer<typeof prdInputSchema>
export type PrdOutput = z.infer<typeof prdOutputSchema>
export type PrdBundle = z.infer<typeof prdBundleSchema>
export type PrdFeedbackDimensions = z.infer<typeof prdFeedbackDimensionsSchema>
export type PrdFeedbackLatest = z.infer<typeof prdFeedbackLatestSchema>
export type PrdFeedbackRequest = z.infer<typeof prdFeedbackRequestSchema>
export type DecisionContext = z.infer<typeof decisionContextSchema>
export type IdeaStage = z.infer<typeof ideaStageSchema>
export type IdeaStatus = z.infer<typeof ideaStatusSchema>
export type IdeaSummary = z.infer<typeof ideaSummarySchema>
export type IdeaDetail = z.infer<typeof ideaDetailSchema>
export type IdeasListResponse = z.infer<typeof ideasListResponseSchema>
export type CreateIdeaRequest = z.infer<typeof createIdeaRequestSchema>
export type PatchIdeaRequest = z.infer<typeof patchIdeaRequestSchema>
export type PatchIdeaContextRequest = z.infer<typeof patchIdeaContextRequestSchema>
export type AgentEnvelope = z.infer<typeof agentEnvelopeSchema>
export type AIProviderKind = z.infer<typeof aiProviderKindSchema>
export type AIProviderConfig = z.infer<typeof aiProviderConfigSchema>
export type AISettings = z.infer<typeof aiSettingsSchema>
export type PatchAISettingsRequest = z.infer<typeof patchAiSettingsRequestSchema>
export type TestAIProviderRequest = z.infer<typeof testAiProviderRequestSchema>
export type TestAIProviderResponse = z.infer<typeof testAiProviderResponseSchema>
export type AuthUser = z.infer<typeof authUserSchema>
export type AuthLoginRequest = z.infer<typeof authLoginRequestSchema>
export type AuthLoginResponse = z.infer<typeof authLoginResponseSchema>
