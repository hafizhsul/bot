import "dotenv/config";
import { Bot } from "grammy";
import * as pty from "node-pty";
import { existsSync, mkdirSync } from "node:fs";

// ---------- Config ----------
const TOKEN = requireEnv("TELEGRAM_BOT_TOKEN");
const ALLOWED_CHAT_IDS = new Set(
  requireEnv("ALLOWED_CHAT_IDS")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
);
const DEFAULT_DIR = requireEnv("DEFAULT_PROJECT_DIR");
const OPENCODE_BIN = process.env.OPENCODE_BIN || "opencode";
const OPENCODE_MODEL = process.env.OPENCODE_MODEL || "";
// Default true karena opencode run butuh --auto supaya nggak nunggu approval
// interaktif (yang bakal bikin bot hang selamanya). Bisa dimatikan lewat env
// kalau kamu sudah atur permission whitelist sendiri di config opencode.
const AUTO_APPROVE = (process.env.OPENCODE_AUTO_APPROVE ?? "true") !== "false";

// state per chat: direktori kerja & apakah sudah pernah run (buat --continue)
type ChatState = { dir: string; started: boolean };
const chatState = new Map<number, ChatState>();

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) {
    console.error(`Missing env var: ${name} (cek .env kamu)`);
    process.exit(1);
  }
  return v;
}

function getState(chatId: number): ChatState {
  if (!chatState.has(chatId)) {
    chatState.set(chatId, { dir: DEFAULT_DIR, started: false });
  }
  return chatState.get(chatId)!;
}

// ---------- Helpers tampilan ----------

function stripAnsi(s: string): string {
  return s
    .replace(/\x1B\[[0-?]*[ -\/]*[@-~]/g, "")
    .replace(/\x1B\][^\x07]*\x07/g, "")
    .replace(/\r/g, "");
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Ubah teks prosa markdown-ish (bold, inline code, header) jadi HTML Telegram.
// TIDAK dibungkus <pre> supaya Telegram auto word-wrap -> enak dibaca di HP,
// nggak perlu geser layar ke samping.
function formatProse(text: string): string {
  let t = escapeHtml(text);
  t = t.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  t = t.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  t = t.replace(/^#{1,6}\s+(.*)$/gm, "<b>$1</b>");
  return t;
}

type Segment = { code: boolean; raw: string };

// Pisahkan output jadi segmen "prosa biasa" vs "blok kode ```...```"
function parseSegments(md: string): Segment[] {
  const segments: Segment[] = [];
  const regex = /```[a-zA-Z0-9]*\n?([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(md))) {
    if (m.index > last) segments.push({ code: false, raw: md.slice(last, m.index) });
    segments.push({ code: true, raw: m[1] });
    last = m.index + m[0].length;
  }
  if (last < md.length) segments.push({ code: false, raw: md.slice(last) });
  return segments.filter((s) => s.raw.trim().length > 0);
}

function renderSegment(seg: Segment): string {
  if (seg.code) return `<pre><code>${escapeHtml(seg.raw.trim())}</code></pre>`;
  return formatProse(seg.raw.trim());
}

// Susun output final jadi beberapa pesan Telegram, tanpa motong di tengah tag HTML,
// dan pecah blok kode besar per-baris biar tetap kebaca di layar sempit.
function buildTelegramChunks(md: string, maxLen = 3500): string[] {
  const segments = parseSegments(md);
  const chunks: string[] = [];
  let current = "";

  const push = () => {
    if (current.trim()) chunks.push(current.trim());
    current = "";
  };

  for (const seg of segments) {
    const rendered = renderSegment(seg);
    if (rendered.length > maxLen) {
      push();
      if (seg.code) {
        const step = maxLen - 30;
        for (let i = 0; i < seg.raw.length; i += step) {
          chunks.push(`<pre><code>${escapeHtml(seg.raw.slice(i, i + step))}</code></pre>`);
        }
      } else {
        for (const para of seg.raw.split(/\n{2,}/)) {
          const renderedPara = formatProse(para.trim()) + "\n\n";
          if ((current + renderedPara).length > maxLen) push();
          current += renderedPara;
        }
      }
      continue;
    }
    if ((current + "\n\n" + rendered).length > maxLen) push();
    current += (current ? "\n\n" : "") + rendered;
  }
  push();
  return chunks.length ? chunks : ["(kosong)"];
}

// ---------- Jalankan opencode dengan live update ----------

function runOpencodeStreaming(
  prompt: string,
  cwd: string,
  continueSession: boolean,
  onUpdate: (partial: string) => void
): Promise<string> {
  return new Promise((resolve, reject) => {
    const args = ["run"];
    if (continueSession) args.push("--continue");
    if (OPENCODE_MODEL) args.push("--model", OPENCODE_MODEL);
    if (AUTO_APPROVE) args.push("--auto");
    args.push(prompt);

    // Pakai pseudo-terminal (PTY) sendiri, terpisah dari stdin bot ini.
    // opencode run butuh TTY asli buat jalan normal; kalau cuma pipe biasa
    // dia bisa hang atau lempar "UnknownError". PTY bikin ini konsisten
    // apapun cara bot dijalankan (terminal interaktif, tmux, atau nanti
    // systemd/pm2 sekalipun).
    let term: pty.IPty;
    try {
      term = pty.spawn(OPENCODE_BIN, args, {
        name: "xterm-256color",
        cols: 120,
        rows: 40,
        cwd,
        env: process.env as { [key: string]: string },
      });
    } catch (err: any) {
      reject(err);
      return;
    }

    let buffer = "";
    let settled = false;

    term.onData((data) => {
      buffer += stripAnsi(data);
      onUpdate(buffer);
    });

    term.onExit(() => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      resolve(buffer.trim() || "(tidak ada output)");
    });

    const timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      try {
        term.kill();
      } catch {
        // proses mungkin sudah mati duluan
      }
      reject(
        new Error(
          "Timeout: opencode nggak merespon dalam 5 menit (kemungkinan nunggu approval permission atau nyangkut)"
        )
      );
    }, 5 * 60 * 1000);
  });
}

// ---------- Bot ----------
const bot = new Bot(TOKEN);

bot.use(async (ctx, next) => {
  const chatId = ctx.chat?.id;
  if (!chatId || !ALLOWED_CHAT_IDS.has(String(chatId))) {
    await ctx.reply(`Chat ID kamu (${chatId}) belum di-whitelist. Minta owner tambahin ke ALLOWED_CHAT_IDS.`);
    return;
  }
  await next();
});

bot.command("start", (ctx) =>
  ctx.reply(
    "Bot OpenCode siap.\n\n" +
      "Kirim pesan apa aja = prompt ke OpenCode di direktori project aktif.\n\n" +
      "/dir <path> — ganti direktori project\n" +
      "/reset — mulai sesi baru (bukan lanjutan)\n" +
      "/where — lihat direktori aktif"
  )
);

bot.command("dir", async (ctx) => {
  const path = ctx.match?.toString().trim();
  if (!path) return ctx.reply("Pakai: /dir /path/ke/project");
  if (!existsSync(path)) return ctx.reply(`Direktori "${path}" tidak ditemukan di server.`);
  const state = getState(ctx.chat.id);
  state.dir = path;
  state.started = false;
  await ctx.reply(`Direktori diganti ke: ${path}`);
});

bot.command("reset", async (ctx) => {
  const state = getState(ctx.chat.id);
  state.started = false;
  await ctx.reply("Sesi direset. Prompt berikutnya mulai percakapan baru.");
});

bot.command("where", async (ctx) => {
  const state = getState(ctx.chat.id);
  await ctx.reply(`Direktori aktif: ${state.dir}`);
});

bot.on("message:text", async (ctx) => {
  const text = ctx.message.text;
  if (text.startsWith("/")) return;

  const state = getState(ctx.chat.id);
  if (!existsSync(state.dir)) mkdirSync(state.dir, { recursive: true });

  // pesan status yang di-edit live selama proses (plain text, tanpa parse_mode,
  // biar aman dari partial-tag saat output belum lengkap)
  const liveMsg = await ctx.reply("⏳ Menjalankan prompt di OpenCode...");

  let lastStatus = "";
  let lastEditAt = 0;
  let pendingEdit: NodeJS.Timeout | null = null;
  const MIN_EDIT_INTERVAL_MS = 1200;
  const startedAt = Date.now();

  const doStatusEdit = async (raw: string) => {
    const elapsed = Math.round((Date.now() - startedAt) / 1000);
    const preview = raw.slice(-300).trim();
    const status = `⏳ Menjalankan (${elapsed}s)...\n\n${preview}`;
    if (status === lastStatus) return;
    lastStatus = status;
    lastEditAt = Date.now();
    try {
      await ctx.api.editMessageText(ctx.chat.id, liveMsg.message_id, status);
    } catch {
      // abaikan "message not modified" / rate limit sesaat
    }
  };

  const scheduleStatus = (raw: string) => {
    const elapsed = Date.now() - lastEditAt;
    if (pendingEdit) clearTimeout(pendingEdit);
    if (elapsed >= MIN_EDIT_INTERVAL_MS) doStatusEdit(raw);
    else pendingEdit = setTimeout(() => doStatusEdit(raw), MIN_EDIT_INTERVAL_MS - elapsed);
  };

  try {
    const output = await runOpencodeStreaming(text, state.dir, state.started, scheduleStatus);
    state.started = true;
    if (pendingEdit) clearTimeout(pendingEdit);

    const chunks = buildTelegramChunks(output);

    // edit pesan live jadi hasil pertama (rapi, HTML), sisanya kirim pesan baru
    try {
      await ctx.api.editMessageText(ctx.chat.id, liveMsg.message_id, chunks[0], {
        parse_mode: "HTML",
      });
    } catch {
      await ctx.reply(chunks[0], { parse_mode: "HTML" });
    }
    for (const part of chunks.slice(1)) {
      await ctx.reply(part, { parse_mode: "HTML" });
    }
  } catch (err: any) {
    if (pendingEdit) clearTimeout(pendingEdit);
    await ctx.api
      .editMessageText(ctx.chat.id, liveMsg.message_id, `❌ Error: ${err.message}`)
      .catch(() => ctx.reply(`❌ Error: ${err.message}`));
  }
});

bot.catch((err) => console.error("Bot error:", err));

bot.start();
console.log("opencode-tg-bot berjalan...");