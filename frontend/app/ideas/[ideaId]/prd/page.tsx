import { PrdPage } from '../../../../components/prd/PrdPage'
import { IdeaScopedHydration } from '../../../../components/ideas/IdeaScopedHydration'
import { PageErrorBoundary } from '../../../../components/common/PageErrorBoundary'

type PrdScopedPageProps = {
  params: Promise<{
    ideaId: string
  }>
  searchParams: Promise<{
    baseline_id?: string
  }>
}

export default async function PrdScopedPage({ params, searchParams }: PrdScopedPageProps) {
  const { ideaId } = await params
  const { baseline_id: baselineId } = await searchParams

  return (
    <IdeaScopedHydration ideaId={ideaId}>
      <PageErrorBoundary>
        <PrdPage baselineId={baselineId ?? null} />
      </PageErrorBoundary>
    </IdeaScopedHydration>
  )
}
