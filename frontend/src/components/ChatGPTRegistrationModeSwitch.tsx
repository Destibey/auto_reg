import { Segmented, Space, Tag, Typography } from 'antd'

import {
  CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
  CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF,
  CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
  type ChatGPTRegistrationMode,
} from '@/lib/chatgptRegistrationMode'

const { Text } = Typography

type ChatGPTRegistrationModeSwitchProps = {
  mode: ChatGPTRegistrationMode
  onChange: (mode: ChatGPTRegistrationMode) => void
}

export function ChatGPTRegistrationModeSwitch({
  mode,
  onChange,
}: ChatGPTRegistrationModeSwitchProps) {
  const modeMeta = {
    [CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN]: {
      tag: '默认推荐',
      color: 'success',
      desc: '协议注册链路会走协议请求 + Sentinel Browser，只完成注册并保存邮箱/密码；Token 请在账号管理页手动取Token。',
    },
    [CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY]: {
      tag: '兼容旧方案',
      color: 'default',
      desc: '旧协议链路同样只完成注册并保存邮箱/密码，不在注册任务内读取 Session 或 Access Token。',
    },
    [CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF]: {
      tag: '人工接管',
      color: 'processing',
      desc: '浏览器人工接管会固定打开 Camoufox ChatGPT 直接注册页，等待你手动完成注册；当前只保存邮箱和密码，不自动取 token。',
    },
  }[mode]

  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Space align="center" wrap>
        <Segmented
          value={mode}
          onChange={(value) => onChange(value as ChatGPTRegistrationMode)}
          options={[
            { label: '协议注册', value: CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN },
            { label: '旧协议注册', value: CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY },
            {
              label: '浏览器接管',
              value: CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF,
            },
          ]}
        />
        <Tag color={modeMeta.color}>{modeMeta.tag}</Tag>
      </Space>
      <Text type="secondary">{modeMeta.desc}</Text>
    </Space>
  )
}
