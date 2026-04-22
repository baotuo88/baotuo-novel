// AIMETA P=LLM_API客户端_模型配置接口|R=LLM配置CRUD|NR=不含UI逻辑|E=api:llm|X=internal|A=llmApi对象|D=axios|S=net|RD=./README.ai
import router from '@/router'
import { useAuthStore } from '@/stores/auth';
import { httpRequest, downloadFile } from './http'

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

const clientRequest = <T>(url: string, options: RequestInit = {}) => {
  const authStore = useAuthStore()
  return httpRequest<T>(url, {
    ...options,
    token: authStore.token,
    onUnauthorized: async () => {
      authStore.logout()
      await router.push('/login')
    }
  })
}

export const getLLMConfig = async (): Promise<LLMConfig | null> => {
  try {
    return await clientRequest<LLMConfig>(LLM_BASE, { method: 'GET' })
  } catch (error) {
    if ((error as Error).message.includes('状态码: 404')) {
      return null
    }
    throw error
  }
};

export const createOrUpdateLLMConfig = async (config: LLMConfigCreate): Promise<LLMConfig> => {
  return clientRequest<LLMConfig>(LLM_BASE, {
    method: 'PUT',
    body: JSON.stringify(config),
  })
};

export const deleteLLMConfig = async (): Promise<void> => {
  await clientRequest<void>(LLM_BASE, { method: 'DELETE' })
};

export interface ModelListRequest {
  llm_provider_url?: string;
  llm_provider_api_key: string;
}

export const getAvailableModels = async (request: ModelListRequest): Promise<string[]> => {
  try {
    return await clientRequest<string[]>(`${LLM_BASE}/models`, {
      method: 'POST',
      body: JSON.stringify(request),
    })
  } catch {
    // 获取模型列表失败时返回空数组，不影响主流程
    return [];
  }
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
  daily_request_remaining: number;
  daily_request_ratio: number;
  today_estimated_cost_usd: number;
  daily_budget_limit_usd: number;
  daily_budget_remaining_usd: number;
  daily_budget_ratio: number;
  reset_at: string;
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
  return clientRequest<UserSubscriptionStatus>('/api/auth/subscription', { method: 'GET' })
};

export const getMySubscriptionUsageSummary = async (): Promise<UserSubscriptionUsageSummary> => {
  return clientRequest<UserSubscriptionUsageSummary>('/api/auth/subscription/usage-summary', { method: 'GET' })
};

export const getMySubscriptionBilling = async (params: {
  hours?: number;
  limit?: number;
} = {}): Promise<UserSubscriptionBillingSummary> => {
  const query = new URLSearchParams();
  if (params.hours != null) query.set('hours', String(params.hours));
  if (params.limit != null) query.set('limit', String(params.limit));
  const qs = query.toString();
  return clientRequest<UserSubscriptionBillingSummary>(`/api/auth/subscription/billing${qs ? `?${qs}` : ''}`, {
    method: 'GET',
  })
};

export const downloadMySubscriptionBillingCsv = async (params: {
  hours?: number;
  limit?: number;
} = {}): Promise<void> => {
  const authStore = useAuthStore()
  const query = new URLSearchParams();
  if (params.hours != null) query.set('hours', String(params.hours));
  if (params.limit != null) query.set('limit', String(params.limit));
  const qs = query.toString();
  await downloadFile(`/api/auth/subscription/billing/export.csv${qs ? `?${qs}` : ''}`, {
    method: 'GET',
    token: authStore.token,
    onUnauthorized: async () => {
      authStore.logout()
      await router.push('/login')
    },
    fallbackName: `subscription_billing_${Date.now()}.csv`,
  })
};

export const testLLMConnection = async (
  payload: LLMConnectionTestRequest
): Promise<LLMConnectionTestResult> => {
  return clientRequest<LLMConnectionTestResult>(`${LLM_BASE}/test-connection`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
};
