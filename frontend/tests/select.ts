import { expect, type Locator } from '@playwright/test'
export async function selectChoice(control: Locator, choice: string | { label: string }) {
  control = control.and(control.page().getByRole('combobox'))
  await control.click()
  const id = await control.getAttribute('aria-controls')
  const menu = control.page().locator('[id=' + JSON.stringify(id) + ']')
  const option =
    typeof choice === 'string'
      ? menu.locator('[role="option"][data-value=' + JSON.stringify(choice) + ']')
      : menu.getByRole('option', { name: choice.label, exact: true })
  await option.click()
  await expect(control).toHaveAttribute('aria-expanded', 'false')
}
export async function readChoices(control: Locator) {
  control = control.and(control.page().getByRole('combobox'))
  await control.click()
  const id = await control.getAttribute('aria-controls')
  const values = await control
    .page()
    .locator('[id=' + JSON.stringify(id) + '] [role="option"]')
    .allTextContents()
  await control.press('Escape')
  return values
}
