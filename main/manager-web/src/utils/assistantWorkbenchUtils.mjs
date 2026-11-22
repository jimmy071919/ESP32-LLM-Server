export const TEACHING_START = '<xiaozhi-workbench-teaching>'
export const TEACHING_END = '</xiaozhi-workbench-teaching>'

const FILE_EXTENSIONS = new Set([
  'csv', 'doc', 'docx', 'json', 'md', 'mp3', 'mp4', 'pdf', 'png', 'jpg', 'jpeg',
  'ppt', 'pptx', 'txt', 'wav', 'webp', 'xls', 'xlsx', 'zip'
])

/**
 * 解析部署設定的 Web Chat 允許主機（逗號或空白分隔，例如 "aiot.example.com, 10.0.0.5"）。
 * 來源：建置時的 VUE_APP_WEB_CHAT_ALLOWED_HOSTS；不在程式碼中寫死任何私有 IP 或網域。
 */
export function parseAllowedHosts(value = '') {
  return String(value || '')
    .split(/[\s,]+/)
    .map(host => host.trim().toLowerCase())
    .filter(Boolean)
}

/**
 * 只允許標準形式的 HTTPS origin；若有設定允許主機清單，主機名稱必須在清單中。
 * 未設定清單時接受任何 HTTPS origin（由反向代理決定可達性）。
 */
export function isAllowedWebChatOrigin(origin, allowedHosts = []) {
  try {
    const url = new URL(origin)
    if (url.protocol !== 'https:' || url.origin !== origin) return false
    const hosts = Array.isArray(allowedHosts) ? allowedHosts : parseAllowedHosts(allowedHosts)
    return hosts.length === 0 || hosts.includes(url.hostname.toLowerCase())
  } catch (_) {
    return false
  }
}

export function readTeaching(prompt = '') {
  const source = String(prompt || '')
  const start = source.indexOf(TEACHING_START)
  const end = source.indexOf(TEACHING_END, start + TEACHING_START.length)
  if (start < 0 || end < 0) return ''
  const bodyStart = source.indexOf('\n', start + TEACHING_START.length)
  return bodyStart < 0 || bodyStart > end ? '' : source.slice(bodyStart + 1, end).replace(/\n$/, '')
}

export function writeTeaching(prompt = '', teaching = '') {
  const source = String(prompt || '')
  const start = source.indexOf(TEACHING_START)
  const end = source.indexOf(TEACHING_END, start + TEACHING_START.length)
  const base = start < 0 || end < 0
    ? source.trimEnd()
    : [source.slice(0, start).trimEnd(), source.slice(end + TEACHING_END.length).trimStart()]
      .filter(Boolean).join('\n\n')
  const rules = String(teaching || '').trim()
  return rules ? `${base}${base ? '\n\n' : ''}${TEACHING_START}\n${rules}\n${TEACHING_END}` : base
}

export function messageParts(content) {
  if (Array.isArray(content)) return normalizeParts(content)
  if (typeof content !== 'string') return [{ type: 'text', text: String(content ?? '') }]

  try {
    const parsed = JSON.parse(content)
    if (Array.isArray(parsed)) return normalizeParts(parsed)
    if (parsed && typeof parsed === 'object' && 'content' in parsed) {
      return messageParts(typeof parsed.content === 'string' ? parsed.content : JSON.stringify(parsed.content))
    }
  } catch (_) {
    // Stored messages are commonly plain text rather than JSON.
  }
  return [{ type: 'text', text: content }]
}

function normalizeParts(parts) {
  return parts.map((part) => {
    if (typeof part === 'string') return { type: 'text', text: part }
    return {
      type: part?.type || 'text',
      text: String(part?.text ?? part?.content ?? '')
    }
  }).filter((part) => part.text)
}

export function extractResources(messages = []) {
  const resources = new Map()
  const localPaths = new Set()
  const localPathPattern = /(?:^|[\s("'`])((?:~|\.)?\/[^\s"'`<>]+?\.(?:csv|docx?|json|md|mp3|mp4|pdf|png|jpe?g|pptx?|txt|wav|webp|xlsx?|zip))(?![\w])/gi

  messages.forEach((message) => {
    messageParts(message?.content).forEach(({ text }) => {
      const markdownPattern = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/gi
      let match
      while ((match = markdownPattern.exec(text))) addResource(resources, match[2], match[1])

      const urlPattern = /https?:\/\/[^\s<>"'`，。！？；：]+/gi
      while ((match = urlPattern.exec(text))) addResource(resources, match[0], '')

      while ((match = localPathPattern.exec(text))) localPaths.add(match[1].replace(/[),.;，。！？]+$/, ''))
    })
  })

  const links = Array.from(resources.values())
  const files = links.filter((item) => item.isFile)
  localPaths.forEach((path) => {
    if (!files.some((item) => item.url === path)) files.push({
      url: '', label: path.split('/').pop(), isFile: true, localPath: path
    })
  })
  return { files, links: links.filter((item) => !item.isFile) }
}

export function buildWebSocketUrl(websocketInfo, deviceId, clientId, pageOrigin) {
  if (!websocketInfo?.url || !deviceId || !clientId) throw new Error('缺少小智連線資料')
  const page = new URL(pageOrigin)
  const url = new URL(websocketInfo.url, page)
  url.protocol = page.protocol === 'https:' ? 'wss:' : 'ws:'
  url.host = page.host
  url.pathname = '/xiaozhi/v1/'
  url.search = ''
  url.hash = ''
  if (websocketInfo.token) {
    const token = String(websocketInfo.token)
    url.searchParams.set('authorization', token.startsWith('Bearer ') ? token : `Bearer ${token}`)
  }
  url.searchParams.set('device-id', String(deviceId))
  url.searchParams.set('client-id', String(clientId))
  return url.toString()
}

function addResource(resources, rawUrl, label) {
  const url = String(rawUrl || '').replace(/[),.;，。！？]+$/, '')
  let parsed
  try {
    parsed = new URL(url)
  } catch (_) {
    return
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) return
  const cleanUrl = parsed.href
  if (!resources.has(cleanUrl)) {
    const extension = parsed.pathname.split('.').pop().toLowerCase()
    resources.set(cleanUrl, {
      url: cleanUrl,
      label: label || parsed.pathname.split('/').filter(Boolean).pop() || parsed.hostname,
      isFile: FILE_EXTENSIONS.has(extension)
    })
  }
}
