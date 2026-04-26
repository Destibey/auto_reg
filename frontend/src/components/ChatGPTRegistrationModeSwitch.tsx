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
      desc: '有 RT 方案会走协议请求 + Sentinel Browser，产出 Access Token + Refresh Token。',
    },
    [CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY]: {
      tag: '兼容旧方案',
      color: 'default',
      desc: '无 RT 方案会走旧协议链路，只产出 Access Token / Session，依赖 RT 的能力可能不可用。',
    },
    [CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF]: {
      tag: '人工接管',
      color: 'processing',
      desc: '浏览器人工接管会打开隔离有头浏览器，等待你手动完成注册/OAuth，再从 callback 提取 token。',
    },
  }[mode]

  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Space align="center" wrap>
        <Segmented
          value={mode}
          onChange={(value) => onChange(value as ChatGPTRegistrationMode)}
          options={[
            { label: '有 RT', value: CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN },
            { label: '无 RT', value: CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY },
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
