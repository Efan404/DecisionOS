import { ScopeFreezePage } from '../../../../components/scope/ScopeFreezePage'
import { IdeaScopedHydration } from '../../../../components/ideas/IdeaScopedHydration'
import { PageErrorBoundary } from '../../../../components/common/PageErrorBoundary'

type ScopeFreezeScopedPageProps = {
  params: Promise<{
    ideaId: string
  }>
}

export default async function ScopeFreezeScopedPage({ params }: ScopeFreezeScopedPageProps) {
  const { ideaId } = await params

  return (
    <IdeaScopedHydration ideaId={ideaId}>
      <PageErrorBoundary>
        <ScopeFreezePage />
      </PageErrorBoundary>
    </IdeaScopedHydration>
  )
}
