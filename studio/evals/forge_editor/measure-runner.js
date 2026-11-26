export const meta = { name: 'unbuilt', description: 'Run one review in each checkout.' }
const BUILT = null
if (!BUILT) return { done: false, reason: 'not_built' }

const results = await parallel(BUILT.trees.map(tree => () =>
  agent(tree.prompt, { label: tree.name, model: BUILT.model, schema: BUILT.schema })
))
return { done: true, count: results.length }
