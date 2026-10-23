export function shouldOpenTaskRow(event: MouseEvent) {
  const target = event.target
  return !(
    event.defaultPrevented ||
    event.button !== 0 ||
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    event.shiftKey ||
    (target instanceof Element &&
      target.closest(
        'button, a, input, select, textarea, label, [role="switch"], .task-status, .row-actions',
      )) ||
    window.getSelection()?.toString()
  )
}
