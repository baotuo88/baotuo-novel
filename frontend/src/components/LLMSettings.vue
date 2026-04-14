<!-- AIMETA P=LLM设置_模型配置界面|R=LLM配置表单|NR=不含模型调用|E=component:LLMSettings|X=internal|A=设置组件|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="bg-white/70 backdrop-blur-xl rounded-2xl shadow-lg p-8">
    <h2 class="text-2xl font-bold text-gray-800 mb-6">LLM 配置</h2>
    <h5 class="text-1xl font-bold text-gray-800 mb-6">建议使用自己的中转API和KEY</h5>
    <div
      class="mb-6 rounded-lg border px-4 py-3 text-sm"
      :class="subscriptionCardClass"
    >
      <div class="font-semibold">{{ subscriptionTitle }}</div>
      <div class="mt-1 opacity-90">{{ subscriptionDetail }}</div>
      <div v-if="usingCustomKey" class="mt-2 text-emerald-700">
        当前已填写自定义 API Key，调用时优先使用你的自定义 Key。
      </div>
    </div>

    <div class="mb-6 rounded-lg border px-4 py-3 text-sm bg-slate-50 border-slate-200 text-slate-700">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div class="font-semibold">订阅额度与账单</div>
        <button
          type="button"
          class="px-3 py-1.5 rounded-md border border-slate-300 hover:bg-slate-100"
          :disabled="billingLoading"
          @click="loadSubscriptionMetrics"
        >
          {{ billingLoading ? '刷新中...' : '刷新' }}
        </button>
      </div>

      <div v-if="subscriptionUsage" class="mt-3 space-y-2">
        <div>
          请求额度：{{ subscriptionUsage.daily_request_used }} / {{ subscriptionUsage.daily_request_limit }}
          <span class="ml-2">({{ Math.round(subscriptionUsage.daily_request_ratio * 100) }}%)</span>
        </div>
        <div>
          预算额度：$ {{ subscriptionUsage.today_estimated_cost_usd.toFixed(4) }}
          / $ {{ subscriptionUsage.daily_budget_limit_usd.toFixed(4) }}
          <span class="ml-2">({{ Math.round(subscriptionUsage.daily_budget_ratio * 100) }}%)</span>
        </div>
        <div>
          预警等级：
          <span :class="usageWarningClass">{{ subscriptionUsage.warning_level }}</span>
        </div>
      </div>
      <div v-else-if="subscriptionUsageError" class="mt-3 text-rose-600">
        {{ subscriptionUsageError }}
      </div>

      <div v-if="subscriptionBilling?.items?.length" class="mt-4">
        <div class="font-medium mb-2">
          最近 {{ subscriptionBilling.hours }} 小时账单（{{ subscriptionBilling.total_calls }} 次调用）
        </div>
        <div class="max-h-52 overflow-auto border border-slate-200 rounded-md bg-white">
          <table class="w-full text-xs">
            <thead class="sticky top-0 bg-slate-100 text-slate-600">
              <tr>
                <th class="px-2 py-1 text-left">时间</th>
                <th class="px-2 py-1 text-left">类型</th>
                <th class="px-2 py-1 text-left">模型</th>
                <th class="px-2 py-1 text-left">状态</th>
                <th class="px-2 py-1 text-right">费用(USD)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in subscriptionBilling.items" :key="item.id" class="border-t border-slate-100">
                <td class="px-2 py-1">{{ formatDateTime(item.created_at) }}</td>
                <td class="px-2 py-1">{{ item.request_type }}</td>
                <td class="px-2 py-1">{{ item.model || '-' }}</td>
                <td class="px-2 py-1">{{ item.status }}</td>
                <td class="px-2 py-1 text-right">{{ item.estimated_cost_usd.toFixed(6) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="mt-2 text-xs text-slate-500">
          合计费用：$ {{ subscriptionBilling.total_estimated_cost_usd.toFixed(6) }}
        </div>
      </div>
      <div v-else-if="subscriptionBillingError" class="mt-3 text-rose-600">
        {{ subscriptionBillingError }}
      </div>
    </div>
    <form @submit.prevent="handleSave" class="space-y-6">
      <div>
        <label for="url" class="block text-sm font-medium text-gray-700">API URL</label>
        <div class="relative mt-1">
          <input
            type="text"
            id="url"
            v-model="config.llm_provider_url"
            class="block w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
            placeholder="https://api.example.com/v1"
          >
          <button
            type="button"
            @click="clearApiUrl"
            class="absolute inset-y-0 right-2 flex items-center px-2 text-gray-400 hover:text-gray-600"
            aria-label="清空 API URL"
          >
            <svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>
      </div>
      <div>
        <label for="key" class="block text-sm font-medium text-gray-700">API Key</label>
        <div class="relative mt-1">
          <input
            :type="showApiKey ? 'text' : 'password'"
            id="key"
            v-model="config.llm_provider_api_key"
            class="block w-full px-3 py-2 pr-24 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
            placeholder="留空则使用默认Key"
          >
          <button
            type="button"
            @click="clearApiKey"
            class="absolute inset-y-0 right-2 flex items-center px-2 text-gray-400 hover:text-gray-600"
            aria-label="清空 API Key"
          >
            <svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
            </svg>
          </button>
          <button
            type="button"
            @click="toggleApiKeyVisibility"
            class="absolute inset-y-0 right-10 flex items-center px-2 text-gray-400 hover:text-gray-600"
            :aria-label="showApiKey ? '隐藏 API Key' : '显示 API Key'"
          >
            <svg v-if="showApiKey" class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10 5c-4.478 0-8.268 2.943-9.542 7C1.732 16.057 5.522 19 10 19s8.268-2.943 9.542-7C18.268 7.943 14.478 5 10 5zm0 10a5 5 0 110-10 5 5 0 010 10z" fill-opacity="0.2" />
              <path d="M10 7a3 3 0 100 6 3 3 0 000-6z" />
            </svg>
            <svg v-else class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zm13.707 0a4.167 4.167 0 11-8.334 0 4.167 4.167 0 018.334 0z" clip-rule="evenodd" />
              <path d="M10 8a2 2 0 100 4 2 2 0 000-4z" />
            </svg>
          </button>
        </div>
      </div>
      <div>
        <label for="model" class="block text-sm font-medium text-gray-700">Model</label>
        <div class="flex gap-2 mt-1">
          <div class="relative flex-1">
            <input
              type="text"
              id="model"
              v-model="config.llm_provider_model"
              @focus="showModelDropdown = true"
              @blur="hideDropdown"
              class="block w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              placeholder="留空则使用默认模型"
            >
            <button
              type="button"
              @click="clearApiModel"
              class="absolute inset-y-0 right-2 flex items-center px-2 text-gray-400 hover:text-gray-600"
              aria-label="清空模型名称"
            >
              <svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
              </svg>
            </button>
            <!-- 下拉选择提示框 -->
            <div
              v-if="showModelDropdown && availableModels.length > 0"
              class="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-auto"
            >
              <div
                v-for="model in filteredModels"
                :key="model"
                @mousedown="selectModel(model)"
                class="px-3 py-2 cursor-pointer hover:bg-indigo-50 hover:text-indigo-600 text-sm"
              >
                {{ model }}
              </div>
              <div v-if="filteredModels.length === 0" class="px-3 py-2 text-sm text-gray-500">
                无匹配的模型
              </div>
            </div>
          </div>
          <div class="flex gap-2">
            <button
              type="button"
              @click="loadModels"
              :disabled="isLoadingModels"
              class="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <svg v-if="isLoadingModels" class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span>{{ isLoadingModels ? '加载中...' : '获取模型' }}</span>
            </button>
            <button
              type="button"
              @click="runConnectionTest"
              :disabled="isTestingConnection"
              class="px-4 py-2 bg-emerald-600 text-white rounded-md hover:bg-emerald-700 transition-colors disabled:bg-emerald-300 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <svg v-if="isTestingConnection" class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span>{{ isTestingConnection ? '测试中...' : '测试连接' }}</span>
            </button>
          </div>
        </div>
        <div
          v-if="connectionResult"
          class="mt-3 rounded-md px-3 py-2 text-sm border"
          :class="connectionResult.success ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-rose-50 border-rose-200 text-rose-700'"
        >
          <div class="font-medium">{{ connectionResult.message }}</div>
          <div class="mt-1 opacity-90">
            提供商：{{ connectionResult.provider }}
            <span v-if="connectionResult.latency_ms != null"> · 延迟：{{ connectionResult.latency_ms }}ms</span>
            <span> · 模型数：{{ connectionResult.model_count }}</span>
          </div>
          <div v-if="connectionResult.sample_models.length" class="mt-1 truncate">
            示例模型：{{ connectionResult.sample_models.slice(0, 3).join('、') }}
          </div>
        </div>
      </div>
      <div class="flex justify-end space-x-4 pt-4">
        <button type="button" @click="handleDelete" class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors">删除配置</button>
        <button type="submit" class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">保存</button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import {
  getLLMConfig,
  createOrUpdateLLMConfig,
  deleteLLMConfig,
  getAvailableModels,
  getMySubscriptionBilling,
  getMySubscriptionStatus,
  getMySubscriptionUsageSummary,
  testLLMConnection,
  type LLMConfigCreate,
  type LLMConnectionTestResult,
  type UserSubscriptionBillingSummary,
  type UserSubscriptionStatus,
  type UserSubscriptionUsageSummary,
} from '@/api/llm';

const config = ref<LLMConfigCreate>({
  llm_provider_url: '',
  llm_provider_api_key: '',
  llm_provider_model: '',
});

const showApiKey = ref(false);
const availableModels = ref<string[]>([]);
const isLoadingModels = ref(false);
const showModelDropdown = ref(false);
const isTestingConnection = ref(false);
const connectionResult = ref<LLMConnectionTestResult | null>(null);
const subscriptionStatus = ref<UserSubscriptionStatus | null>(null);
const subscriptionStatusError = ref('');
const subscriptionUsage = ref<UserSubscriptionUsageSummary | null>(null);
const subscriptionUsageError = ref('');
const subscriptionBilling = ref<UserSubscriptionBillingSummary | null>(null);
const subscriptionBillingError = ref('');
const billingLoading = ref(false);

// 根据输入过滤模型列表
const filteredModels = computed(() => {
  if (!config.value.llm_provider_model) {
    return availableModels.value;
  }
  const searchTerm = config.value.llm_provider_model.toLowerCase();
  return availableModels.value.filter(model =>
    model.toLowerCase().includes(searchTerm)
  );
});

const usingCustomKey = computed(() => Boolean(config.value.llm_provider_api_key?.trim()));

const formatDateTime = (value?: string | null): string => {
  if (!value) return '未设置';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未设置';
  return date.toLocaleString('zh-CN', { hour12: false });
};

const subscriptionTitle = computed(() => {
  if (subscriptionStatusError.value) return '订阅状态读取失败';
  if (!subscriptionStatus.value) return '订阅状态加载中';
  if (subscriptionStatus.value.is_active) {
    return `系统 Key 订阅有效（${subscriptionStatus.value.plan_name}）`;
  }
  return `系统 Key 订阅未生效（${subscriptionStatus.value.plan_name}）`;
});

const subscriptionDetail = computed(() => {
  if (subscriptionStatusError.value) return subscriptionStatusError.value;
  if (!subscriptionStatus.value) return '正在读取你的订阅信息...';
  const start = formatDateTime(subscriptionStatus.value.starts_at);
  const end = formatDateTime(subscriptionStatus.value.expires_at);
  return `状态：${subscriptionStatus.value.status}，开始：${start}，到期：${end}`;
});

const subscriptionCardClass = computed(() => {
  if (subscriptionStatusError.value) return 'border-rose-200 bg-rose-50 text-rose-700';
  if (!subscriptionStatus.value) return 'border-slate-200 bg-slate-50 text-slate-700';
  return subscriptionStatus.value.is_active
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-amber-200 bg-amber-50 text-amber-700';
});

const usageWarningClass = computed(() => {
  const level = String(subscriptionUsage.value?.warning_level || 'ok').toLowerCase();
  if (level === 'exceeded' || level === 'critical') return 'text-rose-700 font-semibold';
  if (level === 'warning') return 'text-amber-700 font-semibold';
  return 'text-emerald-700 font-semibold';
});

const loadSubscriptionMetrics = async () => {
  billingLoading.value = true;
  subscriptionUsageError.value = '';
  subscriptionBillingError.value = '';
  try {
    const [usage, billing] = await Promise.all([
      getMySubscriptionUsageSummary(),
      getMySubscriptionBilling({ hours: 72, limit: 80 })
    ]);
    subscriptionUsage.value = usage;
    subscriptionBilling.value = billing;
  } catch (error) {
    console.error('加载订阅额度/账单失败', error);
    if (!subscriptionUsage.value) {
      subscriptionUsageError.value = '暂时无法读取额度摘要。';
    }
    if (!subscriptionBilling.value) {
      subscriptionBillingError.value = '暂时无法读取账单明细。';
    }
  } finally {
    billingLoading.value = false;
  }
};

onMounted(async () => {
  try {
    const existingConfig = await getLLMConfig();
    if (existingConfig) {
      config.value = {
        llm_provider_url: existingConfig.llm_provider_url || '',
        llm_provider_api_key: existingConfig.llm_provider_api_key || '',
        llm_provider_model: existingConfig.llm_provider_model || '',
      };
    }
  } catch (error) {
    console.error('加载 LLM 配置失败', error);
  }

  try {
    subscriptionStatus.value = await getMySubscriptionStatus();
  } catch (error) {
    console.error('加载订阅状态失败', error);
    subscriptionStatusError.value = '暂时无法读取订阅状态，请稍后重试。';
  }
  await loadSubscriptionMetrics();
});

const handleSave = async () => {
  await createOrUpdateLLMConfig(config.value);
  alert('设置已保存！');
};

const handleDelete = async () => {
  if (confirm('确定要删除您的自定义LLM配置吗？删除后将恢复为默认配置。')) {
    await deleteLLMConfig();
    config.value = {
      llm_provider_url: '',
      llm_provider_api_key: '',
      llm_provider_model: '',
    };
    alert('配置已删除！');
  }
};

const toggleApiKeyVisibility = () => {
  showApiKey.value = !showApiKey.value;
};

const clearApiKey = () => {
  config.value.llm_provider_api_key = '';
};

const clearApiUrl = () => {
  config.value.llm_provider_url = '';
};

const clearApiModel = () => {
  config.value.llm_provider_model = '';
};

const loadModels = async () => {
  // 验证表单
  if (!config.value.llm_provider_api_key) {
    alert('请先填写 API Key');
    return;
  }

  isLoadingModels.value = true;
  try {
    const models = await getAvailableModels({
      llm_provider_api_key: config.value.llm_provider_api_key,
      llm_provider_url: config.value.llm_provider_url || undefined,
    });
    availableModels.value = models;
    if (models.length > 0) {
      showModelDropdown.value = true;
    } else {
      alert('未获取到模型列表，请检查API配置是否正确');
    }
  } catch (error) {
    console.error('Failed to load models:', error);
    alert('获取模型列表失败，请检查网络连接和API配置');
  } finally {
    isLoadingModels.value = false;
  }
};

const runConnectionTest = async () => {
  if (!config.value.llm_provider_api_key) {
    alert('请先填写 API Key');
    return;
  }

  isTestingConnection.value = true;
  try {
    connectionResult.value = await testLLMConnection({
      llm_provider_api_key: config.value.llm_provider_api_key,
      llm_provider_url: config.value.llm_provider_url || undefined,
      llm_provider_model: config.value.llm_provider_model || undefined,
    });
  } catch (error) {
    console.error('LLM connection test failed:', error);
    connectionResult.value = {
      success: false,
      provider: 'unknown',
      message: '连接测试失败，请稍后重试',
      latency_ms: null,
      model_count: 0,
      sample_models: [],
    };
  } finally {
    isTestingConnection.value = false;
  }
};

const selectModel = (model: string) => {
  config.value.llm_provider_model = model;
  showModelDropdown.value = false;
};

const hideDropdown = () => {
  // 延迟隐藏，确保点击事件能触发
  setTimeout(() => {
    showModelDropdown.value = false;
  }, 200);
};
</script>
