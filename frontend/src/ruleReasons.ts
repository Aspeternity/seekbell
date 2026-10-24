import type { Reason } from './history'
export function reasonText(reason: Reason) {
  const known: Record<string, string> = {
    missing_summary: '摘要缺失',
    missing_author: '作者缺失',
    missing_category: '版块缺失',
    author_include:
      reason.truth === 'true'
        ? '作者在包含名单内'
        : reason.truth === 'false'
          ? '作者不在包含名单内'
          : '无法确定作者是否在包含名单内',
    author_exclude:
      reason.truth === 'true'
        ? '作者在排除名单内'
        : reason.truth === 'false'
          ? '作者不在排除名单内'
          : '无法确定作者是否在排除名单内',
    category:
      reason.truth === 'true'
        ? '版块符合范围'
        : reason.truth === 'false'
          ? '版块不在范围内'
          : '无法确定版块',
  }
  if (known[reason.code]) return known[reason.code]
  const prefix =
    reason.code === 'exclude'
      ? '排除词'
      : reason.code === 'all_of'
        ? '全部包含词'
        : reason.code === 'any_of'
          ? '至少包含词'
          : '判定'
  return (
    (reason.group ? '条件组 ' + reason.group + ' · ' : '') +
    prefix +
    (reason.term ? '「' + reason.term + '」' : '') +
    '：' +
    { true: '已出现', false: '未出现', unknown: '无法确定' }[reason.truth]
  )
}
