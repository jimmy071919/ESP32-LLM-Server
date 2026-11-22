import { describe, expect, it } from 'vitest'
import { buildWebSocketUrl, extractResources, isAllowedWebChatOrigin, messageParts, parseAllowedHosts, readTeaching, writeTeaching } from '../src/utils/assistantWorkbenchUtils.mjs'

describe('assistant workbench helpers', () => {
  it('adds and replaces teaching without changing the original prompt', () => {
    const original = 'Be concise.\nKeep the device voice natural.'
    const taught = writeTeaching(original, '列新聞時附上來源網址。')
    expect(taught).toContain(original)
    expect(readTeaching(taught)).toBe('列新聞時附上來源網址。')
    expect(readTeaching(writeTeaching(taught, '改用繁體中文。'))).toBe('改用繁體中文。')
    expect(writeTeaching(taught, '')).toBe(original)
  })

  it('reads text, tool and tool-result records from stored JSON', () => {
    expect(messageParts(JSON.stringify([
      { type: 'text', text: '完成了。' },
      { type: 'tool', text: 'search_news' },
      { type: 'tool_result', text: '找到 3 則。' }
    ]))).toEqual([
      { type: 'text', text: '完成了。' },
      { type: 'tool', text: 'search_news' },
      { type: 'tool_result', text: '找到 3 則。' }
    ])
  })

  it('keeps file and source links scoped to the message that contains them', () => {
    const first = extractResources([{ content: '[report](https://files.example.org/report.pdf) https://news.example.org/a' }])
    const second = extractResources([{ content: '沒有連結的回覆。' }])
    expect(first.files).toHaveLength(1)
    expect(first.links).toHaveLength(1)
    expect(second.files).toHaveLength(0)
    expect(second.links).toHaveLength(0)
  })

  it('deduplicates safe web links and separates downloadable URLs from local paths', () => {
    const { files, links } = extractResources([
      { content: '新聞來源：[官方公告](https://news.example.org/item/1)。 https://news.example.org/item/1' },
      { content: '檔案：https://files.example.org/report.xlsx?download=1，另存 /home/jimmy/report.pdf' },
      { content: '[不安全](javascript:alert(1))' }
    ])
    expect(links).toHaveLength(1)
    expect(links[0].url).toBe('https://news.example.org/item/1')
    expect(files.map((file) => file.label)).toEqual(['report.xlsx', 'report.pdf'])
    expect(files[0].url).toBe('https://files.example.org/report.xlsx?download=1')
    expect(files[1].localPath).toBe('/home/jimmy/report.pdf')
  })

  it('keeps web chat on the current HTTPS origin and carries OTA auth only to WSS', () => {
    const url = new URL(buildWebSocketUrl(
      { url: 'ws://public.example.org/xiaozhi/v1/', token: 'secret-token' },
      'AA:BB:CC:DD:EE:FF',
      'web-chat-1',
      'https://10.0.0.5:18002'
    ))
    expect(url.protocol).toBe('wss:')
    expect(url.host).toBe('10.0.0.5:18002')
    expect(url.pathname).toBe('/xiaozhi/v1/')
    expect(url.searchParams.get('authorization')).toBe('Bearer secret-token')
    expect(url.searchParams.get('device-id')).toBe('AA:BB:CC:DD:EE:FF')
    expect(url.searchParams.get('client-id')).toBe('web-chat-1')
  })

  it('accepts canonical HTTPS manager origins without pinning a host', () => {
    expect(isAllowedWebChatOrigin('https://manager.example.com')).toBe(true)
    expect(isAllowedWebChatOrigin('https://10.0.0.5:18002')).toBe(true)
    expect(isAllowedWebChatOrigin('https://example.org')).toBe(true)
    expect(isAllowedWebChatOrigin('http://manager.example.com')).toBe(false)
    expect(isAllowedWebChatOrigin('https://example.org/path')).toBe(false)
    expect(isAllowedWebChatOrigin('https://user:pass@example.org')).toBe(false)
    expect(isAllowedWebChatOrigin('not a url')).toBe(false)
  })

  it('enforces the deployment-configured host allowlist when present', () => {
    const hosts = parseAllowedHosts(' Manager.Example.com, 10.0.0.5 ')
    expect(hosts).toEqual(['manager.example.com', '10.0.0.5'])
    expect(isAllowedWebChatOrigin('https://manager.example.com', hosts)).toBe(true)
    expect(isAllowedWebChatOrigin('https://10.0.0.5:18002', hosts)).toBe(true)
    expect(isAllowedWebChatOrigin('https://evil.example.net', hosts)).toBe(false)
    expect(isAllowedWebChatOrigin('https://manager.example.com', '')).toBe(true)
    expect(parseAllowedHosts(undefined)).toEqual([])
  })
})
