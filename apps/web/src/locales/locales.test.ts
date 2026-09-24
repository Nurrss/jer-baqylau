import kk from './kk.json'
import ru from './ru.json'

type Tree = { [key: string]: string | Tree }

/** Flatten keys, collapsing plural suffixes (ru has _few/_many, kk only _one/_other). */
function keys(tree: Tree, prefix = ''): Set<string> {
  const out = new Set<string>()
  for (const [k, v] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'string') out.add(path.replace(/_(one|few|many|other)$/, ''))
    else keys(v, path).forEach((key) => out.add(key))
  }
  return out
}

test('ru and kk define the same keys', () => {
  const ruKeys = keys(ru as Tree)
  const kkKeys = keys(kk as Tree)
  expect([...ruKeys].filter((k) => !kkKeys.has(k))).toEqual([])
  expect([...kkKeys].filter((k) => !ruKeys.has(k))).toEqual([])
})

test('every string is non-empty', () => {
  const walk = (tree: Tree): string[] =>
    Object.values(tree).flatMap((v) => (typeof v === 'string' ? [v] : walk(v)))
  expect(walk(ru as Tree).every((s) => s.trim().length > 0)).toBe(true)
  expect(walk(kk as Tree).every((s) => s.trim().length > 0)).toBe(true)
})
