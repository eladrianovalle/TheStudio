export const meta = {
  name: 'measure-editor',
  description: 'Run the forge editor once in each prepared checkout.',
}
const BUILT = null
if (!BUILT) return { measured: false, reason: 'not_built' }

const results = await parallel(BUILT.trees.map(tree => () =>
  agent(tree.prompt, { label: tree.name, model: BUILT.model, schema: BUILT.schema })
))
return { measured: true, count: results.length }
