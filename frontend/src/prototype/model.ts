export interface Group {
  all: string[]
  any: string[]
}
export interface Task {
  id: string
  name: string
  description: string
  enabled: boolean
  scope: 'title' | 'summary' | 'title_summary'
  groups: Group[]
  exclude: string[]
  categories: string[]
  authorsInclude: string[]
  authorsExclude: string[]
  caseSensitive: boolean
  wholeWord: boolean
  targets: string[]
  hits: number
  lastHit: string
  color: string
  icon: string
}
export interface Sample {
  title: string
  summary: string | null
  author: string | null
  category: string | null
}
export const targets = [
  { id: 'telegram', name: 'Telegram 私人通知', type: 'Telegram Bot', icon: 'send', color: 'blue' },
  { id: 'bark', name: '我的 iPhone', type: 'Bark', icon: 'phone', color: 'purple' },
  { id: 'smtp', name: '每日邮箱', type: 'SMTP', icon: 'mail', color: 'orange' },
  { id: 'webhook', name: '家庭服务', type: 'Webhook', icon: 'code', color: 'green' },
]
export function emptyTask(): Task {
  return {
    id: '',
    name: '',
    description: '',
    enabled: true,
    scope: 'title',
    groups: [{ all: [], any: [] }],
    exclude: [],
    categories: [],
    authorsInclude: [],
    authorsExclude: [],
    caseSensitive: false,
    wholeWord: false,
    targets: [],
    hits: 0,
    lastHit: '暂无命中',
    color: 'orange',
    icon: 'layers',
  }
}
export const initialTasks: Task[] = [
  {
    ...emptyTask(),
    id: 'deals',
    name: '好价服务器雷达',
    description: '留意 DMIT 与搬瓦工的新优惠',
    groups: [
      { all: ['DMIT'], any: ['优惠', '补货'] },
      { all: ['搬瓦工'], any: ['折扣', '促销'] },
    ],
    exclude: ['求购', '已出'],
    targets: ['telegram', 'bark'],
    hits: 18,
    lastHit: '2 分钟前',
    color: 'orange',
    icon: 'spark',
  },
  {
    ...emptyTask(),
    id: 'selfhost',
    name: '自托管灵感收集',
    description: '发现值得折腾的新项目',
    groups: [{ all: [], any: ['开源', '自托管', 'Docker'] }],
    targets: ['telegram'],
    hits: 12,
    lastHit: '18 分钟前',
    color: 'purple',
    icon: 'code',
  },
  {
    ...emptyTask(),
    id: 'network',
    name: '网络与线路观察',
    description: '关注线路测试和网络体验',
    groups: [{ all: [], any: ['CN2', '线路', '测评'] }],
    targets: ['bark'],
    hits: 8,
    lastHit: '36 分钟前',
    color: 'blue',
    icon: 'globe',
  },
  {
    ...emptyTask(),
    id: 'trade',
    name: '闲置设备好物',
    description: '筛选值得关注的设备转让',
    enabled: false,
    categories: ['交易'],
    groups: [{ all: [], any: ['迷你主机', 'NAS'] }],
    targets: ['smtp'],
    hits: 4,
    lastHit: '今天 09:18',
    color: 'green',
    icon: 'inbox',
  },
]
export const historySamples: Sample[] = [
  {
    title: 'DMIT 洛杉矶套餐补货，附本次优惠信息',
    summary: '新一批套餐已经开放。这里是合成演示内容。',
    author: 'cloud_note',
    category: '优惠',
  },
  {
    title: '搬瓦工新一轮促销，整理一下可选套餐',
    summary: '记录本次促销信息。',
    author: 'tiny_server',
    category: '优惠',
  },
  {
    title: '求购 DMIT 优惠套餐，有出的吗？',
    summary: '个人求购信息。',
    author: 'demo_buyer',
    category: '交易',
  },
  {
    title: '分享一个轻量的 Docker 自托管面板',
    summary: '开源项目的安装记录。',
    author: 'selfhost_lab',
    category: '技术',
  },
  { title: 'DMIT 套餐更新', summary: null, author: 'cloud_note', category: '日常' },
]
export type Truth = 'yes' | 'no' | 'unknown'
const and = (values: Truth[]): Truth =>
  values.includes('no') ? 'no' : values.includes('unknown') ? 'unknown' : 'yes'
const or = (values: Truth[]): Truth =>
  values.includes('yes') ? 'yes' : values.includes('unknown') ? 'unknown' : 'no'
const not = (value: Truth): Truth => (value === 'unknown' ? value : value === 'yes' ? 'no' : 'yes')
export function evaluate(task: Task, sample: Sample): { status: Truth; reasons: string[] } {
  const fields =
    task.scope === 'title'
      ? [sample.title]
      : task.scope === 'summary'
        ? [sample.summary]
        : [sample.title, sample.summary]
  const normalize = (value: string) => (task.caseSensitive ? value : value.toLowerCase())
  const contains = (text: string, term: string): boolean => {
    const haystack = normalize(text),
      needle = normalize(term)
    let offset = haystack.indexOf(needle)
    while (offset !== -1) {
      const word = (char: string) => /^[a-zA-Z0-9_]$/.test(char)
      if (
        !task.wholeWord ||
        ((!word(needle[0] ?? '') || !word(haystack[offset - 1] ?? '')) &&
          (!word(needle.at(-1) ?? '') || !word(haystack[offset + needle.length] ?? '')))
      )
        return true
      offset = haystack.indexOf(needle, offset + 1)
    }
    return false
  }
  const keyword = (term: string): Truth =>
    fields.some((field) => field !== null && contains(field, term))
      ? 'yes'
      : fields.includes(null)
        ? 'unknown'
        : 'no'
  const member = (value: string | null, choices: string[]): Truth =>
    value === null ? 'unknown' : choices.includes(value) ? 'yes' : 'no'
  const results: Truth[] = []
  const reasons: string[] = []
  const groups = task.groups.filter((group) => group.all.length || group.any.length)
  if (groups.length) {
    const values = groups.map((group, i) => {
      const value = and([
        ...group.all.map(keyword),
        ...(group.any.length ? [or(group.any.map(keyword))] : []),
      ])
      reasons.push(
        '条件组 ' + (i + 1) + '：' + { yes: '满足', no: '不满足', unknown: '信息不足' }[value],
      )
      return value
    })
    results.push(or(values))
  }
  for (const [label, value] of [
    ...(task.exclude.length ? [['排除词检查', not(or(task.exclude.map(keyword)))]] : []),
    ...(task.categories.length ? [['版块范围', member(sample.category, task.categories)]] : []),
    ...(task.authorsInclude.length
      ? [['指定作者', member(sample.author, task.authorsInclude)]]
      : []),
    ...(task.authorsExclude.length
      ? [['排除作者', not(member(sample.author, task.authorsExclude))]]
      : []),
  ] as [string, Truth][]) {
    results.push(value)
    reasons.push(label + '：' + { yes: '通过', no: '未通过', unknown: '信息不足' }[value])
  }
  const status = and(results)
  if (status === 'unknown') reasons.push('来源字段缺失，无法得出确定结论。')
  if (!results.length) reasons.push('未设置筛选条件，将匹配全部新帖。')
  return { status, reasons }
}
export const statusLabel: Record<Truth, string> = { yes: '命中', no: '不命中', unknown: '信息不足' }
