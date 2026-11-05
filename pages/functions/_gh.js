// GitHub 仓库文件读写助手（供 Pages Functions 调用）。以下划线开头的文件不会被部署为路由。

const B64 = {
  decode(s) {
    s = (s || "").replace(/\n/g, "");
    const bin = atob(s);
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  },
  encode(str) {
    const bytes = new TextEncoder().encode(str);
    let bin = "";
    bytes.forEach((b) => (bin += String.fromCharCode(b)));
    return btoa(bin);
  },
};

export async function getFile(env, path) {
  const branch = env.GH_BRANCH || "main";
  const url = `https://api.github.com/repos/${env.GH_REPO}/contents/${path}?ref=${branch}`;
  const headers = { Accept: "application/vnd.github+json", "User-Agent": "yt2bili-pages" };
  if (env.GH_TOKEN) headers.Authorization = `Bearer ${env.GH_TOKEN}`;
  const r = await fetch(url, { headers });
  if (!r.ok) throw new Error(`GitHub ${r.status} for ${path}`);
  const data = await r.json();
  return { content: JSON.parse(B64.decode(data.content)), sha: data.sha };
}

export async function putFile(env, path, content, sha, message) {
  const branch = env.GH_BRANCH || "main";
  const url = `https://api.github.com/repos/${env.GH_REPO}/contents/${path}`;
  const headers = {
    Accept: "application/vnd.github+json",
    "User-Agent": "yt2bili-pages",
    Authorization: `Bearer ${env.GH_TOKEN}`,
  };
  const r = await fetch(url, {
    method: "PUT",
    headers,
    body: JSON.stringify({
      message,
      content: B64.encode(JSON.stringify(content, null, 2)),
      sha,
      branch,
    }),
  });
  return r.ok;
}
