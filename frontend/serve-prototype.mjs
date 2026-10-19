import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { resolve, relative, extname, isAbsolute } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('./dist-prototype/', import.meta.url))
const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json; charset=utf-8',
  '.ico': 'image/x-icon',
}
try {
  await stat(resolve(root, 'prototype.html'))
} catch {
  console.error('缺少预构建界面，请先运行 pnpm --dir frontend build:prototype。')
  process.exit(1)
}
const server = createServer(async (request, response) => {
  response.setHeader('Cache-Control', 'no-store')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  if (!['GET', 'HEAD'].includes(request.method)) {
    response.writeHead(405, { Allow: 'GET, HEAD' }).end()
    return
  }
  let pathname
  try {
    pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname)
  } catch {
    response.writeHead(400).end()
    return
  }
  if (pathname === '/') {
    response.writeHead(302, { Location: '/prototype.html' }).end()
    return
  }
  const path = resolve(root, '.' + pathname)
  const inside = relative(root, path)
  if (inside.startsWith('..') || isAbsolute(inside)) {
    response.writeHead(403).end()
    return
  }
  try {
    const data = await readFile(path)
    response.writeHead(200, {
      'Content-Type': types[extname(path)] ?? 'application/octet-stream',
      'Content-Length': data.length,
    })
    response.end(request.method === 'HEAD' ? undefined : data)
  } catch {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('文件不存在')
  }
})
server.on('error', (error) => {
  console.error(
    error.code === 'EADDRINUSE' ? '4175 端口已被使用，请停止旧预览后重试。' : error.message,
  )
  process.exit(1)
})
server.listen(4175, '127.0.0.1', () => {
  console.log('SeekBell 完整界面预览：http://localhost:4175/prototype.html#/')
  console.log('仅模拟数据。按 Ctrl+C 停止。')
})
