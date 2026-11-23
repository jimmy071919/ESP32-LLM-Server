<template>
  <div class="assistant-workbench">
    <HeaderBar :devices="agents" />
    <main class="workbench-shell">
      <section class="workbench-grid">
        <aside class="session-panel">
          <label class="field-label" for="agent-picker">選擇助理</label>
          <el-select
            id="agent-picker"
            v-model="selectedAgentId"
            class="agent-picker"
            filterable
            :disabled="!agents.length"
            placeholder="選擇智能體"
            @change="changeAgent"
          >
            <el-option v-for="agent in agents" :key="agent.id" :label="agent.agentName" :value="agent.id" />
          </el-select>

          <div class="session-heading">
            <div>
              <h2>對話</h2>
              <span>{{ sessions.length }} 段已載入</span>
            </div>
            <div class="session-actions">
              <button class="new-chat-button" :class="{ active: chatMode === 'live' }" type="button" :disabled="!selectedAgentId" @click="startWebChat">
                <i class="el-icon-chat-line-round"></i> 文字對話
              </button>
              <button class="new-chat-button" type="button" :disabled="!selectedAgentId" @click="startDeviceMonitor">
                <i class="el-icon-monitor"></i> {{ deviceMonitorActive ? '追蹤 ESP32' : '即時設備' }}
              </button>
              <button class="icon-button" type="button" title="重新整理對話" :disabled="!selectedAgentId" @click="refreshData">
                <i class="el-icon-refresh" :class="{ spinning: refreshing }"></i>
              </button>
            </div>
          </div>
          <el-input
            v-model="sessionSearch"
            class="session-search"
            prefix-icon="el-icon-search"
            clearable
            placeholder="搜尋對話"
          />
          <div class="session-list">
            <button
              v-for="session in visibleSessions"
              :key="session.sessionId"
              type="button"
              class="session-card"
              :class="{ selected: currentSessionId === session.sessionId }"
              @click="openSession(session)"
            >
              <span class="session-mark"><i class="el-icon-chat-dot-round"></i></span>
              <span class="session-copy">
                <strong>{{ session.title || formatTime(session.createdAt) }}</strong>
                <small>{{ formatTime(session.createdAt) }}<template v-if="session.chatCount"> · {{ session.chatCount }} 則</template></small>
              </span>
              <i class="el-icon-arrow-right session-arrow"></i>
            </button>
            <div v-if="loadingSessions" class="quiet-state">載入對話中…</div>
            <div v-else-if="!visibleSessions.length && !sessions.length" class="quiet-state">
              <i class="el-icon-chat-line-round"></i>
              <span>還沒有已保存的對話</span>
            </div>
            <div v-else-if="!visibleSessions.length" class="quiet-state">找不到符合的對話</div>
            <button v-if="hasMoreSessions" class="load-older" type="button" :disabled="loadingSessions" @click="loadMoreSessions">
              {{ loadingSessions ? '載入中…' : '載入更早對話' }}
            </button>
          </div>
          <div v-if="selectedAgent && chatHistoryConf === 0" class="history-notice">
            <i class="el-icon-info"></i>
            <span>目前未保存對話。啟用後只保存文字，不錄音。</span>
            <button type="button" :disabled="savingHistory" @click="enableTextHistory">
              {{ savingHistory ? '處理中…' : '啟用文字紀錄' }}
            </button>
          </div>
        </aside>

        <section class="workspace-panel">
          <nav class="workspace-tabs" aria-label="助理工作台分頁">
            <button type="button" :class="{ active: activeTab === 'chat' }" @click="activeTab = 'chat'">
              對話內容
            </button>
            <button type="button" :class="{ active: activeTab === 'teach' }" @click="activeTab = 'teach'">
              教它做事
            </button>
            <button type="button" :class="{ active: activeTab === 'outputs' }" @click="activeTab = 'outputs'">
              成果
              <span v-if="resources.files.length + resources.links.length" class="tab-count">{{ resources.files.length + resources.links.length }}</span>
            </button>
            <span class="workspace-spacer"></span>
            <span v-if="activeTab === 'chat' && chatHistoryConf !== null" class="record-state" :class="{ off: chatHistoryConf === 0 }">
              <span class="status-dot"></span>{{ chatHistoryConf === 0 ? '未記錄' : '文字紀錄中' }}
            </span>
          </nav>

          <div v-if="!selectedAgentId && !loadingAgents" class="workspace-empty">
            <div class="empty-mark"><i class="el-icon-monitor"></i></div>
            <h2>{{ agents.length ? '選擇一個助理開始' : '尚未建立助理' }}</h2>
            <p>{{ agents.length ? '從左側選擇智能體，即可查看它的對話與成果。' : '先到智能管理新增智能體並連線 ESP32。' }}</p>
            <el-button v-if="!agents.length" type="primary" @click="$router.push('/home')">前往智能管理</el-button>
          </div>

          <template v-else-if="selectedAgentId">
            <section v-if="activeTab === 'chat'" class="tab-content chat-content">
              <div v-if="deviceMonitorActive" class="live-chat-toolbar">
                <div class="live-chat-state state-connected">
                  <span class="status-dot"></span>
                  {{ deviceMonitorMac ? `正在追蹤 ESP32 · ${deviceMonitorMac}` : '正在尋找已綁定的 ESP32' }}
                </div>
                <el-select
                  v-if="boundDevices.length > 1"
                  v-model="deviceMonitorMac"
                  size="small"
                  aria-label="選擇 ESP32 設備"
                  @change="changeMonitorDevice"
                >
                  <el-option
                    v-for="device in boundDevices"
                    :key="device.macAddress"
                    :label="`${device.deviceName || device.board || 'ESP32'} · ${device.macAddress}`"
                    :value="device.macAddress"
                  />
                </el-select>
                <div class="live-chat-actions">
                  <button type="button" :disabled="deviceMonitorPolling" @click="refreshDeviceConversation">
                    {{ deviceMonitorPolling ? '同步中…' : '立即更新' }}
                  </button>
                </div>
              </div>
              <div v-if="deviceMonitorError" class="live-chat-error" role="alert">{{ deviceMonitorError }}</div>
              <template v-if="chatMode === 'live'">
                <div class="live-chat-toolbar">
                  <div class="live-chat-state" :class="`state-${webChatStatus}`">
                    <span class="status-dot"></span>{{ webChatStatusLabel }}
                    <span v-if="webChatBusy" class="typing-indicator">助理正在回覆</span>
                  </div>
                  <div class="live-chat-actions">
                    <button v-if="webChatStatus !== 'connected'" type="button" :disabled="webChatConnecting" @click="connectWebChat">
                      {{ webChatConnecting ? '連線中…' : '重新連線' }}
                    </button>
                    <button v-else type="button" @click="disconnectWebChat">結束連線</button>
                  </div>
                </div>
                <div v-if="webChatError" class="live-chat-error" role="alert">{{ webChatError }}</div>
                <div v-if="webSearchEnabled === false" class="search-config-note" role="note">
                  <span>此 agent 尚未啟用一般網頁搜尋；已配置的新聞工具仍可使用。</span>
                  <button type="button" @click="$router.push({ path: '/role-config', query: { agentId: selectedAgentId } })">設定搜尋</button>
                </div>
                <div v-if="chatHistoryConf === 0" class="inline-notice">
                  <i class="el-icon-info"></i><span>這個 agent 尚未保存文字對話；目前訊息只在此頁顯示。</span>
                </div>
                <div v-if="!messages.length" class="message-empty live-empty">
                  <i class="el-icon-chat-line-round"></i>
                  <strong>想查什麼或聊什麼？</strong>
                  <span>直接輸入問題，助理的回答和可辨識來源會顯示在對話裡。</span>
                </div>
                <div v-else ref="messageList" class="message-list live-message-list">
                  <article
                    v-for="(message, index) in messagesWithResources"
                    :key="message.id || `${message.createdAt}-${index}`"
                    class="message-row"
                    :class="messageClass(message)"
                  >
                    <template v-if="message.chatType === 3">
                      <div class="message-avatar tool-avatar"><i class="el-icon-link"></i></div>
                      <div class="message-body source-summary">
                        <details>
                          <summary>{{ message.resources.links.length ? `查詢來源 · ${message.resources.links.length}` : '查詢紀錄' }}</summary>
                          <div v-if="message.resources.links.length" class="message-resources">
                            <a v-for="link in message.resources.links" :key="link.url" :href="link.url" target="_blank" rel="noopener noreferrer" class="inline-resource-card source-link">
                              <span class="inline-resource-icon source"><i class="el-icon-link"></i></span>
                              <span class="inline-resource-name">{{ link.label }}</span>
                              <i class="el-icon-top-right inline-resource-action"></i>
                            </a>
                          </div>
                          <p v-else class="source-empty">這次沒有回傳可開啟的來源連結。</p>
                        </details>
                      </div>
                    </template>
                    <template v-else>
                      <div class="message-avatar">{{ message.chatType === 1 ? '你' : selectedAgent.agentName }}</div>
                      <div class="message-body">
                        <div class="message-meta">
                          <strong>{{ message.chatType === 1 ? '你' : selectedAgent.agentName }}</strong>
                          <time>{{ formatTime(message.createdAt) }}</time>
                        </div>
                        <div class="message-bubble">
                          <div
                            v-for="(part, partIndex) in messageParts(message.content)"
                            :key="`${part.type}-${partIndex}`"
                            class="message-part"
                          >{{ part.text }}</div>
                          <span v-if="message.pending" class="typing-dots" aria-label="助理正在回覆"><i></i><i></i><i></i></span>
                        </div>
                        <div v-if="message.resources.files.length || message.resources.links.length" class="message-resources">
                          <a v-for="link in message.resources.links" :key="link.url" :href="link.url" target="_blank" rel="noopener noreferrer" class="inline-resource-card source-link">
                            <span class="inline-resource-icon source"><i class="el-icon-link"></i></span>
                            <span class="inline-resource-name">{{ link.label }}</span>
                            <i class="el-icon-top-right inline-resource-action"></i>
                          </a>
                        </div>
                      </div>
                    </template>
                  </article>
                </div>
                <form class="chat-composer" @submit.prevent="sendWebChatMessage">
                  <textarea
                    v-model="webChatDraft"
                    rows="1"
                    :disabled="webChatStatus !== 'connected' || webChatBusy"
                    placeholder="傳送訊息給助理…"
                    aria-label="輸入訊息"
                    @keydown="handleWebChatKeydown"
                  ></textarea>
                  <button type="submit" :disabled="!webChatDraft.trim() || webChatStatus !== 'connected' || webChatBusy" aria-label="送出訊息" title="送出訊息">
                    <i class="el-icon-s-promotion"></i>
                  </button>
                </form>
              </template>
              <template v-else>
              <div v-if="chatHistoryConf === 0" class="inline-notice">
                <i class="el-icon-info"></i>
                <span>尚未啟用文字紀錄。啟用後才會開始保存新的對話，既有未保存的內容無法補回。</span>
                <button type="button" :disabled="savingHistory" @click="enableTextHistory">啟用文字紀錄</button>
              </div>
              <div v-if="loadingMessages" class="message-empty">載入對話內容中…</div>
              <div v-else-if="!currentSessionId" class="message-empty">
                <i class="el-icon-chat-line-round"></i>
                <strong>{{ deviceMonitorActive ? '等待你和 ESP32 說話' : '選一段對話來查看' }}</strong>
                <span>{{ deviceMonitorActive ? '你對設備說話後，辨識文字、查詢內容、來源與助理回答會同步顯示在這裡。' : '對話由 ESP32 收音，助理的回覆與文字紀錄會顯示在這裡。' }}</span>
              </div>
              <div v-else-if="!messages.length" class="message-empty">
                <i class="el-icon-document"></i>
                <strong>這段對話目前沒有文字紀錄</strong>
                <span>如果剛啟用紀錄，請重新連線 ESP32 後再試一次。</span>
              </div>
              <div v-else ref="messageList" class="message-list">
                <article
                  v-for="(message, index) in messagesWithResources"
                  :key="message.id || `${message.createdAt}-${index}`"
                  class="message-row"
                  :class="messageClass(message)"
                >
                  <div class="message-avatar">{{ message.chatType === 1 ? '你' : message.chatType === 3 ? '執行' : '助理' }}</div>
                  <div class="message-body">
                    <div class="message-meta">
                      <strong>{{ message.chatType === 1 ? '你' : message.chatType === 3 ? '工具紀錄' : selectedAgent.agentName }}</strong>
                      <time>{{ formatTime(message.createdAt) }}</time>
                    </div>
                    <div class="message-bubble">
                      <div
                        v-for="(part, partIndex) in messageParts(message.content)"
                        :key="`${part.type}-${partIndex}`"
                        class="message-part"
                        :class="partClass(part)"
                      >{{ part.text }}</div>
                    </div>
                    <div v-if="message.resources.files.length || message.resources.links.length" class="message-resources">
                      <div v-if="message.resources.files.length" class="message-resource-group">
                        <span class="message-resource-label"><i class="el-icon-folder"></i> 檔案</span>
                        <div v-for="file in message.resources.files" :key="file.url || file.localPath" class="inline-resource">
                          <a v-if="file.url" :href="file.url" target="_blank" rel="noopener noreferrer" class="inline-resource-card">
                            <span class="inline-resource-icon file"><i class="el-icon-document"></i></span>
                            <span class="inline-resource-name">{{ file.label }}</span>
                            <span class="inline-resource-action">下載</span>
                          </a>
                          <div v-else class="inline-resource-card local-file">
                            <span class="inline-resource-icon file"><i class="el-icon-document"></i></span>
                            <span class="inline-resource-name" :title="file.localPath">{{ file.label }}<small>本機路徑，尚無下載網址</small></span>
                            <button type="button" class="inline-resource-action" @click="copyPath(file.localPath)">複製路徑</button>
                          </div>
                        </div>
                      </div>
                      <div v-if="message.resources.links.length" class="message-resource-group">
                        <span class="message-resource-label"><i class="el-icon-link"></i> 來源連結</span>
                        <a v-for="link in message.resources.links" :key="link.url" :href="link.url" target="_blank" rel="noopener noreferrer" class="inline-resource-card source-link">
                          <span class="inline-resource-icon source"><i class="el-icon-link"></i></span>
                          <span class="inline-resource-name">{{ link.label }}</span>
                          <i class="el-icon-top-right inline-resource-action"></i>
                        </a>
                      </div>
                    </div>
                  </div>
                </article>
              </div>
              <footer v-if="currentSessionId && messages.length" class="chat-footer">
                <span><i class="el-icon-lock"></i> 僅顯示此帳號有權限查看的對話</span>
                <span>{{ messages.length }} 則訊息</span>
              </footer>
              </template>
            </section>

            <section v-else-if="activeTab === 'teach'" class="tab-content teach-content">
              <div class="teach-intro">
                <span class="teach-icon"><i class="el-icon-edit-outline"></i></span>
                <div>
                  <h2>把做事方式教給助理</h2>
                  <p>這些規則會保存到「{{ selectedAgent.agentName }}」的提示詞，之後的對話會一併使用。原有角色設定會保留。</p>
                </div>
              </div>
              <label class="field-label" for="teaching-rules">你希望它記住什麼？</label>
              <el-input
                id="teaching-rules"
                v-model="teachingDraft"
                type="textarea"
                :rows="12"
                resize="vertical"
                placeholder="例如：&#10;當我說「找今天的 AI 新聞」時，先整理 5 則最新消息。&#10;每則都附上標題、日期和原始新聞連結。&#10;如果要產生檔案，請提供真實可下載的連結；沒有連結時要明確說明。"
                :disabled="loadingPrompt || savingTeaching"
              />
              <div class="teach-footer">
                <span>{{ loadingPrompt ? '正在讀取設定…' : '留白後儲存會移除這些教學，不影響其他角色設定。' }}</span>
                <el-button type="primary" :loading="savingTeaching" :disabled="loadingPrompt || !promptLoaded" @click="saveTeaching">
                  儲存教學
                </el-button>
              </div>
              <div v-if="teachingSaved" class="saved-note"><i class="el-icon-circle-check"></i> 已保存，後續對話會使用這些教學。</div>
            </section>

            <section v-else class="tab-content outputs-content">
              <div class="outputs-heading">
                <div>
                  <h2>這段對話的成果</h2>
                  <p>{{ currentSession ? (currentSession.title || formatTime(currentSession.createdAt)) : '先從左側選擇對話' }}</p>
                </div>
                <span class="result-count">{{ resources.files.length + resources.links.length }} 項</span>
              </div>
              <div v-if="!currentSessionId" class="resource-empty">
                <i class="el-icon-folder-opened"></i>
                <span>選擇一段對話後，這裡會整理其中的檔案與連結。</span>
              </div>
              <template v-else>
                <div class="resource-section">
                  <div class="section-title"><span class="file-icon"><i class="el-icon-document"></i></span><h3>檔案</h3><span>{{ resources.files.length }}</span></div>
                  <div v-if="resources.files.length" class="resource-list">
                    <div v-for="file in resources.files" :key="file.url || file.localPath" class="resource-card">
                      <span class="resource-type">{{ fileExtension(file.label) }}</span>
                      <div class="resource-copy">
                        <strong>{{ file.label }}</strong>
                        <small v-if="file.localPath">主機路徑，尚無可下載網址</small>
                        <small v-else>{{ file.url }}</small>
                      </div>
                      <a v-if="file.url" :href="file.url" target="_blank" rel="noopener noreferrer" class="resource-action" :aria-label="`開啟 ${file.label}`">
                        <i class="el-icon-download"></i>
                      </a>
                      <button v-else class="resource-action" type="button" title="複製檔案路徑" @click="copyPath(file.localPath)">
                        <i class="el-icon-copy-document"></i>
                      </button>
                    </div>
                  </div>
                  <div v-else class="resource-empty small-empty">這段對話沒有找到可辨識的檔案連結。</div>
                </div>
                <div class="resource-section">
                  <div class="section-title"><span class="link-icon"><i class="el-icon-link"></i></span><h3>新聞與網頁來源</h3><span>{{ resources.links.length }}</span></div>
                  <div v-if="resources.links.length" class="resource-list">
                    <a v-for="link in resources.links" :key="link.url" :href="link.url" target="_blank" rel="noopener noreferrer" class="resource-card link-card">
                      <span class="link-icon"><i class="el-icon-link"></i></span>
                      <span class="resource-copy"><strong>{{ link.label }}</strong><small>{{ link.url }}</small></span>
                      <i class="el-icon-top-right resource-action"></i>
                    </a>
                  </div>
                  <div v-else class="resource-empty small-empty">這段對話沒有找到可開啟的新聞或網頁連結。</div>
                </div>
                <p class="resource-footnote">只整理助理在這段對話中實際回傳的網址；本機檔案路徑不會被當成下載連結。</p>
              </template>
            </section>
          </template>
        </section>
      </section>
      <div v-if="loadingAgents" class="loading-cover"><i class="el-icon-loading"></i> 正在載入你的智能體…</div>
    </main>
  </div>
</template>

<script>
import Api from '@/apis/api'
import HeaderBar from '@/components/HeaderBar.vue'
import { buildWebSocketUrl, extractResources, isAllowedWebChatOrigin, messageParts, parseAllowedHosts, readTeaching, writeTeaching } from '@/utils/assistantWorkbenchUtils.mjs'

const PAGE_SIZE = 20

export default {
  name: 'AssistantWorkbench',
  components: { HeaderBar },
  data() {
    return {
      agents: [],
      selectedAgentId: '',
      sessions: [],
      currentSessionId: '',
      messages: [],
      activeTab: 'chat',
      chatMode: 'history',
      sessionSearch: '',
      loadingAgents: true,
      loadingSessions: false,
      loadingMessages: false,
      hasMoreSessions: false,
      sessionPage: 1,
      refreshing: false,
      refreshTimer: null,
      requestSequence: 0,
      deviceMonitorActive: false,
      deviceMonitorPolling: false,
      deviceMonitorError: '',
      deviceMonitorMac: '',
      boundDevices: [],
      chatHistoryConf: null,
      savingHistory: false,
      loadingPrompt: false,
      savingTeaching: false,
      promptLoaded: false,
      originalPrompt: '',
      teachingDraft: '',
      teachingSaved: false,
      webChatSocket: null,
      webChatStatus: 'offline',
      webChatConnecting: false,
      webChatBusy: false,
      webChatDraft: '',
      webChatError: '',
      webChatMac: '',
      webChatClientId: '',
      webChatSessionId: '',
      webSearchEnabled: null,
      liveAssistantMessageId: ''
    }
  },
  computed: {
    selectedAgent() {
      return this.agents.find((agent) => agent.id === this.selectedAgentId) || null
    },
    currentSession() {
      return this.sessions.find((session) => session.sessionId === this.currentSessionId) || null
    },
    messagesWithResources() {
      return this.messages.map((message) => ({ ...message, resources: extractResources([message]) }))
    },
    visibleSessions() {
      const query = this.sessionSearch.trim().toLowerCase()
      if (!query) return this.sessions
      return this.sessions.filter((session) => `${session.title || ''} ${this.formatTime(session.createdAt)}`.toLowerCase().includes(query))
    },
    resources() {
      return extractResources(this.messages)
    },
    webChatStatusLabel() {
      return ({ connected: '已連線', connecting: '連線中', error: '連線失敗' })[this.webChatStatus] || '未連線'
    }
  },
  created() {
    this.fetchAgents()
    this.refreshTimer = setInterval(this.refreshData, 10000)
  },
  beforeDestroy() {
    if (this.refreshTimer) clearInterval(this.refreshTimer)
    this.requestSequence += 1
    this.disconnectWebChat()
  },
  methods: {
    messageParts,
    fetchAgents() {
      this.loadingAgents = true
      Api.agent.getAgentList((res) => {
        const list = res?.data?.data
        this.agents = Array.isArray(list) ? list : []
        const requestedId = String(this.$route.query.agentId || '')
        const preferred = this.agents.find((agent) => agent.id === requestedId)
        this.loadingAgents = false
        if (this.agents.length) {
          this.selectedAgentId = (preferred || this.agents[0]).id
          this.changeAgent()
        }
      }, () => {
        this.loadingAgents = false
        this.$message.error('無法載入智能體，請重新登入或稍後再試。')
      })
    },
    changeAgent() {
      this.disconnectWebChat()
      this.chatMode = 'history'
      this.requestSequence += 1
      this.deviceMonitorActive = false
      this.deviceMonitorPolling = false
      this.deviceMonitorError = ''
      this.deviceMonitorMac = ''
      this.boundDevices = []
      this.setRefreshInterval(10000)
      this.sessions = []
      this.messages = []
      this.currentSessionId = ''
      this.loadingSessions = false
      this.loadingMessages = false
      this.refreshing = false
      this.savingHistory = false
      this.savingTeaching = false
      this.teachingSaved = false
      this.sessionPage = 1
      this.hasMoreSessions = false
      this.sessionSearch = ''
      this.chatHistoryConf = null
      this.webSearchEnabled = null
      this.promptLoaded = false
      this.teachingDraft = ''
      this.originalPrompt = ''
      this.loadAgentConfig()
      this.startDeviceMonitor()
    },
    loadAgentConfig() {
      if (!this.selectedAgentId) return
      const agentId = this.selectedAgentId
      this.loadingPrompt = true
      Api.agent.getDeviceConfig(agentId, (res) => {
        if (this.selectedAgentId !== agentId) return
        const config = res?.data?.data
        if (!config) {
          this.loadingPrompt = false
          return
        }
        this.chatHistoryConf = Number(config.chatHistoryConf ?? 0)
        this.webSearchEnabled = Array.isArray(config.functions)
          ? config.functions.some((item) => item.providerCode === 'web_search')
          : false
        this.originalPrompt = String(config.systemPrompt || '')
        this.teachingDraft = readTeaching(this.originalPrompt)
        this.promptLoaded = true
        this.loadingPrompt = false
      }, () => {
        if (this.selectedAgentId === agentId) {
          this.loadingPrompt = false
          this.$message.error('無法讀取助理設定，請稍後再試。')
        }
      })
    },
    loadSessions(reset = false) {
      if (!this.selectedAgentId || this.loadingSessions) return
      if (reset) {
        this.sessions = []
        this.sessionPage = 1
        this.hasMoreSessions = true
      }
      if (!this.hasMoreSessions && !reset) return
      const agentId = this.selectedAgentId
      const page = this.sessionPage
      this.loadingSessions = true
      const params = { page, limit: PAGE_SIZE }
      if (this.deviceMonitorActive && this.deviceMonitorMac) params.macAddress = this.deviceMonitorMac
      Api.agent.getAgentSessions(agentId, params, (res) => {
        if (this.selectedAgentId !== agentId) return
        const data = res?.data?.data
        const list = Array.isArray(data?.list) ? data.list : []
        const existing = new Set(this.sessions.map((session) => session.sessionId))
        this.sessions = [...this.sessions, ...list.filter((session) => !existing.has(session.sessionId))]
        this.hasMoreSessions = list.length === PAGE_SIZE
        this.sessionPage = page + 1
        this.loadingSessions = false
        if (!this.currentSessionId && this.sessions.length && !this.deviceMonitorActive) this.openSession(this.sessions[0])
      }, () => {
        if (this.selectedAgentId === agentId) {
          this.loadingSessions = false
          this.hasMoreSessions = false
          this.$message.error('無法載入對話清單，請稍後再試。')
        }
      })
    },
    loadMoreSessions() {
      this.loadSessions(false)
    },
    setRefreshInterval(milliseconds) {
      if (this.refreshTimer) clearInterval(this.refreshTimer)
      this.refreshTimer = setInterval(this.refreshData, milliseconds)
    },
    startDeviceMonitor() {
      if (!this.selectedAgentId) return
      const agentId = this.selectedAgentId
      const sequence = ++this.requestSequence
      this.disconnectWebChat()
      this.chatMode = 'history'
      this.deviceMonitorActive = true
      this.deviceMonitorPolling = false
      this.deviceMonitorError = ''
      this.deviceMonitorMac = ''
      this.boundDevices = []
      this.sessions = []
      this.currentSessionId = ''
      this.messages = []
      this.loadingMessages = false
      this.setRefreshInterval(2000)
      Api.device.getAgentBindDevices(agentId, (res) => {
        if (sequence !== this.requestSequence || this.selectedAgentId !== agentId || !this.deviceMonitorActive) return
        this.boundDevices = (res?.data?.data || []).filter((device) => device?.macAddress)
        if (!this.boundDevices.length) {
          this.deviceMonitorError = '這個智能體目前沒有綁定 ESP32 設備。'
          this.deviceMonitorActive = false
          this.setRefreshInterval(10000)
          this.loadSessions(true)
          return
        }
        this.deviceMonitorMac = this.boundDevices[0].macAddress
        this.refreshDeviceConversation()
      }, () => {
        if (sequence !== this.requestSequence || this.selectedAgentId !== agentId || !this.deviceMonitorActive) return
        this.deviceMonitorError = '無法取得已綁定的 ESP32 設備。'
        this.deviceMonitorActive = false
        this.setRefreshInterval(10000)
        this.loadSessions(true)
      })
    },
    changeMonitorDevice() {
      this.requestSequence += 1
      this.deviceMonitorPolling = false
      this.sessions = []
      this.currentSessionId = ''
      this.messages = []
      this.deviceMonitorError = ''
      this.refreshDeviceConversation()
    },
    refreshDeviceConversation() {
      if (!this.deviceMonitorActive || !this.selectedAgentId || !this.deviceMonitorMac || this.deviceMonitorPolling) return
      const agentId = this.selectedAgentId
      const macAddress = this.deviceMonitorMac
      const sequence = ++this.requestSequence
      this.deviceMonitorPolling = true
      Api.agent.getAgentSessions(agentId, { page: 1, limit: PAGE_SIZE, macAddress }, (res) => {
        if (sequence !== this.requestSequence || agentId !== this.selectedAgentId || macAddress !== this.deviceMonitorMac || !this.deviceMonitorActive) {
          if (sequence === this.requestSequence) this.deviceMonitorPolling = false
          return
        }
        const list = res?.data?.data?.list
        const latestSessions = Array.isArray(list) ? list : []
        const latestIds = new Set(latestSessions.map((session) => session.sessionId))
        this.sessions = [...latestSessions, ...this.sessions.filter((session) => !latestIds.has(session.sessionId))]
        this.hasMoreSessions = latestSessions.length === PAGE_SIZE
        this.sessionPage = 2
        const latest = this.sessions[0]
        if (!latest) {
          this.currentSessionId = ''
          this.messages = []
          this.loadingMessages = false
          this.deviceMonitorPolling = false
          return
        }
        const sessionId = latest.sessionId
        const newSession = sessionId !== this.currentSessionId
        if (newSession) {
          this.currentSessionId = sessionId
          this.messages = []
          this.loadingMessages = true
        }
        const wasAtBottom = newSession || (this.$refs.messageList && this.$refs.messageList.scrollHeight - this.$refs.messageList.scrollTop - this.$refs.messageList.clientHeight < 80)
        Api.agent.getAgentChatHistory(agentId, sessionId, (historyResponse) => {
          if (sequence !== this.requestSequence || agentId !== this.selectedAgentId || sessionId !== this.currentSessionId || macAddress !== this.deviceMonitorMac || !this.deviceMonitorActive) {
            if (sequence === this.requestSequence) this.deviceMonitorPolling = false
            return
          }
          const history = historyResponse?.data?.data
          if (Array.isArray(history)) {
            this.messages = history
            this.loadingMessages = false
            this.$nextTick(() => {
              if (wasAtBottom && this.$refs.messageList) this.$refs.messageList.scrollTop = this.$refs.messageList.scrollHeight
            })
          }
          this.deviceMonitorPolling = false
        }, macAddress)
      })
    },
    openSession(session) {
      if (!session?.sessionId || session.sessionId === this.currentSessionId && this.messages.length) return
      if (this.deviceMonitorActive) {
        this.deviceMonitorActive = false
        this.deviceMonitorPolling = false
        this.requestSequence += 1
        this.setRefreshInterval(10000)
      }
      this.disconnectWebChat()
      this.chatMode = 'history'
      const agentId = this.selectedAgentId
      const sequence = ++this.requestSequence
      this.currentSessionId = session.sessionId
      this.messages = []
      this.loadingMessages = true
      this.activeTab = 'chat'
      Api.agent.getAgentChatHistory(agentId, session.sessionId, (res) => {
        if (sequence !== this.requestSequence || this.selectedAgentId !== agentId) return
        const history = res?.data?.data
        this.messages = Array.isArray(history) ? history : []
        this.loadingMessages = false
        this.$nextTick(() => {
          const list = this.$refs.messageList
          if (list) list.scrollTop = list.scrollHeight
        })
      }, session.macAddress || '')
    },
    refreshData() {
      if (this.deviceMonitorActive) {
        this.refreshDeviceConversation()
        return
      }
      if (!this.selectedAgentId || this.refreshing) return
      const agentId = this.selectedAgentId
      const sessionId = this.currentSessionId
      this.refreshing = true
      Api.agent.getAgentSessions(agentId, { page: 1, limit: PAGE_SIZE }, (res) => {
        if (this.selectedAgentId !== agentId) return
        const latest = res?.data?.data?.list
        if (Array.isArray(latest)) {
          const latestIds = new Set(latest.map((session) => session.sessionId))
          this.sessions = [...latest, ...this.sessions.filter((session) => !latestIds.has(session.sessionId))]
          if (!sessionId && latest.length && this.chatMode !== 'live') this.openSession(latest[0])
        }
        this.refreshing = false
      }, () => { this.refreshing = false })
      if (sessionId) {
        Api.agent.getAgentChatHistory(agentId, sessionId, (res) => {
          if (this.selectedAgentId !== agentId || this.currentSessionId !== sessionId) return
          const history = res?.data?.data
          if (Array.isArray(history)) {
            const wasAtBottom = this.$refs.messageList && this.$refs.messageList.scrollHeight - this.$refs.messageList.scrollTop - this.$refs.messageList.clientHeight < 80
            this.messages = history
            this.$nextTick(() => {
              if (wasAtBottom && this.$refs.messageList) this.$refs.messageList.scrollTop = this.$refs.messageList.scrollHeight
            })
          }
        }, this.currentSession?.macAddress || '')
      }
    },
    startWebChat() {
      if (!this.selectedAgentId) return
      // 停止即時設備監看，避免輪詢覆蓋文字對話內容
      if (this.deviceMonitorActive) {
        this.deviceMonitorActive = false
        this.deviceMonitorPolling = false
        this.deviceMonitorError = ''
        this.requestSequence += 1
        this.setRefreshInterval(10000)
      }
      this.disconnectWebChat()
      this.chatMode = 'live'
      this.activeTab = 'chat'
      this.currentSessionId = ''
      this.messages = []
      this.webChatDraft = ''
      this.webChatError = ''
      this.connectWebChat()
    },
    async connectWebChat() {
      if (!this.selectedAgentId || this.webChatConnecting) return
      if (this.webChatSocket && this.webChatSocket.readyState < WebSocket.CLOSING) return

      const agentId = this.selectedAgentId
      if (process.env.NODE_ENV === 'production' &&
        !isAllowedWebChatOrigin(window.location.origin, parseAllowedHosts(process.env.VUE_APP_WEB_CHAT_ALLOWED_HOSTS))) {
        this.webChatStatus = 'error'
        this.webChatError = '請使用支援 WebSocket 代理的 HTTPS 管理網址進行文字聊天。'
        return
      }
      this.webChatConnecting = true
      this.webChatStatus = 'connecting'
      this.webChatError = ''
      this.webChatSessionId = ''
      try {
        const response = await new Promise((resolve, reject) => {
          Api.device.getAgentBindDevices(agentId, resolve, reject)
        })
        const devices = response?.data?.data
        const device = Array.isArray(devices) ? devices[0] : null
        const deviceId = String(device?.macAddress || '').trim()
        if (!deviceId) throw new Error('這個助理尚未綁定設備。')
        if (!device?.appVersion) throw new Error('設備版本資料不完整，請先讓設備重新連線。')

        const clientId = `web-chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
        const apiBase = String(Api.getServiceUrl() || '').replace(/\/$/, '')
        const otaResponse = await fetch(`${apiBase}/ota/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Device-Id': deviceId,
            'Client-Id': clientId
          },
          body: JSON.stringify({
            version: 0,
            uuid: '',
            application: {
              name: 'web-chat',
              version: device.appVersion,
              compile_time: 'web-chat',
              idf_version: 'web',
              elf_sha256: 'web-chat'
            },
            ota: { label: 'web-chat' },
            board: {
              type: device.board || device.deviceType || 'web-chat',
              ssid: 'web-chat',
              rssi: 0,
              channel: 0,
              ip: '127.0.0.1',
              mac: deviceId
            },
            flash_size: 0,
            minimum_free_heap_size: 0,
            mac_address: deviceId,
            chip_model_name: '',
            chip_info: { model: 0, cores: 0, revision: 0, features: 0 },
            partition_table: [{ label: '', type: 0, subtype: 0, address: 0, size: 0 }]
          })
        })
        if (!otaResponse.ok) throw new Error(`設備授權失敗（HTTP ${otaResponse.status}）。`)
        const ota = await otaResponse.json()
        if (!ota?.websocket?.url || !ota?.websocket?.token) {
          throw new Error('設備未回傳有效授權，請確認已登入且設備仍綁定。')
        }

        const socket = new WebSocket(buildWebSocketUrl(ota.websocket, deviceId, clientId, window.location.origin))
        this.webChatSocket = socket
        this.webChatMac = deviceId
        this.webChatClientId = clientId
        socket.binaryType = 'arraybuffer'
        socket.onopen = () => {
          socket.send(JSON.stringify({
            type: 'hello',
            device_id: deviceId,
            device_name: '助理工作台',
            device_mac: deviceId,
            features: { mcp: true, emoji: false }
          }))
        }
        socket.onmessage = (event) => this.handleWebChatMessage(event.data)
        socket.onerror = () => {
          this.webChatStatus = 'error'
          this.webChatError = '無法連線到助理，請確認目前的 HTTPS 管理網址支援 WebSocket 代理後重試。'
        }
        socket.onclose = () => {
          if (this.webChatSocket === socket) this.webChatSocket = null
          this.webChatStatus = 'offline'
          this.webChatBusy = false
          this.liveAssistantMessageId = ''
        }
      } catch (error) {
        this.webChatStatus = 'error'
        this.webChatError = error?.message || '無法啟動文字對話。'
      } finally {
        this.webChatConnecting = false
      }
    },
    disconnectWebChat() {
      const socket = this.webChatSocket
      this.webChatSocket = null
      if (socket && socket.readyState < WebSocket.CLOSING) socket.close()
      this.webChatStatus = 'offline'
      this.webChatConnecting = false
      this.webChatBusy = false
      this.webChatSessionId = ''
      this.webChatMac = ''
      this.webChatClientId = ''
      this.liveAssistantMessageId = ''
    },
    handleWebChatMessage(raw) {
      if (typeof raw !== 'string') return
      let message
      try {
        message = JSON.parse(raw)
      } catch (_) {
        this.webChatError = '助理回傳了無法讀取的訊息。'
        return
      }
      if (message.type === 'hello' && message.session_id) {
        this.webChatSessionId = message.session_id
        this.webChatStatus = 'connecting'
        setTimeout(() => {
          if (this.webChatSocket?.readyState === WebSocket.OPEN && this.webChatSessionId === message.session_id) {
            this.webChatStatus = 'connected'
          }
        }, 1200)
        return
      }
      if (message.type !== 'tts') return
      if (message.state === 'sentence_start' && message.text) this.appendWebChatText(message.text)
      if (message.state === 'stop') {
        this.webChatBusy = false
        const pending = this.messages.find((item) => item.id === this.liveAssistantMessageId)
        if (pending) pending.pending = false
        this.liveAssistantMessageId = ''
        this.refreshLiveHistory()
      }
    },
    appendWebChatText(text) {
      let message = this.messages.find((item) => item.id === this.liveAssistantMessageId)
      if (!message) {
        message = { id: `live-assistant-${Date.now()}`, chatType: 2, content: '', createdAt: Date.now(), pending: true }
        this.messages.push(message)
        this.liveAssistantMessageId = message.id
      }
      message.content += String(text)
      this.$nextTick(() => {
        const list = this.$refs.messageList
        if (list) list.scrollTop = list.scrollHeight
      })
    },
    sendWebChatMessage() {
      const text = this.webChatDraft.trim()
      if (!text || this.webChatBusy || !this.webChatSocket || this.webChatSocket.readyState !== WebSocket.OPEN) return
      this.messages.push({ id: `live-user-${Date.now()}`, chatType: 1, content: text, createdAt: Date.now() })
      const assistant = { id: `live-assistant-${Date.now()}-pending`, chatType: 2, content: '', createdAt: Date.now(), pending: true }
      this.messages.push(assistant)
      this.liveAssistantMessageId = assistant.id
      this.webChatBusy = true
      this.webChatDraft = ''
      try {
        this.webChatSocket.send(JSON.stringify({ type: 'listen', state: 'detect', text }))
      } catch (_) {
        this.webChatBusy = false
        assistant.pending = false
        this.webChatError = '訊息送出失敗，請重新連線。'
      }
      this.$nextTick(() => {
        const list = this.$refs.messageList
        if (list) list.scrollTop = list.scrollHeight
      })
    },
    handleWebChatKeydown(event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault()
        this.sendWebChatMessage()
      }
    },
    refreshLiveHistory(retry = 0) {
      if (!this.webChatSessionId || !this.webChatMac || this.chatHistoryConf === 0) return
      const agentId = this.selectedAgentId
      const sessionId = this.webChatSessionId
      const expectedUsers = this.messages.filter((item) => Number(item.chatType) === 1).length
      const expectedAssistants = this.messages.filter((item) => Number(item.chatType) === 2 && !item.pending).length
      Api.agent.getAgentChatHistory(agentId, sessionId, (res) => {
        if (agentId !== this.selectedAgentId || sessionId !== this.webChatSessionId) return
        const history = res?.data?.data
        if (!Array.isArray(history)) return
        const users = history.filter((item) => Number(item.chatType) === 1).length
        const assistants = history.filter((item) => Number(item.chatType) === 2).length
        if (users >= expectedUsers && assistants >= expectedAssistants && history.length) {
          this.messages = history
          this.$nextTick(() => {
            const list = this.$refs.messageList
            if (list) list.scrollTop = list.scrollHeight
          })
          this.loadSessions(true)
        } else if (retry < 4) {
          setTimeout(() => this.refreshLiveHistory(retry + 1), 500)
        }
      }, this.webChatMac)
    },
    enableTextHistory() {
      if (!this.selectedAgentId || this.savingHistory) return
      this.$confirm(
        '只會保存之後的文字對話，不會錄製或保存語音；之前未記錄的對話無法補回。',
        '啟用文字對話紀錄',
        { confirmButtonText: '啟用', cancelButtonText: '取消', type: 'info' }
      ).then(() => {
        const agentId = this.selectedAgentId
        this.savingHistory = true
        Api.agent.updateAgentConfig(agentId, { chatHistoryConf: 1 }, (res) => {
          if (this.selectedAgentId !== agentId) return
          this.savingHistory = false
          if (res?.data?.code === 0) {
            this.chatHistoryConf = 1
            this.$message.success('已啟用文字紀錄；請重新連線 ESP32 後開始保存新對話。')
          } else {
            this.$message.error(res?.data?.msg || '啟用失敗，請稍後再試。')
          }
        })
      }).catch(() => {})
    },
    saveTeaching() {
      if (!this.selectedAgentId || !this.promptLoaded || this.savingTeaching) return
      const agentId = this.selectedAgentId
      const nextPrompt = writeTeaching(this.originalPrompt, this.teachingDraft)
      this.savingTeaching = true
      this.teachingSaved = false
      Api.agent.updateAgentConfig(agentId, { systemPrompt: nextPrompt }, (res) => {
        if (this.selectedAgentId !== agentId) return
        this.savingTeaching = false
        if (res?.data?.code === 0) {
          this.originalPrompt = nextPrompt
          this.teachingDraft = readTeaching(nextPrompt)
          this.teachingSaved = true
          this.$message.success('教學已保存。')
        } else {
          this.$message.error(res?.data?.msg || '保存失敗，原有角色設定未變更。')
        }
      })
    },
    messageClass(message) {
      return message.chatType === 1 ? 'from-user' : message.chatType === 3 ? 'from-tool' : 'from-assistant'
    },
    partClass(part) {
      return part.type === 'tool' ? 'tool-call' : part.type === 'tool_result' ? 'tool-result' : ''
    },
    formatTime(timestamp) {
      if (!timestamp) return '時間未提供'
      const date = new Date(timestamp)
      if (Number.isNaN(date.getTime())) return String(timestamp)
      return new Intl.DateTimeFormat('zh-TW', {
        year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
      }).format(date)
    },
    fileExtension(name) {
      const match = String(name || '').match(/\.([^.]+)$/)
      return match ? match[1].slice(0, 5).toUpperCase() : 'FILE'
    },
    copyPath(path) {
      if (!path) return
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(path).then(() => this.$message.success('已複製檔案路徑。'))
          .catch(() => this.$message.warning(path))
      } else {
        this.$message.info(path)
      }
    }
  }
}
</script>

<style scoped>
.assistant-workbench {
  min-height: 100vh;
  background: #f5f7fb;
  color: #172033;
  display: flex;
  flex-direction: column;
}
.workbench-shell {
  width: min(1440px, calc(100% - 48px));
  margin: 0 auto;
  padding: 32px 0 40px;
  flex: 1;
}
.status-dot {
  width: 7px;
  height: 7px;
  background: #2f9b72;
  border-radius: 50%;
  display: inline-block;
}
.workbench-grid {
  min-height: min(740px, calc(100vh - 210px));
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  background: #fff;
  border: 1px solid #e5e9f0;
  border-radius: 14px;
  box-shadow: 0 12px 36px rgba(28, 45, 77, .055);
  overflow: hidden;
}
.session-panel {
  padding: 20px 16px 15px;
  border-right: 1px solid #e9edf3;
  display: flex;
  flex-direction: column;
  min-height: 580px;
  min-width: 0;
}
.field-label {
  display: block;
  color: #4f5d73;
  font-size: 12px;
  font-weight: 650;
  margin-bottom: 8px;
}
.agent-picker { width: 100%; }
.session-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 25px 2px 12px;
}
.session-heading h2 {
  margin: 0 0 3px;
  color: #1e2a3e;
  font-size: 14px;
  font-weight: 700;
}
.session-heading span { color: #8c96a8; font-size: 11px; }
.session-actions { display: flex; align-items: center; gap: 6px; }
.new-chat-button {
  min-height: 32px;
  padding: 0 9px;
  border: 1px solid #dce5f3;
  border-radius: 8px;
  background: #fff;
  color: #3167bd;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}
.new-chat-button:hover { border-color: #aac2e8; background: #f7faff; }
.new-chat-button.active { border-color: #5778ff; background: #eef3ff; }
.new-chat-button:disabled { cursor: not-allowed; opacity: .5; }
.new-chat-button i { margin-right: 3px; }
.icon-button {
  width: 30px;
  height: 30px;
  border: 1px solid #e7ebf1;
  border-radius: 8px;
  color: #5e6b81;
  background: #fff;
  cursor: pointer;
}
.icon-button:hover { color: #2767d8; border-color: #b9cef3; }
.icon-button:disabled { cursor: not-allowed; opacity: .5; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.session-search { margin-bottom: 10px; }
.session-list { overflow: auto; min-height: 100px; flex: 1; }
.session-card {
  width: 100%;
  border: 0;
  border-radius: 9px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
  padding: 10px 8px;
  margin: 2px 0;
  cursor: pointer;
  color: #27344a;
  transition: background .16s ease;
}
.session-card:hover { background: #f6f8fc; }
.session-card.selected { background: #eef4ff; }
.session-mark {
  flex: 0 0 32px;
  height: 32px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: #4a73bc;
  background: #f0f4fb;
  font-size: 15px;
}
.session-card.selected .session-mark { color: #2865ca; background: #dfeaff; }
.session-copy { min-width: 0; display: flex; flex: 1; flex-direction: column; gap: 4px; }
.session-copy strong {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: #354157;
  font-size: 12px;
  font-weight: 650;
}
.session-copy small { color: #929bad; font-size: 10px; }
.session-arrow { color: #9aa4b4; font-size: 11px; }
.quiet-state {
  min-height: 66px;
  color: #8a95a7;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 12px;
  text-align: center;
}
.quiet-state i { font-size: 17px; }
.load-older {
  display: block;
  width: 100%;
  border: 0;
  padding: 10px;
  background: transparent;
  color: #4b74bb;
  cursor: pointer;
  font-size: 11px;
}
.load-older:disabled { opacity: .55; cursor: wait; }
.history-notice {
  border-top: 1px solid #edf0f5;
  padding: 12px 2px 0;
  margin-top: 12px;
  display: flex;
  align-items: flex-start;
  gap: 7px;
  color: #7a8597;
  font-size: 10px;
  line-height: 1.5;
}
.history-notice i { margin-top: 1px; color: #6083c1; }
.history-notice span { flex: 1; }
.history-notice button, .inline-notice button {
  border: 0;
  padding: 0;
  background: transparent;
  color: #2865ca;
  font-size: 10px;
  white-space: nowrap;
  cursor: pointer;
}
.history-notice button:disabled { opacity: .5; cursor: wait; }
.workspace-panel { min-width: 0; display: flex; flex-direction: column; }
.workspace-tabs {
  min-height: 58px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  gap: 24px;
  border-bottom: 1px solid #e9edf3;
}
.workspace-tabs button {
  position: relative;
  height: 58px;
  padding: 0 2px;
  border: 0;
  background: transparent;
  color: #778298;
  font-size: 12px;
  cursor: pointer;
}
.workspace-tabs button.active { color: #245fc4; font-weight: 700; }
.workspace-tabs button.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 2px;
  background: #3374db;
  border-radius: 2px 2px 0 0;
}
.tab-count {
  display: inline-grid;
  place-items: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin-left: 4px;
  border-radius: 10px;
  background: #eef3fc;
  color: #5473aa;
  font-size: 10px;
}
.workspace-spacer { flex: 1; }
.record-state { display: inline-flex; align-items: center; gap: 6px; color: #63806f; font-size: 10px; }
.record-state .status-dot { width: 6px; height: 6px; }
.record-state.off { color: #9a7c4d; }
.record-state.off .status-dot { background: #d3a34f; }
.tab-content { min-height: 500px; flex: 1; }
.chat-content { display: flex; flex-direction: column; min-height: 0; }
.inline-notice {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 20px;
  background: #fffaf0;
  border-bottom: 1px solid #f3e9d0;
  color: #7b6c4f;
  font-size: 11px;
}
.inline-notice i { color: #c09339; }
.inline-notice span { flex: 1; }
.inline-notice button { font-size: 11px; }
.message-list {
  flex: 1;
  overflow: auto;
  padding: 22px 28px;
  display: flex;
  flex-direction: column;
  gap: 22px;
  min-height: 0;
}
.message-row { display: flex; gap: 10px; max-width: 900px; width: 100%; }
.message-row.from-user { align-self: flex-end; flex-direction: row-reverse; }
.message-avatar {
  flex: 0 0 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #e9effa;
  color: #4569a8;
  font-size: 10px;
  font-weight: 700;
}
.from-user .message-avatar { background: #e6f3ed; color: #347553; }
.from-tool .message-avatar { background: #fff3e7; color: #a2692f; font-size: 8px; }
.message-body { min-width: 0; max-width: min(84%, 760px); }
.message-meta { display: flex; align-items: center; gap: 9px; margin: 2px 0 6px; }
.message-meta strong { color: #526078; font-size: 10px; font-weight: 650; }
.message-meta time { color: #a3acba; font-size: 10px; }
.from-user .message-meta { justify-content: flex-end; }
.message-bubble {
  border: 1px solid #e9edf3;
  border-radius: 3px 12px 12px 12px;
  padding: 11px 13px;
  background: #f8f9fc;
  color: #354157;
  font-size: 12px;
  line-height: 1.75;
  overflow-wrap: anywhere;
}
.from-user .message-bubble { border-color: #dcebe1; background: #f1f8f3; border-radius: 12px 3px 12px 12px; }
.from-tool .message-bubble { border-style: dashed; background: #fffaf4; color: #69563f; }
.message-part { white-space: pre-wrap; }
.message-part + .message-part { margin-top: 8px; }
.message-part.tool-call, .message-part.tool-result { color: #6d788c; font-size: 11px; }
.message-part.tool-call::before { content: '工具 · '; color: #9c7546; font-weight: 700; }
.message-part.tool-result::before { content: '結果 · '; color: #5a7d68; font-weight: 700; }
.message-resources { display: grid; gap: 8px; margin-top: 8px; }
.message-resource-group { display: grid; gap: 5px; }
.message-resource-label { display: flex; align-items: center; gap: 5px; color: #8490a2; font-size: 9px; }
.inline-resource { min-width: 0; }
.inline-resource-card {
  min-height: 38px;
  max-width: 100%;
  padding: 5px 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  background: #fff;
  color: #40516b;
  text-decoration: none;
}
.inline-resource-card:hover { border-color: #c9d8ef; background: #fbfcff; }
.inline-resource-icon { flex: 0 0 25px; width: 25px; height: 25px; display: grid; place-items: center; border-radius: 6px; background: #eff4fc; color: #4f75b5; }
.inline-resource-icon.source { background: #edf7f1; color: #438168; }
.inline-resource-name { flex: 1; min-width: 0; overflow: hidden; color: #394960; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.inline-resource-name small { display: block; overflow: hidden; color: #9aa4b3; font-size: 8px; text-overflow: ellipsis; }
.inline-resource-action { flex: 0 0 auto; border: 0; padding: 4px 6px; border-radius: 5px; background: #f2f5fa; color: #58749e; font-size: 9px; white-space: nowrap; }
button.inline-resource-action { cursor: pointer; }
.local-file .inline-resource-name { white-space: normal; }
.message-empty, .workspace-empty {
  flex: 1;
  min-height: 390px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 9px;
  text-align: center;
  color: #8994a6;
  padding: 24px;
}
.message-empty i { color: #aebbd0; font-size: 24px; margin-bottom: 5px; }
.message-empty strong, .workspace-empty h2 { margin: 0; color: #39465d; font-size: 14px; }
.message-empty span, .workspace-empty p { max-width: 420px; margin: 0; color: #8994a6; font-size: 11px; line-height: 1.7; }
.chat-footer {
  border-top: 1px solid #edf0f5;
  padding: 9px 20px;
  display: flex;
  justify-content: space-between;
  color: #98a2b1;
  font-size: 10px;
}
.chat-footer i { margin-right: 4px; }
.live-chat-toolbar {
  min-height: 48px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #edf0f5;
  color: #6e7b91;
  font-size: 12px;
}
.live-chat-state { display: flex; align-items: center; gap: 7px; }
.live-chat-state .status-dot { width: 7px; height: 7px; background: #a9b2bf; }
.live-chat-state.state-connected .status-dot { background: #2f9b72; }
.live-chat-state.state-connecting .status-dot { background: #d19b45; }
.live-chat-state.state-error .status-dot { background: #d85f5f; }
.typing-indicator { margin-left: 8px; color: #8a95a7; }
.live-chat-actions button {
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid #e3e9f1;
  border-radius: 8px;
  background: #fff;
  color: #53647d;
  font-size: 11px;
  cursor: pointer;
}
.live-chat-actions button:disabled { cursor: wait; opacity: .55; }
.live-chat-error {
  padding: 10px 20px;
  border-bottom: 1px solid #f1dada;
  background: #fff8f8;
  color: #a84949;
  font-size: 12px;
}
.search-config-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 20px;
  border-bottom: 1px solid #eee7d5;
  background: #fffdf7;
  color: #786e57;
  font-size: 11px;
}
.search-config-note button {
  border: 0;
  padding: 0;
  background: transparent;
  color: #3167bd;
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
}
.live-chat-shell, .live-message-list { min-height: 0; }
.live-empty { flex: 1; }
.live-message-list { flex: 1; }
.source-summary { max-width: min(84%, 760px); color: #718096; font-size: 11px; }
.source-summary details { border: 1px solid #e8edf3; border-radius: 9px; background: #fbfcfe; }
.source-summary summary { padding: 9px 12px; cursor: pointer; color: #55729e; }
.source-summary .message-resources { padding: 0 9px 9px; }
.source-empty { margin: 0; padding: 0 12px 10px; color: #929cad; font-size: 10px; }
.tool-avatar { color: #5779a9; }
.typing-dots { display: inline-flex; gap: 3px; margin-left: 4px; vertical-align: middle; }
.typing-dots i { width: 4px; height: 4px; border-radius: 50%; background: #8e9db2; animation: typing-pulse 1s infinite ease-in-out; }
.typing-dots i:nth-child(2) { animation-delay: .15s; }
.typing-dots i:nth-child(3) { animation-delay: .3s; }
@keyframes typing-pulse { 0%, 60%, 100% { opacity: .35; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-2px); } }
.chat-composer {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 13px 20px;
  border-top: 1px solid #edf0f5;
  background: #fff;
}
.chat-composer textarea {
  flex: 1;
  min-height: 46px;
  max-height: 144px;
  resize: vertical;
  padding: 12px 14px;
  border: 1px solid #e0e6ef;
  border-radius: 12px;
  outline: none;
  background: #fbfcfe;
  color: #29374d;
  font: inherit;
  font-size: 14px;
  line-height: 1.55;
}
.chat-composer textarea:focus { border-color: #96b5e5; box-shadow: 0 0 0 3px rgba(64, 119, 204, .1); background: #fff; }
.chat-composer textarea:disabled { color: #9aa4b3; cursor: not-allowed; }
.chat-composer button {
  flex: 0 0 46px;
  width: 46px;
  height: 46px;
  border: 0;
  border-radius: 12px;
  background: #326ed0;
  color: #fff;
  font-size: 17px;
  cursor: pointer;
}
.chat-composer button:hover:not(:disabled) { background: #245bb4; }
.chat-composer button:disabled { background: #d6deea; cursor: not-allowed; }
.teach-content { padding: 28px clamp(20px, 5vw, 60px); }
.teach-intro { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 28px; }
.teach-icon {
  flex: 0 0 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: #edf3ff;
  color: #3e70c5;
  font-size: 18px;
}
.teach-intro h2, .outputs-heading h2 { margin: 1px 0 6px; color: #243149; font-size: 16px; }
.teach-intro p, .outputs-heading p { margin: 0; color: #7c8799; font-size: 11px; line-height: 1.7; }
.teach-content .el-textarea { margin-bottom: 12px; }
.teach-content >>> .el-textarea__inner { border-color: #e1e6ef; background: #fbfcfe; color: #334057; line-height: 1.8; font-size: 12px; padding: 13px 14px; }
.teach-footer { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.teach-footer span { color: #929cad; font-size: 10px; }
.saved-note { margin-top: 16px; color: #48805e; font-size: 11px; }
.saved-note i { margin-right: 5px; }
.outputs-content { padding: 26px clamp(20px, 4vw, 48px); }
.outputs-heading { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.result-count { padding: 6px 10px; border-radius: 999px; background: #f2f5fa; color: #67748a; font-size: 10px; }
.resource-section + .resource-section { margin-top: 26px; }
.section-title { display: flex; align-items: center; gap: 9px; margin-bottom: 11px; }
.section-title h3 { margin: 0; color: #39465b; font-size: 12px; }
.section-title > span:last-child { color: #9aa4b3; font-size: 10px; }
.file-icon, .link-icon {
  display: inline-grid;
  place-items: center;
  width: 25px;
  height: 25px;
  border-radius: 7px;
  color: #4773bc;
  background: #eff4fc;
  font-size: 12px;
}
.link-icon { color: #438168; background: #edf7f1; }
.resource-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 310px), 1fr)); gap: 9px; }
.resource-card {
  min-width: 0;
  min-height: 58px;
  padding: 10px 11px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid #e8edf3;
  border-radius: 9px;
  background: #fff;
  color: inherit;
  text-decoration: none;
  transition: border-color .15s ease, background .15s ease;
}
.resource-card:hover { border-color: #cbd9f0; background: #fbfcff; }
.resource-type {
  flex: 0 0 35px;
  height: 35px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: #f1f4f8;
  color: #647289;
  font-size: 8px;
  font-weight: 700;
}
.resource-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4px; }
.resource-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #344159; font-size: 11px; font-weight: 650; }
.resource-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #9aa4b3; font-size: 9px; }
.resource-action {
  flex: 0 0 26px;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 7px;
  color: #5e78a4;
  background: #f2f5fa;
  font-size: 13px;
  cursor: pointer;
  text-decoration: none;
}
.link-card .resource-action { display: grid; }
.resource-empty { min-height: 100px; display: flex; align-items: center; justify-content: center; gap: 9px; color: #929cad; font-size: 11px; text-align: center; padding: 18px; }
.resource-empty i { font-size: 19px; color: #b3bdca; }
.small-empty { min-height: 58px; justify-content: flex-start; padding: 10px 0; font-size: 10px; }
.resource-footnote { margin: 26px 0 0; color: #a0a8b5; font-size: 10px; }
.empty-mark { width: 48px; height: 48px; display: grid; place-items: center; border-radius: 14px; color: #4c73b6; background: #eff4fc; font-size: 21px; }
.loading-cover { text-align: center; color: #718098; font-size: 12px; padding: 18px; }
.loading-cover i { margin-right: 6px; }

@media (max-width: 900px) {
  .workbench-shell { width: calc(100% - 28px); padding-top: 24px; }
  .workbench-grid { grid-template-columns: 255px minmax(0, 1fr); }
  .workspace-tabs { gap: 17px; padding: 0 18px; }
  .message-list { padding: 18px; }
}
@media (max-width: 680px) {
  .workbench-shell { width: 100%; padding: 18px 12px 24px; }
  .workbench-grid { display: flex; flex-direction: column; min-height: calc(100vh - 165px); border-radius: 11px; }
  .session-panel { min-height: 0; padding: 14px; border-right: 0; border-bottom: 1px solid #e9edf3; }
  .session-heading { margin: 13px 2px 8px; }
  .session-list { display: flex; gap: 6px; overflow-x: auto; overflow-y: hidden; min-height: 51px; max-height: 66px; }
  .session-card { flex: 0 0 215px; margin: 0; padding: 7px; border: 1px solid #edf0f5; }
  .session-card.selected { border-color: #d8e5fa; }
  .quiet-state { min-width: 190px; min-height: 46px; }
  .load-older { min-width: 115px; }
  .history-notice { padding-top: 9px; margin-top: 8px; }
  .workspace-tabs { min-height: 51px; padding: 0 13px; gap: 16px; }
  .workspace-tabs button { height: 51px; font-size: 11px; }
  .record-state { font-size: 9px; }
  .tab-content { min-height: 390px; }
  .message-list { min-height: 350px; padding: 16px 12px; gap: 17px; }
  .message-body { max-width: 88%; }
  .message-bubble { padding: 9px 10px; font-size: 11px; }
  .teach-content, .outputs-content { padding: 20px 15px; }
  .teach-footer { align-items: flex-start; }
  .teach-footer span { line-height: 1.5; }
  .inline-notice { padding: 9px 12px; flex-wrap: wrap; }
  .chat-composer { padding: 10px 12px; gap: 8px; }
  .chat-composer textarea { min-height: 44px; padding: 10px 11px; font-size: 16px; }
  .chat-composer button { flex-basis: 44px; width: 44px; height: 44px; }
  .live-chat-toolbar { padding: 0 12px; }
  .live-chat-error { padding: 9px 12px; }
  .search-config-note { padding: 9px 12px; align-items: flex-start; }
  .source-summary { max-width: 88%; }
  .assistant-workbench >>> .header { min-width: 0 !important; height: 56px !important; padding: 0; }
  .assistant-workbench >>> .header-container { gap: 8px; padding: 0 10px; }
  .assistant-workbench >>> .header-left { min-width: 30px; flex: 0 0 30px; }
  .assistant-workbench >>> .brand-name { display: none; }
  .assistant-workbench >>> .header-center { flex: 1; min-width: 0; justify-content: flex-start; overflow-x: auto; scrollbar-width: none; }
  .assistant-workbench >>> .header-center::-webkit-scrollbar { display: none; }
  .assistant-workbench >>> .equipment-management { min-width: 0 !important; padding: 7px 8px; font-size: 10px; }
  .assistant-workbench >>> .nav-text { white-space: nowrap; }
  .assistant-workbench >>> .header-right { flex: 0 0 auto; }
  .assistant-workbench >>> .el-user-dropdown { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
</style>
