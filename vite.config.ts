import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// 前端统一请求相对路径 `/api/v1/...`，由开发服务器代理到后端（见 backend/design_file/api.md §3.1）。
// 代理保留路径、Host、Origin 与 Cookie，并原样转发 Set-Cookie。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.DEV_API_TARGET;

  if (!target) {
    throw new Error('请先在 .env 中配置 DEV_API_TARGET 为后端服务的 origin（如 http://127.0.0.1:8000）');
  }

  const proxy = {
    '/api/v1': {
      target,
      changeOrigin: false,
    },
  };

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(__dirname, 'src') },
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy,
    },
    // `vite preview` 用于本地核对生产构建，沿用同一代理配置
    preview: {
      port: 4173,
      strictPort: true,
      proxy,
    },
  };
});
