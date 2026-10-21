<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const paths: Record<string, string> = {
  logout: 'M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M9 12h12m-5-5 5 5-5 5',
  copy: 'M8 8h13v13H8zM16 8V3H3v13h5',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
  rss: 'M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16M5 19h.01',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2',
  download: 'M12 3v12m-5-5 5 5 5-5M3 16v5h18v-5',
  upload: 'M12 16V4m-5 5 5-5 5 5M3 16v5h18v-5',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  'eye-off':
    'm3 3 18 18M9 5a10 10 0 0 1 3 0c6 0 10 7 10 7a18 18 0 0 1-4 4M6 6a20 20 0 0 0-4 6s4 7 10 7a10 10 0 0 0 4-1',
  bell: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
  grid: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  layers: 'm12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5',
  globe: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z',
  inbox: 'M4 3h16v18H4zM8 7h8M8 11h6M4 16h5l1 2h4l1-2h5',
  settings:
    'm9 3-1 3-3 1-2 5 2 5 3 1 1 3h6l1-3 3-1 2-5-2-5-3-1-1-3H9ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  arrow: 'M5 12h14m-5-5 5 5-5 5',
  back: 'M19 12H5m5-5-5 5 5 5',
  down: 'm6 9 6 6 6-6',
  plus: 'M12 5v14M5 12h14',
  search: 'M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Zm-2 5 6 6',
  check: 'm5 12 4 4L19 6',
  close: 'm6 6 12 12M6 18 18 6',
  activity: 'M2 12h4l3-8 6 16 3-8h4',
  clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 7v5l3 2',
  send: 'm22 2-7 20-4-9-9-4 20-7ZM11 13 22 2',
  mail: 'M3 5h18v14H3zM3 5l9 8 9-8',
  phone: 'M7 2h10v20H7zM10 18h4',
  code: 'm8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18',
  alert: 'm12 3 10 18H2L12 3ZM12 9v5m0 3v1',
  help: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9 9a3 3 0 1 1 4 3c-1 .5-1 1-1 2m0 3v.1',
  spark: 'm12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7Z',
  edit: 'm15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-4-4L5 15l-1 5Z',
  play: 'm8 4 12 8-12 8V4Z',
  refresh: 'M20 7a9 9 0 1 0 1 9M20 2v6h-6',
  menu: 'M4 6h16M4 12h16M4 18h16',
  filter: 'M3 5h18l-7 8v6l-4 2v-8L3 5Z',
  external: 'M14 3h7v7M21 3 10 14M10 3H3v18h18v-7',
  shield: 'm12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4Zm-5 10 3 3 7-7',
}
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.65"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.bell" />
  </svg>
</template>
