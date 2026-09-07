import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = path.join(root, 'apps', 'wechat-miniprogram')
const output = path.join(root, 'dist', 'wechat-production')
const api = process.env.WECHAT_API_BASE_URL || ''
const appId = process.env.WECHAT_APP_ID || ''

function fail(message) {
  console.error(`Production WeChat build failed: ${message}`)
  process.exit(1)
}

const parsed = (() => { try { return new URL(api) } catch { return null } })()
if (!parsed || parsed.protocol !== 'https:' || !parsed.hostname || parsed.hostname === 'localhost' || /^\d+(\.\d+){3}$/.test(parsed.hostname)) fail('WECHAT_API_BASE_URL must be an HTTPS domain, not localhost/IP')
if (!/^wx[a-zA-Z0-9_-]{8,}$/.test(appId)) fail('WECHAT_APP_ID must be a real-looking AppID')

fs.rmSync(output, { recursive: true, force: true })
fs.cpSync(source, output, { recursive: true, filter: (name) => !name.endsWith('config.js') && !name.endsWith('config.dev.js') && !name.endsWith('config.prod.js') && !name.endsWith('package.json') && !name.endsWith('project.private.config.json') })
fs.writeFileSync(path.join(output, 'config.js'), `module.exports = { apiBaseUrl: ${JSON.stringify(api.replace(/\/$/, ''))}, devMode: false }\n`)
const projectPath = path.join(output, 'project.config.json')
const project = JSON.parse(fs.readFileSync(projectPath, 'utf8'))
project.appid = appId
project.setting = { ...project.setting, urlCheck: true }
fs.writeFileSync(projectPath, `${JSON.stringify(project, null, 2)}\n`)
console.log(`Production WeChat package generated at ${output}`)
