<template>
  <div class="shell">
    <div class="backdrop backdrop-a"></div>
    <div class="backdrop backdrop-b"></div>
    <main class="layout">
      <section class="hero panel">
        <div class="hero-copy">
          <p class="eyebrow">DZDP MONITOR CONSOLE</p>
          <h1>大众点评库存监控台</h1>
          <p class="hero-text">
            套餐增删改查、飞书分组路由、轮询频率与代理池入口都集中在这里。前端适合部署到 Cloudflare，监控和 API 继续留在你自己的服务器。
          </p>
        </div>
        <div class="connection-card">
          <h2>连接设置</h2>
          <label>
            <span>API 地址</span>
            <input v-model.trim="apiBaseUrl" type="text" placeholder="https://api.example.com" />
          </label>
          <label>
            <span>Bearer Token</span>
            <input v-model.trim="authToken" type="password" placeholder="可选，若服务端已配置鉴权则必填" />
          </label>
          <div class="button-row">
            <button class="btn btn-primary" :disabled="loading.dashboard" @click="saveConnection">
              {{ loading.dashboard ? '连接中...' : '保存并刷新' }}
            </button>
            <button class="btn btn-secondary" :disabled="loading.dashboard" @click="loadDashboard">
              刷新面板
            </button>
          </div>
          <div class="connection-meta">
            <span :class="['status-dot', dashboardReady ? 'online' : 'offline']"></span>
            <span>{{ dashboardReady ? '已连接' : '未连接' }}</span>
            <span v-if="dashboard.admin_api && dashboard.admin_api.auth_token_configured">服务端已启用鉴权</span>
          </div>
        </div>
      </section>

      <section v-if="notice.message" :class="['notice', notice.type === 'error' ? 'notice-error' : 'notice-success']">
        {{ notice.message }}
      </section>

      <section class="summary-grid">
        <article v-for="card in summaryCards" :key="card.label" class="summary-card panel">
          <p class="summary-label">{{ card.label }}</p>
          <strong class="summary-value">{{ card.value }}</strong>
          <span class="summary-hint">{{ card.hint }}</span>
        </article>
      </section>

      <section class="content-grid">
        <article class="panel section-card">
          <div class="section-head">
            <div>
              <p class="section-kicker">Targets</p>
              <h2>监控套餐</h2>
            </div>
            <button class="btn btn-secondary" :disabled="loading.dashboard" @click="loadDashboard">刷新列表</button>
          </div>

          <form class="stack-form" @submit.prevent="submitTarget">
            <div class="form-grid">
              <label>
                <span>套餐名</span>
                <input v-model.trim="targetForm.name" type="text" placeholder="例如：春意寻味双人餐" required />
              </label>
              <label>
                <span>推送分组</span>
                <select v-model="targetForm.group_key">
                  <option v-for="group in dashboard.notify_groups" :key="group.key" :value="group.key">
                    {{ group.name }} ({{ group.key }})
                  </option>
                </select>
              </label>
            </div>
            <label>
              <span>链接</span>
              <textarea v-model.trim="targetForm.url" rows="3" placeholder="https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=..." required></textarea>
            </label>
            <div class="button-row">
              <button class="btn btn-primary" :disabled="loading.targetSubmit" type="submit">
                {{ loading.targetSubmit ? '提交中...' : (editingTargetIndex ? '保存套餐' : '新增套餐') }}
              </button>
              <button v-if="editingTargetIndex" class="btn btn-secondary" type="button" @click="resetTargetForm">取消编辑</button>
            </div>
          </form>

          <div class="card-list">
            <article v-for="target in dashboard.targets" :key="target.activity_id" class="target-card">
              <div class="target-head">
                <div>
                  <div class="target-title-row">
                    <span class="target-index">#{{ target.index }}</span>
                    <h3>{{ target.name }}</h3>
                  </div>
                  <p class="target-subtitle">{{ target.group_name || target.group_key }} / {{ target.group_key }}</p>
                </div>
                <span :class="['pill', stateClass(target.last_state)]">{{ stateLabel(target.last_state) }}</span>
              </div>
              <p v-if="target.last_title" class="muted">接口标题：{{ target.last_title }}</p>
              <a class="target-link" :href="target.url" target="_blank" rel="noreferrer">{{ target.url }}</a>
              <div class="meta-grid">
                <span>最近变更：{{ target.last_change_ts || '暂无' }}</span>
                <span>失败次数：{{ target.fail_count || 0 }}</span>
                <span v-if="target.last_error_text">错误连击：{{ target.last_error_streak || 0 }}</span>
              </div>
              <p v-if="target.last_error_text" class="error-text">{{ target.last_error_text }}</p>
              <div class="button-row compact-row">
                <button class="btn btn-secondary" @click="startEditTarget(target)">编辑</button>
                <button class="btn btn-danger" @click="removeTarget(target)">删除</button>
              </div>
            </article>
            <div v-if="!dashboard.targets.length" class="empty-state">还没有监控套餐，先在上面新增一个。</div>
          </div>
        </article>

        <article class="panel section-card">
          <div class="section-head">
            <div>
              <p class="section-kicker">Notify Routing</p>
              <h2>飞书推送分组</h2>
            </div>
          </div>

          <form class="stack-form" @submit.prevent="submitGroup">
            <div class="form-grid">
              <label>
                <span>分组名</span>
                <input v-model.trim="groupForm.name" type="text" placeholder="例如：武汉群" required />
              </label>
              <label>
                <span>分组 Key</span>
                <input v-model.trim="groupForm.key" type="text" placeholder="留空则自动生成" />
              </label>
            </div>
            <label>
              <span>Webhook</span>
              <input v-model.trim="groupForm.webhook" type="text" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
            </label>
            <label v-if="editingGroupKey" class="checkbox-row">
              <input v-model="groupForm.clear_webhook" type="checkbox" />
              <span>保存时清空该分组的 webhook</span>
            </label>
            <label v-if="editingGroupKey" class="checkbox-row">
              <input v-model="groupForm.make_default" type="checkbox" />
              <span>设为默认分组</span>
            </label>
            <div class="button-row">
              <button class="btn btn-primary" :disabled="loading.groupSubmit" type="submit">
                {{ loading.groupSubmit ? '提交中...' : (editingGroupKey ? '保存分组' : '新增分组') }}
              </button>
              <button v-if="editingGroupKey" class="btn btn-secondary" type="button" @click="resetGroupForm">取消编辑</button>
            </div>
          </form>

          <div class="card-list compact-list">
            <article v-for="group in dashboard.notify_groups" :key="group.key" class="group-card">
              <div class="target-head">
                <div>
                  <h3>{{ group.name }}</h3>
                  <p class="target-subtitle">{{ group.key }}</p>
                </div>
                <span :class="['pill', group.is_default ? 'pill-warm' : 'pill-neutral']">
                  {{ group.is_default ? '默认分组' : '备用分组' }}
                </span>
              </div>
              <p class="muted">Webhook：{{ group.webhook_masked || '未配置' }}</p>
              <p class="muted">状态：{{ group.webhook_configured ? '已配置' : '未配置' }}</p>
              <div class="button-row compact-row">
                <button class="btn btn-secondary" @click="startEditGroup(group)">编辑</button>
                <button class="btn btn-danger" :disabled="dashboard.notify_groups.length <= 1" @click="removeGroup(group)">删除</button>
              </div>
            </article>
          </div>
        </article>
      </section>

      <section class="content-grid lower-grid">
        <article class="panel section-card">
          <div class="section-head">
            <div>
              <p class="section-kicker">Polling</p>
              <h2>轮询频率</h2>
            </div>
          </div>
          <form class="inline-form" @submit.prevent="submitPoll">
            <label>
              <span>轮询秒数</span>
              <input v-model.number="pollSeconds" min="5" step="1" type="number" required />
            </label>
            <button class="btn btn-primary" :disabled="loading.pollSubmit" type="submit">
              {{ loading.pollSubmit ? '保存中...' : '保存轮询配置' }}
            </button>
          </form>
          <p class="muted">当前配置会热更新到运行中的监控进程，不需要重启容器。</p>
        </article>

        <article class="panel section-card proxy-card">
          <div class="section-head">
            <div>
              <p class="section-kicker">Proxy Pool</p>
              <h2>代理池接入入口</h2>
            </div>
          </div>
          <form class="stack-form" @submit.prevent="submitProxy">
            <div class="form-grid three-col">
              <label class="checkbox-card">
                <span>启用代理池</span>
                <input v-model="proxyForm.enabled" type="checkbox" />
              </label>
              <label>
                <span>Provider</span>
                <input v-model.trim="proxyForm.provider" type="text" placeholder="generic_json" />
              </label>
              <label>
                <span>请求方法</span>
                <select v-model="proxyForm.request_method">
                  <option value="GET">GET</option>
                  <option value="POST">POST</option>
                </select>
              </label>
            </div>
            <div class="form-grid">
              <label>
                <span>API URL</span>
                <input v-model.trim="proxyForm.api_url" type="text" placeholder="https://proxy-provider.example.com/get" />
              </label>
              <label>
                <span>API Key Header</span>
                <input v-model.trim="proxyForm.api_key_header" type="text" placeholder="X-API-Key" />
              </label>
            </div>
            <label>
              <span>API Key</span>
              <input v-model.trim="proxyForm.api_key" type="password" placeholder="保存时写入服务端配置" />
            </label>
            <div class="form-grid">
              <label>
                <span>缓存秒数</span>
                <input v-model.number="proxyForm.cache_seconds" min="1" step="1" type="number" />
              </label>
              <label>
                <span>超时秒数</span>
                <input v-model.number="proxyForm.timeout_seconds" min="1" step="1" type="number" />
              </label>
              <label>
                <span>Sticky 模式</span>
                <select v-model="proxyForm.sticky_mode">
                  <option value="shared">shared</option>
                  <option value="per_target">per_target</option>
                </select>
              </label>
            </div>
            <label class="checkbox-row">
              <input v-model="proxyForm.verify_ssl" type="checkbox" />
              <span>验证代理池接口 SSL 证书</span>
            </label>
            <div class="form-grid">
              <label>
                <span>extra_headers(JSON)</span>
                <textarea v-model.trim="proxyForm.extra_headers_json" rows="4"></textarea>
              </label>
              <label>
                <span>query_params(JSON)</span>
                <textarea v-model.trim="proxyForm.query_params_json" rows="4"></textarea>
              </label>
            </div>
            <div class="form-grid">
              <label>
                <span>request_body(JSON)</span>
                <textarea v-model.trim="proxyForm.request_body_json" rows="4"></textarea>
              </label>
              <label>
                <span>response_fields(JSON)</span>
                <textarea v-model.trim="proxyForm.response_fields_json" rows="4"></textarea>
              </label>
            </div>
            <label>
              <span>response_data_path</span>
              <input v-model.trim="proxyForm.response_data_path" type="text" placeholder="例如 data.items.0" />
            </label>
            <div class="button-row">
              <button class="btn btn-primary" :disabled="loading.proxySubmit" type="submit">
                {{ loading.proxySubmit ? '保存中...' : '保存代理配置' }}
              </button>
            </div>
            <p class="muted">这一块是预留入口。后续只要填 provider API 地址、key 和字段映射，就能切到代理池模式。</p>
          </form>
        </article>
      </section>
    </main>
  </div>
</template>

<script>
import {
  addNotifyGroup,
  addTarget,
  deleteNotifyGroup,
  deleteTarget,
  getDashboard,
  updateNotifyGroup,
  updatePoll,
  updateProxy,
  updateTarget
} from './services/api';

const DEFAULT_RESPONSE_FIELDS = {
  proxy_url: 'proxy_url',
  scheme: 'scheme',
  host: 'host',
  port: 'port',
  username: 'username',
  password: 'password'
};

function defaultDashboard() {
  return {
    summary: {
      total_targets: 0,
      in_stock: 0,
      sold_out: 0,
      unknown: 0,
      error_targets: 0
    },
    targets: [],
    notify_groups: [],
    poll: { interval_seconds: 60 },
    proxy: {
      enabled: false,
      provider: 'generic_json',
      request_method: 'GET',
      api_url: '',
      api_key_header: 'X-API-Key',
      api_key_configured: false,
      extra_headers: {},
      query_params: {},
      request_body: {},
      response_data_path: '',
      response_fields: { ...DEFAULT_RESPONSE_FIELDS },
      cache_seconds: 120,
      timeout_seconds: 8,
      sticky_mode: 'shared',
      verify_ssl: true
    },
    admin_api: {
      auth_token_configured: false
    }
  };
}

function defaultTargetForm() {
  return {
    name: '',
    url: '',
    group_key: ''
  };
}

function defaultGroupForm() {
  return {
    name: '',
    key: '',
    webhook: '',
    clear_webhook: false,
    make_default: false
  };
}

function defaultProxyForm() {
  return {
    enabled: false,
    provider: 'generic_json',
    request_method: 'GET',
    api_url: '',
    api_key: '',
    api_key_header: 'X-API-Key',
    extra_headers_json: '{\n}',
    query_params_json: '{\n}',
    request_body_json: '{\n}',
    response_data_path: '',
    response_fields_json: JSON.stringify(DEFAULT_RESPONSE_FIELDS, null, 2),
    cache_seconds: 120,
    timeout_seconds: 8,
    sticky_mode: 'shared',
    verify_ssl: true
  };
}

function localValue(key, fallback) {
  return window.localStorage.getItem(key) || fallback;
}

export default {
  name: 'DzdpMonitorConsole',
  data() {
    return {
      apiBaseUrl: localValue('dzdp_api_base_url', process.env.VUE_APP_API_BASE_URL || 'http://127.0.0.1:8787'),
      authToken: localValue('dzdp_api_token', ''),
      dashboard: defaultDashboard(),
      dashboardReady: false,
      loading: {
        dashboard: false,
        targetSubmit: false,
        groupSubmit: false,
        pollSubmit: false,
        proxySubmit: false
      },
      notice: {
        type: 'success',
        message: ''
      },
      editingTargetIndex: null,
      targetForm: defaultTargetForm(),
      editingGroupKey: '',
      groupForm: defaultGroupForm(),
      pollSeconds: 60,
      proxyForm: defaultProxyForm()
    };
  },
  computed: {
    summaryCards() {
      const summary = this.dashboard.summary || {};
      return [
        { label: '监控总数', value: summary.total_targets || 0, hint: '当前配置中的套餐数量' },
        { label: '有货套餐', value: summary.in_stock || 0, hint: '最近一次轮询状态为 IN_STOCK' },
        { label: '售罄套餐', value: summary.sold_out || 0, hint: '最近一次轮询状态为 SOLD_OUT' },
        { label: '异常套餐', value: summary.error_targets || 0, hint: '最近一次状态里带错误信息' }
      ];
    }
  },
  created() {
    this.loadDashboard();
  },
  methods: {
    setNotice(type, message) {
      this.notice = { type, message };
      if (!message) {
        return;
      }
      window.clearTimeout(this.noticeTimer);
      this.noticeTimer = window.setTimeout(() => {
        this.notice.message = '';
      }, 4000);
    },
    stateClass(state) {
      if (state === 'IN_STOCK') {
        return 'pill-green';
      }
      if (state === 'SOLD_OUT') {
        return 'pill-amber';
      }
      return 'pill-neutral';
    },
    stateLabel(state) {
      if (state === 'IN_STOCK') {
        return '有货';
      }
      if (state === 'SOLD_OUT') {
        return '售罄';
      }
      return '未知';
    },
    saveConnection() {
      window.localStorage.setItem('dzdp_api_base_url', this.apiBaseUrl);
      window.localStorage.setItem('dzdp_api_token', this.authToken);
      this.loadDashboard();
    },
    applyDashboard(payload) {
      this.dashboard = payload || defaultDashboard();
      this.dashboardReady = true;
      this.pollSeconds = (this.dashboard.poll && this.dashboard.poll.interval_seconds) || 60;
      if (!this.targetForm.group_key && this.dashboard.notify_groups.length) {
        this.targetForm.group_key = this.dashboard.notify_groups[0].key;
      }
      this.proxyForm = {
        enabled: !!this.dashboard.proxy.enabled,
        provider: this.dashboard.proxy.provider || 'generic_json',
        request_method: this.dashboard.proxy.request_method || 'GET',
        api_url: this.dashboard.proxy.api_url || '',
        api_key: '',
        api_key_header: this.dashboard.proxy.api_key_header || 'X-API-Key',
        extra_headers_json: JSON.stringify(this.dashboard.proxy.extra_headers || {}, null, 2),
        query_params_json: JSON.stringify(this.dashboard.proxy.query_params || {}, null, 2),
        request_body_json: JSON.stringify(this.dashboard.proxy.request_body || {}, null, 2),
        response_data_path: this.dashboard.proxy.response_data_path || '',
        response_fields_json: JSON.stringify(this.dashboard.proxy.response_fields || DEFAULT_RESPONSE_FIELDS, null, 2),
        cache_seconds: this.dashboard.proxy.cache_seconds || 120,
        timeout_seconds: this.dashboard.proxy.timeout_seconds || 8,
        sticky_mode: this.dashboard.proxy.sticky_mode || 'shared',
        verify_ssl: this.dashboard.proxy.verify_ssl !== false
      };
    },
    async loadDashboard() {
      this.loading.dashboard = true;
      try {
        const payload = await getDashboard(this.apiBaseUrl, this.authToken);
        this.applyDashboard(payload);
        this.setNotice('success', '面板已刷新');
      } catch (error) {
        this.dashboardReady = false;
        this.setNotice('error', error.message || '加载面板失败');
      } finally {
        this.loading.dashboard = false;
      }
    },
    resetTargetForm() {
      this.editingTargetIndex = null;
      this.targetForm = defaultTargetForm();
      if (this.dashboard.notify_groups.length) {
        this.targetForm.group_key = this.dashboard.notify_groups[0].key;
      }
    },
    startEditTarget(target) {
      this.editingTargetIndex = target.index;
      this.targetForm = {
        name: target.name,
        url: target.url,
        group_key: target.group_key
      };
    },
    async submitTarget() {
      this.loading.targetSubmit = true;
      try {
        if (this.editingTargetIndex) {
          await updateTarget(this.apiBaseUrl, this.authToken, this.editingTargetIndex, {
            set_name: this.targetForm.name,
            set_url: this.targetForm.url,
            set_group_key: this.targetForm.group_key
          });
          this.setNotice('success', `已更新套餐 #${this.editingTargetIndex}`);
        } else {
          await addTarget(this.apiBaseUrl, this.authToken, {
            name: this.targetForm.name,
            url: this.targetForm.url,
            group_key: this.targetForm.group_key
          });
          this.setNotice('success', '已新增套餐');
        }
        this.resetTargetForm();
        await this.loadDashboard();
      } catch (error) {
        this.setNotice('error', error.message || '提交套餐失败');
      } finally {
        this.loading.targetSubmit = false;
      }
    },
    async removeTarget(target) {
      if (!window.confirm(`删除监控套餐「${target.name}」？`)) {
        return;
      }
      try {
        await deleteTarget(this.apiBaseUrl, this.authToken, target.index);
        this.setNotice('success', `已删除套餐 #${target.index}`);
        if (this.editingTargetIndex === target.index) {
          this.resetTargetForm();
        }
        await this.loadDashboard();
      } catch (error) {
        this.setNotice('error', error.message || '删除套餐失败');
      }
    },
    resetGroupForm() {
      this.editingGroupKey = '';
      this.groupForm = defaultGroupForm();
    },
    startEditGroup(group) {
      this.editingGroupKey = group.key;
      this.groupForm = {
        name: group.name,
        key: group.key,
        webhook: '',
        clear_webhook: false,
        make_default: !!group.is_default
      };
    },
    async submitGroup() {
      this.loading.groupSubmit = true;
      try {
        if (this.editingGroupKey) {
          const payload = {
            set_name: this.groupForm.name,
            make_default: this.groupForm.make_default
          };
          if (this.groupForm.webhook) {
            payload.set_webhook = this.groupForm.webhook;
          } else if (this.groupForm.clear_webhook) {
            payload.set_webhook = '';
          }
          await updateNotifyGroup(this.apiBaseUrl, this.authToken, this.editingGroupKey, payload);
          this.setNotice('success', `已更新分组 ${this.editingGroupKey}`);
        } else {
          await addNotifyGroup(this.apiBaseUrl, this.authToken, {
            name: this.groupForm.name,
            key: this.groupForm.key,
            webhook: this.groupForm.webhook
          });
          this.setNotice('success', '已新增分组');
        }
        this.resetGroupForm();
        await this.loadDashboard();
      } catch (error) {
        this.setNotice('error', error.message || '保存分组失败');
      } finally {
        this.loading.groupSubmit = false;
      }
    },
    async removeGroup(group) {
      if (!window.confirm(`删除推送分组「${group.name}」？`)) {
        return;
      }
      try {
        await deleteNotifyGroup(this.apiBaseUrl, this.authToken, group.key);
        this.setNotice('success', `已删除分组 ${group.key}`);
        if (this.editingGroupKey === group.key) {
          this.resetGroupForm();
        }
        await this.loadDashboard();
      } catch (error) {
        this.setNotice('error', error.message || '删除分组失败');
      }
    },
    async submitPoll() {
      this.loading.pollSubmit = true;
      try {
        await updatePoll(this.apiBaseUrl, this.authToken, this.pollSeconds);
        this.setNotice('success', '轮询频率已更新');
        await this.loadDashboard();
      } catch (error) {
        this.setNotice('error', error.message || '更新轮询频率失败');
      } finally {
        this.loading.pollSubmit = false;
      }
    },
    parseJsonField(label, text) {
      try {
        const parsed = JSON.parse(text || '{}');
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          throw new Error(`${label} 必须是 JSON 对象`);
        }
        return parsed;
      } catch (error) {
        throw new Error(`${label} JSON 不合法：${error.message}`);
      }
    },
    async submitProxy() {
      this.loading.proxySubmit = true;
      try {
        const payload = {
          enabled: this.proxyForm.enabled,
          provider: this.proxyForm.provider,
          request_method: this.proxyForm.request_method,
          api_url: this.proxyForm.api_url,
          api_key: this.proxyForm.api_key,
          api_key_header: this.proxyForm.api_key_header,
          extra_headers: this.parseJsonField('extra_headers', this.proxyForm.extra_headers_json),
          query_params: this.parseJsonField('query_params', this.proxyForm.query_params_json),
          request_body: this.parseJsonField('request_body', this.proxyForm.request_body_json),
          response_data_path: this.proxyForm.response_data_path,
          response_fields: this.parseJsonField('response_fields', this.proxyForm.response_fields_json),
          cache_seconds: this.proxyForm.cache_seconds,
          timeout_seconds: this.proxyForm.timeout_seconds,
          sticky_mode: this.proxyForm.sticky_mode,
          verify_ssl: this.proxyForm.verify_ssl
        };
        await updateProxy(this.apiBaseUrl, this.authToken, payload);
        this.setNotice('success', '代理配置已更新');
        await this.loadDashboard();
      } catch (error) {
        this.setNotice('error', error.message || '保存代理配置失败');
      } finally {
        this.loading.proxySubmit = false;
      }
    }
  }
};
</script>

<style>
:root {
  --bg: #f2ebe0;
  --panel: rgba(255, 250, 245, 0.86);
  --panel-strong: #fff8ef;
  --border: rgba(110, 77, 57, 0.14);
  --text: #2f231c;
  --muted: #6c5b4f;
  --primary: #c95b36;
  --primary-dark: #8f3b1c;
  --teal: #1f7b77;
  --gold: #c08d22;
  --danger: #a63a2f;
  --shadow: 0 24px 48px rgba(97, 63, 44, 0.12);
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  margin: 0;
  min-height: 100%;
  font-family: Avenir, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  background: var(--bg);
  color: var(--text);
}

body {
  min-height: 100vh;
}

button,
input,
select,
textarea {
  font: inherit;
}

button {
  border: 0;
  cursor: pointer;
}

.shell {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
}

.backdrop {
  position: fixed;
  inset: auto;
  border-radius: 999px;
  filter: blur(20px);
  pointer-events: none;
}

.backdrop-a {
  top: -120px;
  right: -120px;
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(201, 91, 54, 0.24), rgba(201, 91, 54, 0));
}

.backdrop-b {
  bottom: -180px;
  left: -120px;
  width: 460px;
  height: 460px;
  background: radial-gradient(circle, rgba(31, 123, 119, 0.22), rgba(31, 123, 119, 0));
}

.layout {
  position: relative;
  z-index: 1;
  width: min(1240px, calc(100% - 32px));
  margin: 0 auto;
  padding: 28px 0 60px;
}

.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 28px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(16px);
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
  gap: 22px;
  padding: 28px;
  background:
    linear-gradient(140deg, rgba(255, 248, 239, 0.95), rgba(255, 240, 227, 0.85)),
    radial-gradient(circle at top left, rgba(201, 91, 54, 0.12), transparent 40%);
}

.eyebrow,
.section-kicker,
.summary-label {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 12px;
  color: var(--muted);
}

.hero h1,
.section-head h2 {
  margin: 8px 0 0;
  font-size: clamp(28px, 4vw, 44px);
  line-height: 1.02;
}

.hero-text {
  max-width: 640px;
  margin: 16px 0 0;
  font-size: 15px;
  line-height: 1.7;
  color: var(--muted);
}

.connection-card {
  padding: 22px;
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(255, 247, 239, 0.9));
  border: 1px solid rgba(201, 91, 54, 0.14);
}

.connection-card h2 {
  margin: 0 0 14px;
  font-size: 20px;
}

label {
  display: grid;
  gap: 8px;
  color: var(--muted);
  font-size: 14px;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid rgba(93, 68, 51, 0.14);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.88);
  color: var(--text);
  padding: 12px 14px;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

input:focus,
select:focus,
textarea:focus {
  outline: none;
  border-color: rgba(201, 91, 54, 0.55);
  transform: translateY(-1px);
}

textarea {
  resize: vertical;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.compact-row {
  margin-top: 12px;
}

.btn {
  padding: 12px 16px;
  border-radius: 999px;
  font-weight: 700;
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.btn-primary {
  background: linear-gradient(135deg, var(--primary), #dd7b3c);
  color: #fff9f4;
}

.btn-secondary {
  background: rgba(47, 35, 28, 0.08);
  color: var(--text);
}

.btn-danger {
  background: rgba(166, 58, 47, 0.12);
  color: var(--danger);
}

.connection-meta,
.meta-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  margin-top: 14px;
  color: var(--muted);
  font-size: 13px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  align-self: center;
}

.status-dot.online {
  background: var(--teal);
}

.status-dot.offline {
  background: var(--danger);
}

.notice {
  margin: 18px 0;
  padding: 14px 18px;
  border-radius: 18px;
  border: 1px solid transparent;
}

.notice-success {
  background: rgba(31, 123, 119, 0.1);
  border-color: rgba(31, 123, 119, 0.16);
}

.notice-error {
  background: rgba(166, 58, 47, 0.12);
  border-color: rgba(166, 58, 47, 0.18);
}

.summary-grid,
.content-grid {
  display: grid;
  gap: 18px;
}

.summary-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 18px 0;
}

.summary-card {
  padding: 22px;
}

.summary-value {
  display: block;
  margin-top: 12px;
  font-size: clamp(28px, 4vw, 42px);
}

.summary-hint,
.muted,
.target-subtitle {
  color: var(--muted);
}

.content-grid {
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
}

.lower-grid {
  margin-top: 18px;
  align-items: start;
}

.section-card {
  padding: 22px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 18px;
}

.stack-form {
  display: grid;
  gap: 14px;
}

.form-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.form-grid.three-col {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.checkbox-row,
.checkbox-card {
  display: flex;
  align-items: center;
  gap: 10px;
}

.checkbox-card {
  justify-content: space-between;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(93, 68, 51, 0.14);
}

.checkbox-row input,
.checkbox-card input {
  width: auto;
}

.inline-form {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 14px;
}

.card-list {
  display: grid;
  gap: 14px;
  margin-top: 18px;
}

.compact-list {
  margin-top: 16px;
}

.target-card,
.group-card {
  padding: 18px;
  border-radius: 22px;
  background: var(--panel-strong);
  border: 1px solid rgba(97, 63, 44, 0.1);
}

.target-head,
.target-title-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
}

.target-title-row {
  justify-content: flex-start;
  align-items: center;
}

.target-title-row h3,
.group-card h3 {
  margin: 0;
  font-size: 20px;
}

.target-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: rgba(201, 91, 54, 0.12);
  color: var(--primary-dark);
  font-weight: 800;
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.pill-green {
  background: rgba(31, 123, 119, 0.14);
  color: var(--teal);
}

.pill-amber,
.pill-warm {
  background: rgba(192, 141, 34, 0.16);
  color: var(--gold);
}

.pill-neutral {
  background: rgba(47, 35, 28, 0.08);
  color: var(--muted);
}

.target-link {
  display: inline-block;
  margin-top: 10px;
  color: var(--primary-dark);
  text-decoration: none;
  word-break: break-all;
}

.error-text {
  margin: 12px 0 0;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(166, 58, 47, 0.1);
  color: var(--danger);
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-state {
  padding: 24px;
  border-radius: 18px;
  border: 1px dashed rgba(97, 63, 44, 0.18);
  color: var(--muted);
  text-align: center;
}

.proxy-card textarea {
  min-height: 128px;
}

@media (max-width: 1080px) {
  .summary-grid,
  .content-grid,
  .hero,
  .form-grid,
  .form-grid.three-col {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .layout {
    width: min(100% - 20px, 1240px);
    padding-top: 18px;
    padding-bottom: 32px;
  }

  .hero,
  .section-card,
  .summary-card {
    border-radius: 22px;
    padding: 18px;
  }

  .target-head,
  .section-head,
  .inline-form {
    flex-direction: column;
    align-items: stretch;
  }

  .button-row {
    width: 100%;
  }

  .btn {
    width: 100%;
    justify-content: center;
  }

  .target-title-row h3,
  .group-card h3 {
    font-size: 18px;
  }
}
</style>
