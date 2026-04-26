import { useEffect, useState } from 'react'
import {
  Alert,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Button,
  Checkbox,
  Tag,
  Space,
  Typography,
  Descriptions,
} from 'antd'
import {
  PlayCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { ChatGPTRegistrationModeSwitch } from '@/components/ChatGPTRegistrationModeSwitch'
import { TaskLogPanel } from '@/components/TaskLogPanel'
import { usePersistentChatGPTRegistrationMode } from '@/hooks/usePersistentChatGPTRegistrationMode'
import { CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF } from '@/lib/chatgptRegistrationMode'
import { parseBooleanConfigValue } from '@/lib/configValueParsers'
import { buildChatGPTRegistrationRequestAdapter } from '@/lib/chatgptRegistrationRequestAdapter'
import { getExecutorOptions, normalizeExecutorForPlatform } from '@/lib/platformExecutorOptions'
import { apiFetch } from '@/lib/utils'

const { Text } = Typography

export default function RegisterTaskPage() {
  const [form] = Form.useForm()
  const [task, setTask] = useState<any>(null)
  const [polling, setPolling] = useState(false)
  const { mode: chatgptRegistrationMode, setMode: setChatgptRegistrationMode } =
    usePersistentChatGPTRegistrationMode()

  useEffect(() => {
    apiFetch('/config').then((cfg) => {
      const currentPlatform = form.getFieldValue('platform') || 'trae'
      form.setFieldsValue({
        executor_type: normalizeExecutorForPlatform(currentPlatform, cfg.default_executor),
        captcha_solver: cfg.default_captcha_solver || 'yescaptcha',
        mail_provider: cfg.mail_provider || 'luckmail',
        yescaptcha_key: cfg.yescaptcha_key || '',
        moemail_api_url: cfg.moemail_api_url || '',
        moemail_api_key: cfg.moemail_api_key || '',
        skymail_api_base: cfg.skymail_api_base || 'https://api.skymail.ink',
        skymail_token: cfg.skymail_token || '',
        skymail_domain: cfg.skymail_domain || '',
        laoudo_auth: cfg.laoudo_auth || '',
        laoudo_email: cfg.laoudo_email || '',
        laoudo_account_id: cfg.laoudo_account_id || '',
        gptmail_base_url: cfg.gptmail_base_url || 'https://mail.chatgpt.org.uk',
        gptmail_api_key: cfg.gptmail_api_key || '',
        gptmail_domain: cfg.gptmail_domain || '',
        opentrashmail_api_url: cfg.opentrashmail_api_url || '',
        opentrashmail_domain: cfg.opentrashmail_domain || '',
        opentrashmail_password: cfg.opentrashmail_password || '',
        maliapi_base_url: cfg.maliapi_base_url || 'https://maliapi.215.im/v1',
        maliapi_api_key: cfg.maliapi_api_key || '',
        maliapi_domain: cfg.maliapi_domain || '',
        maliapi_auto_domain_strategy: cfg.maliapi_auto_domain_strategy || 'balanced',
        duckmail_api_url: cfg.duckmail_api_url || '',
        duckmail_provider_url: cfg.duckmail_provider_url || '',
        duckmail_bearer: cfg.duckmail_bearer || '',
        freemail_api_url: cfg.freemail_api_url || '',
        freemail_admin_token: cfg.freemail_admin_token || '',
        freemail_username: cfg.freemail_username || '',
        freemail_password: cfg.freemail_password || '',
        cfworker_api_url: cfg.cfworker_api_url || '',
        cfworker_admin_token: cfg.cfworker_admin_token || '',
        cfworker_custom_auth: cfg.cfworker_custom_auth || '',
        cfworker_domain_override: '',
        cfworker_subdomain: cfg.cfworker_subdomain || '',
        cfworker_random_subdomain: parseBooleanConfigValue(cfg.cfworker_random_subdomain),
        cfworker_fingerprint: cfg.cfworker_fingerprint || '',
        gmail_imap_email: cfg.gmail_imap_email || '',
        gmail_imap_app_password: cfg.gmail_imap_app_password || '',
        gmail_imap_host: cfg.gmail_imap_host || 'imap.gmail.com',
        gmail_imap_port: cfg.gmail_imap_port || '993',
        gmail_imap_mailbox: cfg.gmail_imap_mailbox || 'INBOX',
        gmail_imap_target_email: cfg.gmail_imap_target_email || '',
        gmail_imap_target_domain: cfg.gmail_imap_target_domain || '',
        mailbox_otp_timeout_seconds: cfg.mailbox_otp_timeout_seconds || '',
        smstome_cookie: cfg.smstome_cookie || '',
        smstome_country_slugs: cfg.smstome_country_slugs || '',
        smstome_phone_attempts: cfg.smstome_phone_attempts || '',
        smstome_otp_timeout_seconds: cfg.smstome_otp_timeout_seconds || '',
        smstome_poll_interval_seconds: cfg.smstome_poll_interval_seconds || '',
        smstome_sync_max_pages_per_country: cfg.smstome_sync_max_pages_per_country || '',
        chatgpt_manual_browser_provider: 'camoufox',
        chatgpt_manual_handoff_timeout_seconds: cfg.chatgpt_manual_handoff_timeout_seconds || '900',
        chatgpt_manual_email_poll_interval_seconds: cfg.chatgpt_manual_email_poll_interval_seconds || '10',
        chatgpt_manual_enable_token_callback: parseBooleanConfigValue(cfg.chatgpt_manual_enable_token_callback),
        chatgpt_manual_browser_profile_dir: cfg.chatgpt_manual_browser_profile_dir || '',
        chatgpt_camoufox_geoip: parseBooleanConfigValue(cfg.chatgpt_camoufox_geoip),
        chatgpt_camoufox_humanize: cfg.chatgpt_camoufox_humanize || '',
        chatgpt_camoufox_os: cfg.chatgpt_camoufox_os || '',
        chatgpt_manual_browser_keep_open: parseBooleanConfigValue(cfg.chatgpt_manual_browser_keep_open),
        luckmail_base_url: cfg.luckmail_base_url || 'https://mails.luckyous.com/',
        luckmail_api_key: cfg.luckmail_api_key || '',
        luckmail_email_type: cfg.luckmail_email_type || '',
        luckmail_domain: cfg.luckmail_domain || '',
        // 自动上传配置
        cpa_api_url: cfg.cpa_api_url || '',
        cpa_api_key: cfg.cpa_api_key || '',
        sub2api_api_url: cfg.sub2api_api_url || '',
        sub2api_api_key: cfg.sub2api_api_key || '',
        sub2api_group_ids: cfg.sub2api_group_ids || '',
        codex_proxy_url: cfg.codex_proxy_url || '',
        codex_proxy_key: cfg.codex_proxy_key || '',
        codex_proxy_upload_type: cfg.codex_proxy_upload_type || 'at',
        team_manager_url: cfg.team_manager_url || '',
        team_manager_key: cfg.team_manager_key || '',
      })
    })
  }, [form])

  const submit = async () => {
    const values = await form.validateFields()
    const registerExtra = {
      mail_provider: values.mail_provider,
      laoudo_auth: values.laoudo_auth,
      laoudo_email: values.laoudo_email,
      laoudo_account_id: values.laoudo_account_id,
      gptmail_base_url: values.gptmail_base_url,
      gptmail_api_key: values.gptmail_api_key,
      gptmail_domain: values.gptmail_domain,
      opentrashmail_api_url: values.opentrashmail_api_url,
      opentrashmail_domain: values.opentrashmail_domain,
      opentrashmail_password: values.opentrashmail_password,
      maliapi_base_url: values.maliapi_base_url,
      maliapi_api_key: values.maliapi_api_key,
      maliapi_domain: values.maliapi_domain,
      maliapi_auto_domain_strategy: values.maliapi_auto_domain_strategy,
      moemail_api_url: values.moemail_api_url,
      moemail_api_key: values.moemail_api_key,
      skymail_api_base: values.skymail_api_base,
      skymail_token: values.skymail_token,
      skymail_domain: values.skymail_domain,
      duckmail_api_url: values.duckmail_api_url,
      duckmail_provider_url: values.duckmail_provider_url,
      duckmail_bearer: values.duckmail_bearer,
      freemail_api_url: values.freemail_api_url,
      freemail_admin_token: values.freemail_admin_token,
      freemail_username: values.freemail_username,
      freemail_password: values.freemail_password,
      cfworker_api_url: values.cfworker_api_url,
      cfworker_admin_token: values.cfworker_admin_token,
      cfworker_custom_auth: values.cfworker_custom_auth,
      cfworker_domain_override: values.cfworker_domain_override,
      cfworker_subdomain: values.cfworker_subdomain,
      cfworker_random_subdomain: values.cfworker_random_subdomain,
      cfworker_fingerprint: values.cfworker_fingerprint,
      gmail_imap_email: values.gmail_imap_email,
      gmail_imap_app_password: values.gmail_imap_app_password,
      gmail_imap_host: values.gmail_imap_host,
      gmail_imap_port: values.gmail_imap_port,
      gmail_imap_mailbox: values.gmail_imap_mailbox,
      gmail_imap_target_email: values.gmail_imap_target_email,
      gmail_imap_target_domain: values.gmail_imap_target_domain,
      mailbox_otp_timeout_seconds: values.mailbox_otp_timeout_seconds,
      smstome_cookie: values.smstome_cookie,
      smstome_country_slugs: values.smstome_country_slugs,
      smstome_phone_attempts: values.smstome_phone_attempts,
      smstome_otp_timeout_seconds: values.smstome_otp_timeout_seconds,
      smstome_poll_interval_seconds: values.smstome_poll_interval_seconds,
      smstome_sync_max_pages_per_country: values.smstome_sync_max_pages_per_country,
      chatgpt_manual_browser_provider: 'camoufox',
      chatgpt_manual_handoff_timeout_seconds: values.chatgpt_manual_handoff_timeout_seconds,
      chatgpt_manual_email_poll_interval_seconds: values.chatgpt_manual_email_poll_interval_seconds,
      chatgpt_manual_enable_token_callback: values.chatgpt_manual_enable_token_callback,
      chatgpt_manual_browser_profile_dir: values.chatgpt_manual_browser_profile_dir,
      chatgpt_camoufox_geoip: values.chatgpt_camoufox_geoip,
      chatgpt_camoufox_humanize: values.chatgpt_camoufox_humanize,
      chatgpt_camoufox_os: values.chatgpt_camoufox_os,
      chatgpt_manual_browser_keep_open: values.chatgpt_manual_browser_keep_open,
      luckmail_base_url: values.luckmail_base_url,
      luckmail_api_key: values.luckmail_api_key,
      luckmail_email_type: values.luckmail_email_type,
      luckmail_domain: values.luckmail_domain,
      yescaptcha_key: values.yescaptcha_key,
      solver_url: values.solver_url,
      // 自动上传配置
      cpa_api_url: values.cpa_api_url,
      cpa_api_key: values.cpa_api_key,
      sub2api_api_url: values.sub2api_api_url,
      sub2api_api_key: values.sub2api_api_key,
      sub2api_group_ids: values.sub2api_group_ids,
      codex_proxy_url: values.codex_proxy_url,
      codex_proxy_key: values.codex_proxy_key,
      codex_proxy_upload_type: values.codex_proxy_upload_type,
      team_manager_url: values.team_manager_url,
      team_manager_key: values.team_manager_key,
    }
    const chatgptRegistrationRequestAdapter =
      buildChatGPTRegistrationRequestAdapter(
        values.platform,
        chatgptRegistrationMode,
      )
    const adaptedRegisterExtra = chatgptRegistrationRequestAdapter
      ? chatgptRegistrationRequestAdapter.extendExtra(registerExtra)
      : registerExtra

    const res = await apiFetch('/tasks/register', {
      method: 'POST',
      body: JSON.stringify({
        platform: values.platform,
        email: values.email || null,
        password: values.password || null,
        count: values.count,
        concurrency: values.concurrency,
        register_delay_seconds: values.register_delay_seconds || 0,
        proxy: values.proxy || null,
        executor_type:
          values.platform === 'chatgpt' &&
          chatgptRegistrationMode === CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF
            ? 'protocol'
            : values.executor_type,
        captcha_solver: values.captcha_solver,
        extra: adaptedRegisterExtra,
      }),
    })
    setTask(res)
    setPolling(true)
    pollTask(res.task_id)
  }

  const pollTask = async (id: string) => {
    const interval = setInterval(async () => {
      const t = await apiFetch(`/tasks/${id}`)
      setTask(t)
      if (t.status === 'done' || t.status === 'failed' || t.status === 'stopped') {
        clearInterval(interval)
        setPolling(false)
        if (t.cashier_urls && t.cashier_urls.length > 0) {
          t.cashier_urls.forEach((url: string) => window.open(url, '_blank'))
        }
      }
    }, 2000)
  }

  const mailProvider = Form.useWatch('mail_provider', form)
  const captchaSolver = Form.useWatch('captcha_solver', form)
  const platform = Form.useWatch('platform', form)
  const manualTokenCallbackEnabled = parseBooleanConfigValue(
    Form.useWatch('chatgpt_manual_enable_token_callback', form),
  )
  const executorOptions = getExecutorOptions(platform)
  const isChatGPTManualHandoff =
    platform === 'chatgpt' &&
    chatgptRegistrationMode === CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF
  const showChatGPTUploadConfig =
    platform === 'chatgpt' && (!isChatGPTManualHandoff || manualTokenCallbackEnabled)

  useEffect(() => {
    if (isChatGPTManualHandoff) {
      form.setFieldValue('executor_type', 'protocol')
      return
    }
    const currentExecutor = form.getFieldValue('executor_type')
    const normalizedExecutor = normalizeExecutorForPlatform(platform, currentExecutor)
    if (currentExecutor !== normalizedExecutor) {
      form.setFieldValue('executor_type', normalizedExecutor)
    }
  }, [form, platform, isChatGPTManualHandoff])

  return (
    <div style={{ maxWidth: 800 }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 'bold', margin: 0 }}>注册任务</h1>
        <p style={{ color: '#7a8ba3', marginTop: 4 }}>创建账号自动注册任务</p>
      </div>

      <Form form={form} layout="vertical" onFinish={submit} initialValues={{
        platform: 'trae',
        executor_type: 'protocol',
        captcha_solver: 'yescaptcha',
        mail_provider: 'luckmail',
        gptmail_base_url: 'https://mail.chatgpt.org.uk',
        count: 1,
        concurrency: 1,
        register_delay_seconds: 0,
        maliapi_base_url: 'https://maliapi.215.im/v1',
        maliapi_auto_domain_strategy: 'balanced',
        solver_url: 'http://localhost:8889',
        chatgpt_manual_browser_provider: 'camoufox',
        chatgpt_manual_handoff_timeout_seconds: '900',
        chatgpt_manual_email_poll_interval_seconds: '10',
        chatgpt_manual_enable_token_callback: false,
        chatgpt_camoufox_geoip: false,
        chatgpt_camoufox_humanize: '',
        chatgpt_camoufox_os: '',
        chatgpt_manual_browser_keep_open: false,
      }}>
        <Card title="基本配置" style={{ marginBottom: 16 }}>
          <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'chatgpt', label: 'ChatGPT' },
                { value: 'trae', label: 'Trae.ai' },
                { value: 'cursor', label: 'Cursor' },
                { value: 'kiro', label: 'Kiro' },
                { value: 'grok', label: 'Grok' },
                { value: 'tavily', label: 'Tavily' },
                { value: 'openblocklabs', label: 'OpenBlockLabs' },
              ]}
            />
          </Form.Item>
          {isChatGPTManualHandoff ? (
            <>
              <Form.Item name="executor_type" hidden>
                <Input />
              </Form.Item>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="人工接管模式不使用执行器选择"
                description="该模式固定启动 Camoufox 打开普通 ChatGPT 入口并等待你手动完成注册；protocol/headless/headed 不会改变 Camoufox 的启动方式。"
              />
            </>
          ) : (
            <Form.Item name="executor_type" label="执行器" rules={[{ required: true }]}>
              <Select options={executorOptions} />
            </Form.Item>
          )}
          {platform === 'chatgpt' && !isChatGPTManualHandoff && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="ChatGPT 执行器说明"
              description="当前 ChatGPT refresh-token 注册主体仍是协议请求；有头/无头只影响 Sentinel Browser，不会复用你打开管理界面的浏览器环境。后台缺少 DISPLAY/WAYLAND_DISPLAY 时会强制 headless，并会在任务日志中写出实际模式。"
            />
          )}
          <Form.Item name="captcha_solver" label="验证码" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'yescaptcha', label: 'YesCaptcha' },
                { value: 'local_solver', label: '本地 Solver (Camoufox)' },
                { value: 'manual', label: '手动' },
              ]}
            />
          </Form.Item>
          <Space style={{ width: '100%' }}>
            <Form.Item name="count" label="批量数量" style={{ flex: 1 }}>
              <Input type="number" min={1} />
            </Form.Item>
            <Form.Item name="concurrency" label="并发数" style={{ flex: 1 }}>
              <Input type="number" min={1} max={5} />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }}>
            <Form.Item name="register_delay_seconds" label="每个注册延迟(秒)" style={{ flex: 1 }}>
              <InputNumber min={0} precision={1} step={0.5} style={{ width: '100%' }} placeholder="0" />
            </Form.Item>
            <Form.Item name="proxy" label="代理 (可选)" style={{ flex: 1 }}>
              <Input placeholder="http://user:pass@host:port" />
            </Form.Item>
          </Space>
          {platform === 'chatgpt' && (
            <Form.Item label="ChatGPT 注册模式">
              <ChatGPTRegistrationModeSwitch
                mode={chatgptRegistrationMode}
                onChange={setChatgptRegistrationMode}
              />
            </Form.Item>
          )}
          {platform === 'chatgpt' &&
            chatgptRegistrationMode === CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
                message="浏览器人工接管模式"
                description={
                  manualTokenCallbackEnabled
                    ? '系统先打开 Camoufox 普通 ChatGPT 注册入口；检测到你进入 ChatGPT 后，才会打开第二段 OAuth 授权页取 token。若进入 add-phone，会直接失败，不会自动处理手机号。'
                    : '系统只打开 Camoufox 普通 ChatGPT 注册入口；验证码、Cloudflare、手机号页都需要你本人处理。若进入 add-phone，会直接失败，不会自动处理手机号。当前只保存邮箱和密码，不自动取 token。'
                }
              />
            )}
        </Card>

        {platform === 'chatgpt' &&
          chatgptRegistrationMode === CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF && (
            <Card title="ChatGPT 浏览器人工接管" style={{ marginBottom: 16 }}>
              <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                使用本地 Camoufox 隔离有头浏览器。AutoReg 只负责打开普通 ChatGPT 入口、提示邮箱验证码并等待你完成注册；页面内操作由你手动完成。
              </Text>
              <Form.Item name="chatgpt_manual_browser_provider" hidden>
                <Input />
              </Form.Item>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="浏览器后端：Camoufox（免费本地）"
                description="如果留空 Profile 目录，后端会使用系统用户目录下的 AutoReg/manual_profiles/chatgpt_camoufox，不再写入项目目录。"
              />
              <Space style={{ width: '100%' }}>
                <Form.Item name="chatgpt_manual_handoff_timeout_seconds" label="人工接管等待秒数" style={{ flex: 1 }}>
                  <Input placeholder="900" />
                </Form.Item>
                <Form.Item name="chatgpt_manual_email_poll_interval_seconds" label="邮箱验证码提示间隔" style={{ flex: 1 }}>
                  <Input placeholder="10" />
                </Form.Item>
              </Space>
              <Form.Item
                name="chatgpt_manual_browser_profile_dir"
                label="Camoufox Profile 目录"
                extra="可留空，推荐使用后端默认的系统用户目录；只有需要固定/迁移 profile 时再填写绝对路径。"
              >
                <Input placeholder="/path/to/profile" />
              </Form.Item>
              <Space style={{ width: '100%' }}>
                <Form.Item name="chatgpt_camoufox_os" label="OS 指纹范围" style={{ flex: 1 }}>
                  <Select
                    options={[
                      { value: '', label: '自动生成' },
                      { value: 'macos', label: 'macOS' },
                      { value: 'windows', label: 'Windows' },
                      { value: 'linux', label: 'Linux' },
                    ]}
                  />
                </Form.Item>
                <Form.Item
                  name="chatgpt_camoufox_humanize"
                  label="Humanize 鼠标轨迹"
                  style={{ flex: 1 }}
                  extra="留空关闭；可填 true 或最大移动秒数，如 1.5。"
                >
                  <Input placeholder="true / 1.5" />
                </Form.Item>
              </Space>
              <Form.Item
                name="chatgpt_manual_enable_token_callback"
                label="第二段 OAuth/token 动作"
                valuePropName="checked"
                extra="默认关闭。开启后会在检测到普通注册完成后，继续打开 OAuth 授权页并等待 callback 取 token，随后才可自动上传到 token 平台。"
              >
                <Checkbox>注册完成后继续进入 OAuth callback 取 token</Checkbox>
              </Form.Item>
              {!manualTokenCallbackEnabled && (
                <Alert
                  type="success"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message="第二段动作已关闭"
                  description="当前任务只做普通注册并保存邮箱/密码，不会取 token，也不会自动上传到 CPA、Sub2API、CodexProxy 或 Team Manager。"
                />
              )}
              <Form.Item
                name="chatgpt_camoufox_geoip"
                label="GeoIP 跟随代理"
                valuePropName="checked"
                extra="需安装 camoufox[geoip]；未安装时后端会自动跳过并写日志。"
              >
                <Checkbox>根据代理 IP 匹配时区、语言和地理位置</Checkbox>
              </Form.Item>
              <Form.Item name="chatgpt_manual_browser_keep_open" label="任务结束后保留浏览器" valuePropName="checked">
                <Checkbox>保留窗口，便于继续查看现场</Checkbox>
              </Form.Item>
            </Card>
          )}

        <Card title="邮箱配置" style={{ marginBottom: 16 }}>
          <Form.Item name="mail_provider" label="邮箱服务" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'luckmail', label: 'LuckMail' },
                { value: 'moemail', label: 'MoeMail (sall.cc)' },
                { value: 'tempmail_lol', label: 'TempMail.lol' },
                { value: 'skymail', label: 'SkyMail (CloudMail)' },
                { value: 'maliapi', label: 'YYDS Mail / MaliAPI' },
                { value: 'gptmail', label: 'GPTMail' },
                { value: 'opentrashmail', label: 'OpenTrashMail' },
                { value: 'duckmail', label: 'DuckMail' },
                { value: 'freemail', label: 'Freemail' },
                { value: 'laoudo', label: 'Laoudo' },
                { value: 'cfworker', label: 'CF Worker' },
                { value: 'gmail_imap', label: 'Gmail IMAP' },
              ]}
            />
          </Form.Item>
          {mailProvider === 'skymail' && (
            <>
              <Form.Item name="skymail_api_base" label="API Base">
                <Input placeholder="https://api.skymail.ink" />
              </Form.Item>
              <Form.Item name="skymail_token" label="Authorization Token">
                <Input.Password placeholder="Bearer xxxxx" />
              </Form.Item>
              <Form.Item name="skymail_domain" label="邮箱域名">
                <Input placeholder="mail.example.com" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'laoudo' && (
            <>
              <Form.Item name="laoudo_email" label="邮箱地址">
                <Input placeholder="xxx@laoudo.com" />
              </Form.Item>
              <Form.Item name="laoudo_account_id" label="Account ID">
                <Input placeholder="563" />
              </Form.Item>
              <Form.Item name="laoudo_auth" label="JWT Token">
                <Input placeholder="eyJ..." />
              </Form.Item>
            </>
          )}
          {mailProvider === 'maliapi' && (
            <>
              <Form.Item name="maliapi_base_url" label="API URL">
                <Input placeholder="https://maliapi.215.im/v1" />
              </Form.Item>
              <Form.Item name="maliapi_api_key" label="API Key">
                <Input.Password placeholder="AC-..." />
              </Form.Item>
              <Form.Item name="maliapi_domain" label="邮箱域名（可选）">
                <Input placeholder="example.com" />
              </Form.Item>
              <Form.Item name="maliapi_auto_domain_strategy" label="自动域名策略">
                <Select
                  options={[
                    { value: 'balanced', label: 'balanced' },
                    { value: 'prefer_owned', label: 'prefer_owned' },
                    { value: 'prefer_public', label: 'prefer_public' },
                  ]}
                />
              </Form.Item>
            </>
          )}
          {mailProvider === 'gptmail' && (
            <>
              <Form.Item name="gptmail_base_url" label="API URL">
                <Input placeholder="https://mail.chatgpt.org.uk" />
              </Form.Item>
              <Form.Item name="gptmail_api_key" label="API Key">
                <Input.Password placeholder="gpt-test" />
              </Form.Item>
              <Form.Item
                name="gptmail_domain"
                label="邮箱域名（可选）"
                extra="已知当前可用域名时可直接本地拼装随机地址，省掉一次 generate-email 请求"
              >
                <Input placeholder="example.com" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'opentrashmail' && (
            <>
              <Form.Item name="opentrashmail_api_url" label="API URL" rules={[{ required: true, message: '请输入 OpenTrashMail 地址' }]}>
                <Input placeholder="http://mail.example.com:8085" />
              </Form.Item>
              <Form.Item
                name="opentrashmail_domain"
                label="邮箱域名（可选）"
                extra="已知 OpenTrashMail 当前启用域名时可直接本地拼装随机地址；留空则调用 /api/random 自动获取"
              >
                <Input placeholder="xiyoufm.com" />
              </Form.Item>
              <Form.Item
                name="opentrashmail_password"
                label="站点密码（可选）"
                extra="当 OpenTrashMail 开启 PASSWORD 保护时填写，会自动追加到 JSON API 查询参数"
              >
                <Input.Password placeholder="留空表示未启用" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'cfworker' && (
            <>
              <Form.Item name="cfworker_api_url" label="API URL">
                <Input placeholder="https://apimail.example.com" />
              </Form.Item>
              <Form.Item name="cfworker_admin_token" label="Admin Token">
                <Input placeholder="abc123,,,abc" />
              </Form.Item>
              <Form.Item name="cfworker_custom_auth" label="Site Password">
                <Input.Password placeholder="private site password" />
              </Form.Item>
              <Form.Item
                name="cfworker_domain_override"
                label="单次任务指定域名（可选）"
                extra="留空时将从设置页已启用的域名列表中随机选择。"
              >
                <Input placeholder="example.com" />
              </Form.Item>
              <Form.Item
                name="cfworker_subdomain"
                label="子域名（可选）"
                extra="填写后将生成 xxx@子域名.根域名；若启用随机子域名，则会生成 xxx@随机值.子域名.根域名。"
              >
                <Input placeholder="mail / pool-a" />
              </Form.Item>
              <Form.Item name="cfworker_random_subdomain" label="随机子域名" valuePropName="checked">
                <Checkbox>每次注册前随机生成一层子域名</Checkbox>
              </Form.Item>
              <Form.Item name="cfworker_fingerprint" label="Fingerprint (可选)">
                <Input placeholder="cfb82279f..." />
              </Form.Item>
            </>
          )}
          {mailProvider === 'gmail_imap' && (
            <>
              <Form.Item name="gmail_imap_email" label="Gmail 登录邮箱" rules={[{ required: true, message: '请输入 Gmail 登录邮箱' }]}>
                <Input placeholder="your@gmail.com" />
              </Form.Item>
              <Form.Item name="gmail_imap_app_password" label="Gmail App Password" rules={[{ required: true, message: '请输入 Gmail 应用专用密码' }]}>
                <Input.Password placeholder="需要开启两步验证后创建应用专用密码" />
              </Form.Item>
              <Form.Item name="gmail_imap_host" label="IMAP Host">
                <Input placeholder="imap.gmail.com" />
              </Form.Item>
              <Form.Item name="gmail_imap_port" label="IMAP Port">
                <Input placeholder="993" />
              </Form.Item>
              <Form.Item
                name="gmail_imap_mailbox"
                label="邮箱目录"
                extra="可用英文逗号分隔多个 IMAP 目录；Gmail 默认会补扫 Junk/Trash 和 [Gmail]/Spam/[Gmail]/Trash。"
              >
                <Input placeholder="INBOX,Junk,Trash" />
              </Form.Item>
              <Form.Item
                name="mailbox_otp_timeout_seconds"
                label="邮箱验证码等待秒数"
                extra="默认 120 秒；网络或 IMAP 不稳定时可适当调大，不再固定等待 700 秒。"
              >
                <Input placeholder="120" />
              </Form.Item>
              <Form.Item
                name="gmail_imap_target_email"
                label="固定注册邮箱（可选）"
                extra="填写后每次都使用这个邮箱注册，例如 jgbbpro@example.com。"
              >
                <Input placeholder="jgbbpro@example.com" />
              </Form.Item>
              <Form.Item
                name="gmail_imap_target_domain"
                label="Catch-all 域名（可选）"
                extra="留空且未填固定注册邮箱时，会直接使用 Gmail 登录邮箱；填写后每次生成随机地址 @该域名，并从 Gmail 收件箱读取转发邮件。"
              >
                <Input placeholder="example.com" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'luckmail' && (
            <>
              <Form.Item name="luckmail_base_url" label="平台地址">
                <Input placeholder="https://mails.luckyous.com" />
              </Form.Item>
              <Form.Item name="luckmail_api_key" label="API Key">
                <Input.Password placeholder="ak_..." />
              </Form.Item>
              <Form.Item name="luckmail_email_type" label="邮箱类型（可选）">
                <Input placeholder="ms_graph / ms_imap" />
              </Form.Item>
              <Form.Item name="luckmail_domain" label="邮箱域名（可选）">
                <Input placeholder="outlook.com" />
              </Form.Item>
            </>
          )}
        </Card>

        {platform === 'chatgpt' && !isChatGPTManualHandoff && (
          <Card title="ChatGPT 手机验证" style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
              仅在 OAuth 流程进入 `add_phone` 时使用，用于自动取号并轮询短信验证码。
            </Text>
            <Form.Item name="smstome_cookie" label="SMSToMe Cookie">
              <Input.Password placeholder="cf_clearance=...; PHPSESSID=..." />
            </Form.Item>
            <Form.Item name="smstome_country_slugs" label="国家列表">
              <Input placeholder="united-kingdom,poland,finland" />
            </Form.Item>
            <Form.Item name="smstome_phone_attempts" label="手机号尝试次数">
              <Input placeholder="3" />
            </Form.Item>
            <Form.Item name="smstome_otp_timeout_seconds" label="短信等待秒数">
              <Input placeholder="45" />
            </Form.Item>
            <Form.Item name="smstome_poll_interval_seconds" label="轮询间隔秒数">
              <Input placeholder="5" />
            </Form.Item>
            <Form.Item name="smstome_sync_max_pages_per_country" label="每国同步页数">
              <Input placeholder="5" />
            </Form.Item>
          </Card>
        )}

        {showChatGPTUploadConfig && (
          <Card title="自动上传配置" style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
              注册成功后自动上传到外部管理平台（留空则不上传）
            </Text>

            <Form.Item name="cpa_api_url" label="CPA API URL">
              <Input placeholder="https://your-cpa.example.com" />
            </Form.Item>
            <Form.Item name="cpa_api_key" label="CPA API Key">
              <Input.Password placeholder="Bearer token" />
            </Form.Item>

            <Form.Item name="sub2api_api_url" label="Sub2API API URL">
              <Input placeholder="https://your-sub2api.example.com" />
            </Form.Item>
            <Form.Item name="sub2api_api_key" label="Sub2API API Key">
              <Input.Password placeholder="API Key" />
            </Form.Item>
            <Form.Item name="sub2api_group_ids" label="Sub2API 分组 ID">
              <Input placeholder="多个分组用逗号分隔，例如 2,4,8" />
            </Form.Item>

            <Form.Item name="codex_proxy_url" label="CodexProxy API URL">
              <Input placeholder="https://your-codex-proxy.example.com" />
            </Form.Item>
            <Form.Item name="codex_proxy_key" label="CodexProxy Admin Key">
              <Input.Password placeholder="Admin Key" />
            </Form.Item>
            <Form.Item name="codex_proxy_upload_type" label="CodexProxy 上传类型">
              <Select
                options={[
                  { value: 'at', label: 'AT (Access Token, 推荐)' },
                  { value: 'rt', label: 'RT (Refresh Token)' },
                ]}
              />
            </Form.Item>

            <Form.Item name="team_manager_url" label="Team Manager API URL">
              <Input placeholder="https://your-tm.example.com" />
            </Form.Item>
            <Form.Item name="team_manager_key" label="Team Manager API Key">
              <Input.Password placeholder="API Key" />
            </Form.Item>
          </Card>
        )}

        {captchaSolver === 'yescaptcha' && (
          <Card title="验证码配置" style={{ marginBottom: 16 }}>
            <Form.Item name="yescaptcha_key" label="YesCaptcha Key">
              <Input />
            </Form.Item>
          </Card>
        )}

        {captchaSolver === 'local_solver' && (
          <Card title="本地 Solver 配置" style={{ marginBottom: 16 }}>
            <Form.Item name="solver_url" label="Solver URL">
              <Input />
            </Form.Item>
            <Text type="secondary" style={{ fontSize: 12 }}>
              启动命令: python services/turnstile_solver/start.py --browser_type camoufox --port 8889
            </Text>
          </Card>
        )}

        <Button type="primary" htmlType="submit" block disabled={polling} icon={polling ? <LoadingOutlined /> : <PlayCircleOutlined />}>
          {polling ? '注册中...' : '开始注册'}
        </Button>
      </Form>

      {task && (
        <Card title={
          <Space>
            <span>任务状态</span>
            <Tag color={
              task.status === 'done' ? 'success' :
              task.status === 'stopped' ? 'warning' :
              task.status === 'failed' ? 'error' : 'processing'
            }>
              {task.status}
            </Tag>
          </Space>
        } style={{ marginTop: 16 }}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="任务 ID">
              <Text copyable style={{ fontFamily: 'monospace' }}>{task.id}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="进度">{task.progress}</Descriptions.Item>
            <Descriptions.Item label="跳过">{task.skipped ?? 0}</Descriptions.Item>
          </Descriptions>
          {task.success != null && (
            <div style={{ marginTop: 8, color: '#10b981' }}>
              <CheckCircleOutlined /> 成功 {task.success} 个
            </div>
          )}
          {task.errors?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              {task.errors.map((e: string, i: number) => (
                <div key={i} style={{ color: '#ef4444', marginBottom: 4 }}>
                  <CloseCircleOutlined /> {e}
                </div>
              ))}
            </div>
          )}
          {task.error && (
            <div style={{ marginTop: 8, color: '#ef4444' }}>
              <CloseCircleOutlined /> {task.error}
            </div>
          )}
          {task.id ? (
            <div style={{ marginTop: 16 }}>
              <TaskLogPanel taskId={task.id} />
            </div>
          ) : null}
        </Card>
      )}
    </div>
  )
}
