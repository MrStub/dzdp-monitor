function stripTrailingSlash(value) {
  return String(value || '').replace(/\/+$/, '');
}

async function parseResponse(response) {
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

export async function apiRequest(baseUrl, token, path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${stripTrailingSlash(baseUrl)}${path}`, {
    ...options,
    headers
  });
  return parseResponse(response);
}

export function getDashboard(baseUrl, token) {
  return apiRequest(baseUrl, token, '/api/dashboard');
}

export function addTarget(baseUrl, token, payload) {
  return apiRequest(baseUrl, token, '/api/targets', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function updateTarget(baseUrl, token, index, payload) {
  return apiRequest(baseUrl, token, `/api/targets/${index}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}

export function deleteTarget(baseUrl, token, index) {
  return apiRequest(baseUrl, token, `/api/targets/${index}`, {
    method: 'DELETE'
  });
}

export function addNotifyGroup(baseUrl, token, payload) {
  return apiRequest(baseUrl, token, '/api/notify-groups', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function updateNotifyGroup(baseUrl, token, key, payload) {
  return apiRequest(baseUrl, token, `/api/notify-groups/${encodeURIComponent(key)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}

export function deleteNotifyGroup(baseUrl, token, key) {
  return apiRequest(baseUrl, token, `/api/notify-groups/${encodeURIComponent(key)}`, {
    method: 'DELETE'
  });
}

export function updatePoll(baseUrl, token, seconds) {
  return apiRequest(baseUrl, token, '/api/poll', {
    method: 'PUT',
    body: JSON.stringify({ seconds })
  });
}

export function updateProxy(baseUrl, token, payload) {
  return apiRequest(baseUrl, token, '/api/proxy', {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
}
