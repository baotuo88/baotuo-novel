// AIMETA P=更新API客户端_更新日志接口|R=更新日志查询|NR=不含UI逻辑|E=api:updates|X=internal|A=updatesApi对象|D=axios|S=net|RD=./README.ai
// Using a relative path to avoid potential alias issues
import { API_BASE_URL } from './config';
import { httpRequest } from './http';

// A simplified request function for public endpoints that don't require authentication.
const publicRequest = async <T = unknown>(url: string, options: RequestInit = {}): Promise<T> => {
  return httpRequest<T>(url, options)
};

export interface UpdateLog {
  id: number;
  content: string;
  created_at: string;
}

export const getLatestUpdates = (): Promise<UpdateLog[]> => {
  return publicRequest(`${API_BASE_URL}/api/updates/latest`);
};
