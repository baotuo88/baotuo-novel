// AIMETA P=认证状态_用户登录状态管理|R=token_user_login_logout|NR=不含API调用|E=store:auth|X=internal|A=useAuthStore|D=pinia|S=storage|RD=./README.ai
import { defineStore } from 'pinia';
import { API_BASE_URL } from '@/api/config';
import { httpRequest } from '@/api/http';

const API_URL = `${API_BASE_URL}/api/auth`;

interface AuthOptions {
  // 是否允许用户自助注册
  allow_registration: boolean;
  // 是否启用 Linux.do 登录
  enable_linuxdo_login: boolean;
}

interface User {
  id: number;
  username: string;
  is_admin: boolean;
  must_change_password: boolean;
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null as string | null,
    user: null as User | null,
    authOptions: null as AuthOptions | null,
    authOptionsLoaded: false,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
    allowRegistration: (state) => state.authOptions?.allow_registration ?? true,
    enableLinuxdoLogin: (state) => state.authOptions?.enable_linuxdo_login ?? false,
    mustChangePassword: (state) => state.user?.must_change_password ?? false,
  },
  actions: {
    async fetchAuthOptions(force = false) {
      // 拉取后端认证相关开关，供前端动态渲染
      if (this.authOptionsLoaded && !force) {
        return;
      }
      try {
        const data = await httpRequest<AuthOptions>(`${API_URL}/options`);
        this.authOptions = data;
      } catch (error) {
        console.error('获取认证配置失败，将使用默认值', error);
        this.authOptions = {
          allow_registration: true,
          enable_linuxdo_login: false,
        };
      } finally {
        this.authOptionsLoaded = true;
      }
    },
    async login(username: string, password: string): Promise<boolean> {
      const params = new URLSearchParams();
      params.append('username', username);
      params.append('password', password);

      const data = await httpRequest<{ access_token: string; must_change_password?: boolean }>(`${API_URL}/token`, {
        method: 'POST',
        body: params,
      });
      this.token = data.access_token;
      if (this.token) {
        localStorage.setItem('token', this.token);
      }
      const mustChangePassword = Boolean(data.must_change_password);
      await this.fetchUser();
      if (this.user) {
        this.user.must_change_password = mustChangePassword || this.user.must_change_password;
      }
      return mustChangePassword;
    },
    // 当前注册流程在 Register.vue 中实现，此处预留方法以兼容旧逻辑
    async register(payload: { username: string; email: string; password: string; verification_code: string }) {
      await httpRequest(`${API_URL}/users`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    async forgotPassword(email: string) {
      await httpRequest(`${API_URL}/password/forgot`, {
        method: 'POST',
        body: JSON.stringify({ email }),
      })
    },
    async resetPassword(payload: { email: string; verification_code: string; new_password: string }) {
      await httpRequest(`${API_URL}/password/reset`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    logout() {
      this.token = null;
      this.user = null;
      localStorage.removeItem('token');
    },
    async fetchUser() {
      if (this.token) {
        try {
          const userData = await httpRequest<User>(`${API_URL}/users/me`, {
            token: this.token,
          })
          this.user = {
            id: userData.id,
            username: userData.username,
            is_admin: userData.is_admin || false,
            must_change_password: userData.must_change_password || false,
          };
        } catch (error) {
          this.logout();
        }
      }
    },
  },
});
