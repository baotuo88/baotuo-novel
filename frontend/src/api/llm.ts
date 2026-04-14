// AIMETA P=LLM_API客户端_模型配置接口|R=LLM配置CRUD|NR=不含UI逻辑|E=api:llm|X=internal|A=llmApi对象|D=axios|S=net|RD=./README.ai
import { useAuthStore } from '@/stores/auth';

const API_PREFIX = '/api';
const LLM_BASE = `${API_PREFIX}/llm-config`;

export interface LLMConfig {
  user_id: number;
  llm_provider_url: string | null;
  llm_provider_api_key: string | null;
  llm_provider_model: string | null;
}

export interface LLMConfigCreate {
  llm_provider_url?: string;
  llm_provider_api_key?: string;
  llm_provider_model?: string;
}

const getHeaders = () => {
  const authStore = useAuthStore();
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${authStore.token}`,
  };
};

export const getLLMConfig = async (): Promise<LLMConfig | null> => {
  const response = await fetch(LLM_BASE, {
    method: 'GET',
    headers: getHeaders(),
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error('Failed to fetch LLM config');
  }
  return response.json();
};

export const createOrUpdateLLMConfig = async (config: LLMConfigCreate): Promise<LLMConfig> => {
  const response = await fetch(LLM_BASE, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    throw new Error('Failed to save LLM config');
  }
  return response.json();
};

export const deleteLLMConfig = async (): Promise<void> => {
  const response = await fetch(LLM_BASE, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  if (!response.ok) {
    throw new Error('Failed to delete LLM config');
  }
};

export interface ModelListRequest {
  llm_provider_url?: string;
  llm_provider_api_key: string;
}

export const getAvailableModels = async (request: ModelListRequest): Promise<string[]> => {
  const response = await fetch(`${LLM_BASE}/models`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    // 获取模型列表失败时返回空数组，不影响主流程
    return [];
  }
  return response.json();
};

export interface LLMConnectionTestRequest {
  llm_provider_url?: string;
  llm_provider_api_key: string;
  llm_provider_model?: string;
}

export interface LLMConnectionTestResult {
  success: boolean;
  provider: string;
  message: string;
  latency_ms?: number | null;
  model_count: number;
  sample_models: string[];
}

export interface UserSubscriptionStatus {
  user_id: number;
  plan_name: string;
  status: string;
  starts_at?: string | null;
  expires_at?: string | null;
  is_active: boolean;
}

export interface UserSubscriptionUsageSummary {
  user_id: number;
  plan_name: string;
  status: string;
  is_active: boolean;
  daily_request_used: number;
  daily_request_limit: number;
  daily_request_ratio: number;
  today_estimated_cost_usd: number;
  daily_budget_limit_usd: number;
  daily_budget_ratio: number;
  warning_level: 'ok' | 'warning' | 'critical' | 'exceeded' | string;
}

export interface UserSubscriptionBillingItem {
  id: number;
  created_at: string;
  project_id?: string | null;
  request_type: string;
  model?: string | null;
  status: string;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_cost_usd: number;
  latency_ms?: number | null;
}

export interface UserSubscriptionBillingSummary {
  user_id: number;
  hours: number;
  total_calls: number;
  success_calls: number;
  total_estimated_cost_usd: number;
  items: UserSubscriptionBillingItem[];
}

export const getMySubscriptionStatus = async (): Promise<UserSubscriptionStatus> => {
  const response = await fetch('/api/auth/subscription', {
    method: 'GET',
    headers: getHeaders(),
  });
  if (!response.ok) {
    throw new Error('获取订阅状态失败');
  }
  return response.json();
};

export const getMySubscriptionUsageSummary = async (): Promise<UserSubscriptionUsageSummary> => {
  const response = await fetch('/api/auth/subscription/usage-summary', {
    method: 'GET',
    headers: getHeaders(),
  });
  if (!response.ok) {
    throw new Error('获取订阅额度摘要失败');
  }
  return response.json();
};

export const getMySubscriptionBilling = async (params: {
  hours?: number;
  limit?: number;
} = {}): Promise<UserSubscriptionBillingSummary> => {
  const query = new URLSearchParams();
  if (params.hours != null) query.set('hours', String(params.hours));
  if (params.limit != null) query.set('limit', String(params.limit));
  const qs = query.toString();
  const response = await fetch(`/api/auth/subscription/billing${qs ? `?${qs}` : ''}`, {
    method: 'GET',
    headers: getHeaders(),
  });
  if (!response.ok) {
    throw new Error('获取订阅账单明细失败');
  }
  return response.json();
};

export const testLLMConnection = async (
  request: LLMConnectionTestRequest
): Promise<LLMConnectionTestResult> => {
  const response = await fetch(`${LLM_BASE}/test-connection`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error('LLM 连接测试失败');
  }
  return response.json();
};
