import { IdeaDAGCanvas } from '../../../../components/idea/dag/IdeaDAGCanvas'
import { IdeaScopedHydration } from '../../../../components/ideas/IdeaScopedHydration'
import { getIdea } from '../../../../lib/api'

type IdeaCanvasScopedPageProps = {
  params: Promise<{
    ideaId: string
  }>
}

export default async function IdeaCanvasScopedPage({ params }: IdeaCanvasScopedPageProps) {
  const { ideaId } = await params
  const idea = await getIdea(ideaId)

  return (
    <IdeaScopedHydration ideaId={ideaId}>
      <main className="h-[calc(100vh-4rem)]">
        <IdeaDAGCanvas ideaId={idea.id} ideaSeed={idea.idea_seed ?? idea.title} />
      </main>
    </IdeaScopedHydration>
  )
}
