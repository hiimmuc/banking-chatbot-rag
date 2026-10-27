import { API_BASE } from './config.js';

const KEY = 'rag.token';

export class AuthError extends Error {}

export const url = path => API_BASE + path;

// sessionStorage: the token dies with the tab and is not shared across tabs.
export const token = {
  get() { try { return sessionStorage.getItem(KEY); } catch { return null; } },
  set(value) { try { sessionStorage.setItem(KEY, value); } catch { /* storage blocked */ } },
  clear() { try { sessionStorage.removeItem(KEY); } catch { /* storage blocked */ } },
};

export async function api(path, {headers = {}, ...options} = {}) {
  const t = token.get();
  let response;
  try {
    response = await fetch(url(path), {...options, headers: t ? {...headers, Authorization: `Bearer ${t}`} : headers});
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new Error('Không kết nối được máy chủ. Kiểm tra mạng hoặc địa chỉ API.');
  }
  if (response.status === 401 && path !== '/api/login') {
    token.clear();
    document.dispatchEvent(new Event('auth-required'));
    throw new AuthError('Phiên đã hết hạn, cần đăng nhập lại.');
  }
  return response;
}

export async function getJson(path) {
  const r = await api(path);
  if (!r.ok) throw new Error(`Lỗi máy chủ (${r.status})`);
  return r.json();
}
