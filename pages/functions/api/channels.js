import { getFile, putFile } from "../_gh.js";

export async function onRequestGet({ env }) {
  try {
    const { content } = await getFile(env, "channels.json");
    return Response.json(content);
  } catch (e) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

export async function onRequestPost({ env, request }) {
  if (!env.GH_TOKEN) {
    return Response.json({ error: "未配置 GH_TOKEN，无法写入" }, { status: 400 });
  }
  try {
    const body = await request.json();
    const { content, sha } = await getFile(env, "channels.json");
    content.push({
      name: body.name || "未命名",
      type: body.type || "channel",
      channel_id: body.channel_id,
    });
    const ok = await putFile(env, "channels.json", content, sha, `web: add ${body.name}`);
    return Response.json({ ok });
  } catch (e) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
