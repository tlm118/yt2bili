import { getFile } from "../_gh.js";

export async function onRequestGet({ env }) {
  try {
    const [{ content: channels }, { content: state }] = await Promise.all([
      getFile(env, "channels.json"),
      getFile(env, "state.json"),
    ]);
    const tasks = Object.fromEntries(
      Object.entries(state).filter(([k]) => !k.startsWith("_"))
    );
    const values = Object.values(tasks);
    const done = values.filter((v) => v.status === "done").length;
    const failed = values.filter((v) => v.status === "failed").length;
    return Response.json({
      channels,
      tasks,
      stats: { channels: channels.length, total: values.length, done, failed },
    });
  } catch (e) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
