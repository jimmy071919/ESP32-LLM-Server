<template>
  <div class="reminders-page">
    <HeaderBar :devices="[]" />
    <main class="reminders-main">
      <div class="page-heading">
        <div>
          <h1>提醒與行事曆</h1>
          <p>{{ device ? `裝置 ${device} · 時間到時小智會直接提醒你` : '時間到時，小智會在待機狀態直接說出提醒。' }}</p>
        </div>
        <el-button icon="el-icon-refresh" :loading="loading" @click="load">重新整理</el-button>
      </div>

      <section class="panel create-panel">
        <div class="panel-heading">
          <h2>新增提醒</h2>
          <span>設定一次或重複提醒</span>
        </div>
        <label class="field-label" for="reminder-text">提醒內容</label>
        <el-input id="reminder-text" v-model="text" maxlength="200" show-word-limit placeholder="例如：吃藥、出門倒垃圾" />
        <div class="mode-options" role="group" aria-label="重複方式">
          <button v-for="option in modes" :key="option.value" type="button" :class="{ selected: mode === option.value }" @click="setMode(option.value)">
            {{ option.label }}
          </button>
        </div>
        <div class="fields-row">
          <div class="field">
            <label class="field-label" for="reminder-time">時間</label>
            <input id="reminder-time" v-model="time" class="native-input" type="time" required>
          </div>
          <div v-if="mode === 'once'" class="field">
            <label class="field-label" for="reminder-date">日期</label>
            <input id="reminder-date" v-model="date" class="native-input" type="date" required>
          </div>
        </div>
        <div v-if="mode === 'custom'" class="weekdays" role="group" aria-label="選擇星期">
          <button v-for="(day, index) in weekdays" :key="day" type="button" :class="{ selected: selectedDays.includes(index) }" :aria-pressed="selectedDays.includes(index)" @click="toggleDay(index)">
            {{ day }}
          </button>
        </div>
        <div class="form-actions">
          <el-button type="primary" :loading="saving" @click="save">新增提醒</el-button>
          <el-button :loading="testing" @click="test">立即試播</el-button>
          <span v-if="message" class="form-message" :class="messageType" role="status">{{ message }}</span>
        </div>
      </section>

      <section class="panel list-panel">
        <div class="panel-heading list-heading">
          <div>
            <h2>已設定提醒</h2>
            <span>{{ reminders.length }} 項</span>
          </div>
        </div>
        <div v-if="loading && !reminders.length" class="empty-state">載入提醒中…</div>
        <div v-else-if="!reminders.length" class="empty-state">
          <i class="el-icon-alarm-clock"></i>
          <strong>還沒有提醒</strong>
          <span>新增一項提醒，小智會在指定時間通知你。</span>
        </div>
        <ul v-else class="reminder-list">
          <li v-for="item in reminders" :key="item.id" class="reminder-item" :class="{ disabled: !item.enabled }">
            <div class="reminder-time">{{ item.time }}</div>
            <div class="reminder-copy">
              <strong>{{ item.text }}</strong>
              <span>{{ repeatLabel(item) }}<template v-if="item.next_at"> · 下次 {{ formatTimestamp(item.next_at) }}</template><template v-if="item.last_status"> · {{ statusLabel(item.last_status) }}</template></span>
            </div>
            <el-button size="mini" plain @click="toggle(item)">{{ item.enabled ? '停用' : '啟用' }}</el-button>
            <el-button size="mini" type="danger" plain @click="remove(item)">刪除</el-button>
          </li>
        </ul>
      </section>
    </main>
  </div>
</template>

<script>
import HeaderBar from '@/components/HeaderBar.vue'

export default {
  name: 'Reminders',
  components: { HeaderBar },
  data() {
    const now = new Date()
    const soon = new Date(now.getTime() + 5 * 60000)
    return {
      reminders: [],
      device: '',
      loading: false,
      saving: false,
      testing: false,
      text: '',
      mode: 'once',
      date: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`,
      time: `${String(soon.getHours()).padStart(2, '0')}:${String(soon.getMinutes()).padStart(2, '0')}`,
      selectedDays: [],
      weekdays: ['一', '二', '三', '四', '五', '六', '日'],
      modes: [
        { value: 'once', label: '單次' },
        { value: 'daily', label: '每天' },
        { value: 'weekdays', label: '平日' },
        { value: 'custom', label: '自訂星期' }
      ],
      message: '',
      messageType: '',
      refreshTimer: null
    }
  },
  mounted() {
    this.load()
    this.refreshTimer = setInterval(this.load, 30000)
  },
  beforeDestroy() {
    clearInterval(this.refreshTimer)
  },
  methods: {
    token() {
      try {
        return JSON.parse(localStorage.getItem('token') || '{}').token || ''
      } catch (error) {
        return ''
      }
    },
    async request(path, options = {}) {
      const token = this.token()
      if (!token) {
        this.$router.replace('/login')
        throw new Error('請先登入智控台')
      }
      const response = await fetch(`/reminders/api${path}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          ...(options.headers || {})
        }
      })
      const data = await response.json().catch(() => ({}))
      if (response.status === 401) {
        localStorage.removeItem('token')
        this.$router.replace('/login')
        throw new Error('登入已逾時，請重新登入')
      }
      if (!response.ok) throw new Error(data.error || '請求失敗')
      return data
    },
    async load() {
      this.loading = true
      try {
        const data = await this.request('/items')
        this.reminders = data.items
        this.device = data.device
      } catch (error) {
        if (error.message !== '請先登入智控台') this.showMessage(error.message, 'error')
      } finally {
        this.loading = false
      }
    },
    setMode(mode) {
      this.mode = mode
      if (mode !== 'custom') this.selectedDays = []
    },
    toggleDay(index) {
      this.selectedDays = this.selectedDays.includes(index)
        ? this.selectedDays.filter(day => day !== index)
        : [...this.selectedDays, index].sort((a, b) => a - b)
    },
    daysForSave() {
      if (this.mode === 'daily') return [0, 1, 2, 3, 4, 5, 6]
      if (this.mode === 'weekdays') return [0, 1, 2, 3, 4]
      return this.mode === 'custom' ? this.selectedDays : []
    },
    async save() {
      if (!this.text.trim()) return this.showMessage('請輸入提醒內容', 'error')
      if (!this.time) return this.showMessage('請選擇提醒時間', 'error')
      if (this.mode === 'once' && !this.date) return this.showMessage('請選擇提醒日期', 'error')
      if (this.mode === 'custom' && !this.selectedDays.length) return this.showMessage('請選擇星期', 'error')
      this.saving = true
      try {
        await this.request('/items', {
          method: 'POST',
          body: JSON.stringify({
            text: this.text.trim(),
            time: this.time,
            date: this.mode === 'once' ? this.date : null,
            days: this.daysForSave()
          })
        })
        this.text = ''
        this.showMessage('提醒已新增', 'success')
        await this.load()
      } catch (error) {
        this.showMessage(error.message, 'error')
      } finally {
        this.saving = false
      }
    },
    async test() {
      this.testing = true
      try {
        const data = await this.request('/test', {
          method: 'POST',
          body: JSON.stringify({ text: this.text.trim() || '這是一則測試提醒' })
        })
        const labels = { notified: '已送出試播提醒', spoken: '已在對話中說出', offline: '裝置目前離線', busy: '裝置忙碌', error: '試播失敗' }
        this.showMessage(labels[data.status] || data.status, ['notified', 'spoken'].includes(data.status) ? 'success' : 'error')
      } catch (error) {
        this.showMessage(error.message, 'error')
      } finally {
        this.testing = false
      }
    },
    async toggle(item) {
      try {
        await this.request(`/items/${item.id}`, {
          method: 'PUT',
          body: JSON.stringify({ enabled: !item.enabled })
        })
        await this.load()
      } catch (error) {
        this.showMessage(error.message, 'error')
      }
    },
    async remove(item) {
      try {
        await this.$confirm(`刪除「${item.text}」？`, '刪除提醒', {
          confirmButtonText: '刪除',
          cancelButtonText: '取消',
          type: 'warning'
        })
        await this.request(`/items/${item.id}`, { method: 'DELETE' })
        await this.load()
      } catch (error) {
        if (error !== 'cancel' && error !== 'close') this.showMessage(error.message || '刪除失敗', 'error')
      }
    },
    repeatLabel(item) {
      if (!item.days) return item.date || '單次提醒'
      const days = item.days.split(',').map(Number)
      if (days.length === 7) return '每天'
      if (days.join(',') === '0,1,2,3,4') return '平日'
      return `每週${days.map(day => this.weekdays[day]).join('、')}`
    },
    formatTimestamp(timestamp) {
      const value = new Date(timestamp * 1000)
      return `${value.getMonth() + 1}/${value.getDate()} ${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}`
    },
    statusLabel(status) {
      const labels = { notified: '已送出', spoken: '已說出', offline: '裝置離線', error: '失敗', missed: '已錯過' }
      return labels[status] || (status.startsWith('retrying') ? '重試中' : status)
    },
    showMessage(message, type) {
      this.message = message
      this.messageType = type
    }
  }
}
</script>

<style scoped>
.reminders-page{min-height:100vh;background:#f5f7fa;color:#1d2433;text-align:left}
.reminders-main{width:min(920px,calc(100% - 40px));margin:0 auto;padding:30px 0 56px}
.page-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:22px}
.page-heading h1{margin:0;font-size:24px;font-weight:650;letter-spacing:-.02em}
.page-heading p{margin:5px 0 0;color:#6b7280;font-size:13px}
.panel{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin-bottom:16px}
.panel-heading{display:flex;align-items:baseline;gap:10px;margin-bottom:18px}
.panel-heading h2{margin:0;font-size:16px;font-weight:650;color:#1d2433}
.panel-heading>span,.list-heading span{color:#6b7280;font-size:12px}
.field-label{display:block;margin:0 0 7px;color:#4b5563;font-size:13px;font-weight:500}
.mode-options{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}
.mode-options button,.weekdays button{min-height:36px;padding:0 14px;border:1px solid #e5e7eb;border-radius:8px;background:#fff;color:#4b5563;font:inherit;font-size:13px;cursor:pointer;transition:background .15s,border-color .15s,color .15s}
.mode-options button.selected,.weekdays button.selected{border-color:#bfdbfe;background:#eff6ff;color:#1d4ed8;font-weight:600}
.fields-row{display:flex;gap:16px;margin-top:16px}
.field{flex:1;min-width:0}
.native-input{width:100%;height:40px;padding:0 11px;border:1px solid #dcdfe6;border-radius:4px;background:#fff;color:#1d2433;font:inherit}
.native-input:focus{outline:0;border-color:#409eff}
.weekdays{display:flex;gap:7px;margin-top:14px}
.weekdays button{width:40px;padding:0}
.form-actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-top:18px}
.form-message{font-size:13px}
.form-message.success{color:#1f8a4c}
.form-message.error{color:#c8372d}
.list-heading{justify-content:space-between;margin-bottom:0}
.list-heading>div{display:flex;align-items:baseline;gap:10px}
.empty-state{display:flex;flex-direction:column;align-items:center;gap:7px;padding:40px 14px 24px;color:#6b7280;text-align:center;font-size:13px}
.empty-state i{font-size:24px;color:#8aa5d3}
.empty-state strong{color:#374151;font-size:14px}
.reminder-list{list-style:none;margin:0;padding:0}
.reminder-item{display:flex;align-items:center;gap:12px;padding:15px 0;border-top:1px solid #eef0f3}
.reminder-item:first-child{margin-top:14px}
.reminder-item.disabled{opacity:.48}
.reminder-time{min-width:70px;color:#1d2433;font-size:22px;font-weight:650;font-variant-numeric:tabular-nums}
.reminder-copy{display:flex;flex:1;flex-direction:column;gap:3px;min-width:0}
.reminder-copy strong{overflow-wrap:anywhere;font-size:14px;font-weight:550}
.reminder-copy span{color:#6b7280;font-size:12px}
@media(max-width:900px){.reminders-page ::v-deep .header{min-width:0}.reminders-page ::v-deep .header-container{padding:0 8px}.reminders-page ::v-deep .header-left{min-width:38px}.reminders-page ::v-deep .header-center{flex:1;justify-content:center;gap:0}.reminders-page ::v-deep .equipment-management{min-width:0;padding:7px 8px;font-size:12px}.reminders-page ::v-deep .header-right{gap:3px}.reminders-page ::v-deep .el-user-dropdown{display:none}}
@media(max-width:700px){.reminders-main{width:calc(100% - 28px);padding-top:22px}.panel{padding:16px}.reminder-item{flex-wrap:wrap}.reminder-copy{min-width:calc(100% - 90px)}.fields-row{gap:10px}}
</style>
