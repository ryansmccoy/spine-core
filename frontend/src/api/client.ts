/** Thin fetch wrapper for the spine-core API. */

const BASE = '/api/v1';

class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API ${status}`);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body);
  }
  return res.json();
}

function get<T>(path: string) {
  return request<T>(path);
}

function post<T>(path: string, body?: unknown) {
  return request<T>(path, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  });
}

function put<T>(path: string, body: unknown) {
  return request<T>(path, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

function del<T>(path: string) {
  return request<T>(path, { method: 'DELETE' });
}

export const api = { get, post, put, del, ApiError };
