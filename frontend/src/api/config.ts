// AIMETA P=API配置_统一基础URL和前缀|R=基础路径常量|NR=不含请求逻辑|E=api:config|X=internal|A=常量|D=none|S=none|RD=./README.ai
export const API_BASE_URL = import.meta.env.MODE === 'production' ? '' : 'http://127.0.0.1:8000'
export const API_PREFIX = '/api'
export const ADMIN_API_PREFIX = '/api/admin'
export const WRITER_API_PREFIX = '/api/writer'
