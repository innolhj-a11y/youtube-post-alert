const base = "https://www.editmon.com/work/";

export function extract(html) {
  const rows = new Map();
  for (const match of html.matchAll(/<a\b[^>]*\bhref\s*=\s*["'](?:[^"']*\/)?employ_detail\.html\?no=(\d+)["'][^>]*>([\s\S]*?)<\/a>/gi)) {
    const entities = {amp:"&", quot:'"', apos:"'", lt:"<", gt:">", nbsp:" "};
    const title = match[2].replace(/<[^>]*>/g, "").replace(/&(amp|quot|apos|lt|gt|nbsp|#39);/g,
      (_, key) => key === "#39" ? "'" : entities[key]).replace(/\s+/g, " ").trim();
    if (title) rows.set(Number(match[1]), title);
  }
  if (!rows.size) throw new Error("편집몬 목록에서 제목을 읽을 수 없습니다.");
  return rows;
}

async function loadPage(page) {
  const response = await fetch(base + "employ_list.html?sort=write_date&page=" + page, {
    cache: "no-store", signal: AbortSignal.timeout(15000)
  });
  if (!response.ok) throw new Error("편집몬 HTTP " + response.status);
  const bytes = await response.arrayBuffer();
  const header = new TextDecoder().decode(bytes.slice(0, 3000));
  const html = new TextDecoder(/charset\s*=\s*["']?utf-8/i.test(header) ? "utf-8" : "euc-kr").decode(bytes);
  return {rows: extract(html), next: new RegExp("employ_list\\.html\\?[^'\"<>]*\\bpage=" + (page + 1) + "(?:[&'\"#]|$)", "i").test(html)};
}

export async function collect(previous, load = loadPage) {
  const fresh = new Map();
  let lastMin = Infinity;
  for (let page = 1; ; page++) {
    const {rows, next} = await load(page);
    const min = Math.min(...rows.keys());
    if (min >= lastMin) throw new Error("편집몬 페이지가 반복되었습니다.");
    for (const [id, title] of rows) if (previous == null || id > previous) fresh.set(id, title);
    if (previous == null || min <= previous || !next) break;
    lastMin = min;
  }
  return [...fresh].sort(([a], [b]) => a - b);
}

function send(env, message) {
  const result = spawnSync("python3", ["-c", "import sys; from bot import send; send(sys.stdin.read())"], {
    input: message, encoding: "utf8", stdio: ["pipe", "ignore", "ignore"],
    env: {...process.env, TELEGRAM_BOT_TOKEN: env.BOT_TOKEN.trim(), TELEGRAM_CHAT_ID: env.CHAT_ID.trim()}
  });
  if (result.status !== 0) throw new Error("텔레그램 전송 실패");
}

import {execFileSync, spawnSync} from "node:child_process";
import {readFileSync, writeFileSync} from "node:fs";
import {pathToFileURL} from "node:url";

function checkpoint(id) {
  writeFileSync("state/editmon-last-id.json", JSON.stringify(id) + "\n");
  for (const args of [["add", "state/editmon-last-id.json"], ["commit", "-m", "Save Editmon notification progress"], ["pull", "--rebase", "origin", process.env.GITHUB_REF_NAME], ["push", "origin", "HEAD:" + process.env.GITHUB_REF_NAME]]) {
    execFileSync("git", args, {stdio:"inherit"});
  }
}

export async function run(previous, jobs, notify, save) {
  if (previous === null) {
    await notify("편집몬 알림이 시작됐습니다. 한국 시간 06:00~24:00에 새 공고를 확인합니다.");
    await save(jobs.at(-1)[0]);
    return;
  }
  for (const [id, title] of jobs) {
    await notify("🎬 편집몬 신규 공고\n" + title + "\n" + base + "employ_detail.html?no=" + id);
    await save(id);
    if (id !== jobs.at(-1)[0]) await new Promise(resolve => setTimeout(resolve, 1100));
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (!process.env.BOT_TOKEN || !process.env.CHAT_ID) throw new Error("BOT_TOKEN / CHAT_ID 설정을 확인하세요.");
  const previous = JSON.parse(readFileSync("state/editmon-last-id.json", "utf8"));
  if (previous !== null && !(Number.isSafeInteger(previous) && previous > 0)) throw new Error("공고 번호 저장값 오류");
  await run(previous, await collect(previous), msg => send(process.env, msg), checkpoint);
}
