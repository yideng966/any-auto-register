import { Radio, Space, Tag, Typography } from 'antd'

import {
  CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
  CHATGPT_REGISTRATION_MODE_HAIGE,
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
  const options = [
    {
      value: CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
      label: '默认 RT',
      tagColor: 'success',
      tagText: '默认推荐',
      description:
        '走默认 RT 链路，产出 Access Token + Refresh Token，兼容当前既有流程。',
    },
    {
      value: CHATGPT_REGISTRATION_MODE_HAIGE,
      label: '海哥模式',
      tagColor: 'processing',
      tagText: 'PKCE',
      description:
        '走 auth.openai.com OAuth PKCE 注册链路，产出 Access Token + Refresh Token。',
    },
    {
      value: CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
      label: '无 RT',
      tagColor: 'default',
      tagText: '兼容旧方案',
      description:
        '走旧链路，只产出 Access Token / Session，依赖 Refresh Token 的能力不可用。',
    },
  ] as const

  const currentOption =
    options.find((option) => option.value === mode) ?? options[0]

  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Space align="center" wrap>
        <Radio.Group
          optionType="button"
          buttonStyle="solid"
          value={mode}
          onChange={(event) =>
            onChange(event.target.value as ChatGPTRegistrationMode)
          }
          options={options.map(({ value, label }) => ({ value, label }))}
        />
        <Tag color={currentOption.tagColor}>{currentOption.tagText}</Tag>
      </Space>
      <Text type="secondary">{currentOption.description}</Text>
      {mode === CHATGPT_REGISTRATION_MODE_HAIGE && (
        <Text type="secondary">
          需要后端已集成海哥模式引擎；当前仓库后端已支持。
        </Text>
      )}
      {mode === CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN && (
        <Text type="secondary">
          适合保持现有默认行为，优先兼容现有注册与后续 RT 相关能力。
        </Text>
      )}
      {mode === CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY && (
        <Text type="secondary">
          仅在你明确不需要 Refresh Token 能力时使用。
        </Text>
      )}
    </Space>
  )
}
