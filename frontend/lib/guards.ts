import type { DecisionContext } from './schemas'

const hasSelectedPlan = (context: DecisionContext): boolean => {
  return Boolean(context.selected_plan_id)
}

const hasScopeBaselinePointer = (context: DecisionContext): boolean => {
  return Boolean(context.current_scope_baseline_id)
}

const hasFrozenScopeBaseline = (context: DecisionContext): boolean => {
  return Boolean(hasScopeBaselinePointer(context) && context.scope_frozen)
}

export const canRunFeasibility = (context: DecisionContext): boolean => {
  return Boolean(context.confirmed_dag_path_id)
}

export const canOpenScope = (context: DecisionContext): boolean => {
  return hasSelectedPlan(context)
}

export const canOpenPrd = (context: DecisionContext): boolean => {
  return Boolean(hasSelectedPlan(context) && hasFrozenScopeBaseline(context))
}
