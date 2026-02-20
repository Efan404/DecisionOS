import type { DecisionContext, FeasibilityPlan } from './schemas'

const hasSelectedPlan = (context: DecisionContext): boolean => {
  if (!context.selected_plan_id || !context.feasibility) {
    return false
  }

  return context.feasibility.plans.some(
    (plan: FeasibilityPlan) => plan.id === context.selected_plan_id
  )
}

export const canRunFeasibility = (context: DecisionContext): boolean => {
  return Boolean(context.confirmed_dag_path_id)
}

export const canOpenScope = (context: DecisionContext): boolean => {
  return Boolean(context.selected_plan_id && context.feasibility && hasSelectedPlan(context))
}

export const canOpenPrd = (context: DecisionContext): boolean => {
  return Boolean(hasSelectedPlan(context) && context.scope)
}
