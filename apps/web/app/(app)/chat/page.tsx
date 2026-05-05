"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Attachment,
  Citation,
  ChatMessage,
  Course,
  Thread,
  UploadedDoc,
  getCourses,
  getMessages,
  getThreads,
  deleteThread,
  sendMessage,
  uploadDocument,
  staticUrl,
} from "@/lib/api";

// ── Slide image viewer ────────────────────────────────────────────────────────
function SlideImages({ citations }: { citations: Citation[] }) {
  const slides = citations.filter((c) => c.doc_type === "slide" && c.slide_image_url);
  if (!slides.length) return null;
  return (
    <div className="flex gap-2 flex-wrap mt-2">
      {slides.map((c, i) => (
        <div key={i} className="border border-slate-200 rounded-lg overflow-hidden w-48 flex-shrink-0 shadow-sm">
          <img
            src={staticUrl(c.slide_image_url!)}
            alt={c.title}
            className="w-full object-cover"
            loading="lazy"
          />
          <div className="px-2 py-1 text-xs text-slate-500 truncate bg-slate-50">
            {c.source}{c.slide_num ? ` — Slide ${c.slide_num}` : ""}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Exam preview carousel + download button ───────────────────────────────────
function AttachmentBar({ attachments }: { attachments: Attachment[] }) {
  if (!attachments.length) return null;
  return (
    <div className="mt-2 flex flex-col gap-2">
      {attachments.map((a, i) => (
        <div key={i}>
          {/* Page image carousel */}
          {(a.preview_urls?.length ?? 0) > 0 && (
            <div className="flex gap-2 overflow-x-auto pb-1 mb-2" style={{ scrollSnapType: "x mandatory" }}>
              {a.preview_urls!.map((url, pi) => (
                <div
                  key={pi}
                  className="flex-shrink-0 border border-slate-200 rounded-lg overflow-hidden shadow-sm"
                  style={{ width: 200, scrollSnapAlign: "start" }}
                >
                  <img
                    src={staticUrl(url)}
                    alt={`Page ${pi + 1}`}
                    className="w-full object-contain bg-white"
                    loading="lazy"
                  />
                  <div className="px-2 py-0.5 text-xs text-slate-400 bg-slate-50 text-center">
                    Page {pi + 1}
                  </div>
                </div>
              ))}
            </div>
          )}
          {/* Download button */}
          <a
            href={staticUrl(a.url)}
            download={a.filename}
            className="inline-flex items-center gap-2 bg-[#003262] text-white text-xs font-semibold px-3 py-2 rounded-lg hover:bg-[#004a8f] transition-colors"
          >
            <span>📄</span>
            {a.label}
          </a>
        </div>
      ))}
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────
function MessageBubble({
  msg,
  onShowSources,
}: {
  msg: ChatMessage & { streaming?: boolean; streamContent?: string };
  onShowSources: (c: Citation[]) => void;
}) {
  const isUser = msg.role === "user";
  const content = msg.streaming ? (msg.streamContent ?? "") : msg.content;
  const hasCitations = (msg.citations?.length ?? 0) > 0;
  const hasImages = msg.citations?.some((c) => c.doc_type === "slide" && c.slide_image_url);
  const hasAttachments = (msg.attachments?.length ?? 0) > 0;

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
          isUser ? "bg-[#003262] text-white" : "bg-[#FDB515] text-[#003262]"
        }`}
      >
        {isUser ? "You" : "AI"}
      </div>

      <div className={`max-w-[82%] flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "bg-[#003262] text-white rounded-tr-sm"
              : "bg-white border border-slate-200 text-slate-800 rounded-tl-sm"
          }`}
        >
          {isUser ? content : <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>}
          {msg.streaming && (
            <span className="inline-block w-1 h-4 bg-slate-400 animate-pulse ml-0.5 align-middle" />
          )}
        </div>

        {!isUser && hasImages && <SlideImages citations={msg.citations!} />}
        {!isUser && hasAttachments && <AttachmentBar attachments={msg.attachments!} />}
        {!isUser && hasCitations && (
          <button
            onClick={() => onShowSources(msg.citations!)}
            className="text-xs text-blue-600 hover:underline self-start"
          >
            {msg.citations!.length} source{msg.citations!.length !== 1 ? "s" : ""}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ChatPage() {
  const { data: session, status } = useSession();
  if (status === "unauthenticated") redirect("/login");

  const [courses, setCourses] = useState<Course[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [selectedCourse, setSelectedCourse] = useState("");
  const [selectedThread, setSelectedThread] = useState<string | null>(null);
  const [messages, setMessages] = useState<(ChatMessage & { streaming?: boolean; streamContent?: string })[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sidebarCitations, setSidebarCitations] = useState<Citation[]>([]);
  const [uploadedDocs, setUploadedDocs] = useState<UploadedDoc[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const token = (session as any)?.accessToken ?? (session as any)?.id_token ?? "";

  useEffect(() => {
    if (!token) return;
    getCourses(token).then((c) => { setCourses(c); if (c.length) setSelectedCourse(c[0].id); });
    getThreads(token).then(setThreads);
  }, [token]);

  async function loadThread(id: string) {
    setSelectedThread(id);
    setMessages(await getMessages(id, token) as any);
    setSidebarCitations([]);
  }

  function newThread() {
    setSelectedThread(null);
    setMessages([]);
    setSidebarCitations([]);
    setUploadedDocs([]);
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !selectedCourse) return;
    e.target.value = "";
    setUploading(true);
    try {
      const result = await uploadDocument({
        file,
        threadId: selectedThread ?? undefined,
        course: selectedCourse,
        token,
      });
      if (!selectedThread) setSelectedThread(result.thread_id);
      setUploadedDocs((p) => [...p, { doc_id: result.doc_id, filename: result.filename, chars: result.chars }]);
      getThreads(token).then(setThreads);
    } catch (err) {
      console.error("Upload failed", err);
    } finally {
      setUploading(false);
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || sending || !selectedCourse) return;
    const text = input.trim();
    setInput("");
    setSending(true);

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: text, created_at: new Date().toISOString() };
    const streamId = crypto.randomUUID();
    const streamMsg = { id: streamId, role: "assistant" as const, content: "", created_at: new Date().toISOString(), streaming: true, streamContent: "" };
    setMessages((p) => [...p, userMsg, streamMsg]);
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });

    try {
      const result = await sendMessage(
        { threadId: selectedThread ?? undefined, course: selectedCourse, content: text, token },
        (tok) => {
          setMessages((p) =>
            p.map((m) => m.id === streamId ? { ...m, streamContent: (m.streamContent ?? "") + tok } : m)
          );
          bottomRef.current?.scrollIntoView({ behavior: "smooth" });
        },
      );

      setMessages((p) =>
        p.map((m) =>
          m.id === streamId
            ? { ...m, streaming: false, content: m.streamContent ?? "", intent: result.intent, citations: result.citations, attachments: result.attachments }
            : m
        )
      );

      if (!selectedThread) {
        setSelectedThread(result.threadId);
        getThreads(token).then(setThreads);
      }
    } finally {
      setSending(false);
    }
  }

  async function handleDelete(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    await deleteThread(id, token);
    setThreads((p) => p.filter((t) => t.id !== id));
    if (selectedThread === id) newThread();
  }

  const courseName = courses.find((c) => c.id === selectedCourse)?.name ?? selectedCourse;

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* ── Sidebar ────────────────────────────────────────────────────────── */}
      <aside className="w-60 bg-[#003262] text-white flex flex-col flex-shrink-0">
        <div className="p-4 border-b border-white/10 font-bold text-[#FDB515]">MCB Tutor</div>

        <div className="p-3 border-b border-white/10">
          <select
            value={selectedCourse}
            onChange={(e) => setSelectedCourse(e.target.value)}
            className="w-full bg-white/10 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#FDB515]"
          >
            {courses.map((c) => (
              <option key={c.id} value={c.id} className="text-slate-900 bg-white">{c.name}</option>
            ))}
          </select>
        </div>

        <button onClick={newThread} className="mx-3 mt-3 bg-[#FDB515] text-[#003262] rounded-lg px-3 py-2 text-sm font-semibold hover:bg-yellow-400 transition-colors">
          + New chat
        </button>

        <div className="flex-1 overflow-y-auto mt-3 px-2 space-y-0.5">
          {threads.filter((t) => t.course === selectedCourse).map((t) => (
            <button
              key={t.id}
              onClick={() => loadThread(t.id)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center justify-between group ${selectedThread === t.id ? "bg-white/20" : "hover:bg-white/10"}`}
            >
              <span className="truncate opacity-90 text-xs">{t.title}</span>
              <span onClick={(e) => handleDelete(t.id, e)} className="opacity-0 group-hover:opacity-60 hover:!opacity-100 text-xs shrink-0 ml-1">✕</span>
            </button>
          ))}
        </div>
      </aside>

      {/* ── Chat ───────────────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-slate-200 px-6 py-3">
          <p className="font-semibold text-[#003262] text-sm">{courseName}</p>
          <p className="text-xs text-slate-400">Adaptive Socratic tutor</p>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {!messages.length && (
            <div className="text-center text-slate-400 mt-20 text-sm space-y-2">
              <p className="text-base font-medium text-slate-500">What would you like to create?</p>
              <p>📝 <span className="italic">Make me a practice exam</span></p>
              <p>📋 <span className="italic">Generate a cheatsheet</span></p>
              <p className="text-xs mt-4">Upload your own notes with the 📎 button to include them.</p>
            </div>
          )}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} onShowSources={setSidebarCitations} />
          ))}
          <div ref={bottomRef} />
        </div>

        <div className="bg-white border-t border-slate-200">
          {/* Uploaded docs strip */}
          {uploadedDocs.length > 0 && (
            <div className="flex gap-2 flex-wrap px-5 pt-3">
              {uploadedDocs.map((d) => (
                <span
                  key={d.doc_id}
                  className="inline-flex items-center gap-1.5 bg-blue-50 border border-blue-200 text-blue-700 text-xs rounded-full px-3 py-1"
                >
                  <span>📎</span>
                  <span className="max-w-[140px] truncate">{d.filename}</span>
                  <span className="text-blue-400">({Math.round(d.chars / 1000)}k chars)</span>
                </span>
              ))}
            </div>
          )}

          <form onSubmit={handleSend} className="flex gap-3 px-5 py-4">
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.pptx,.docx,.txt"
              className="hidden"
              onChange={handleUpload}
            />
            {/* Upload button */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              title="Upload PDF, PPTX, or DOCX"
              className="flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-xl border border-slate-200 text-slate-500 hover:border-[#003262] hover:text-[#003262] transition-colors disabled:opacity-40"
            >
              {uploading ? (
                <span className="w-4 h-4 border-2 border-slate-300 border-t-[#003262] rounded-full animate-spin" />
              ) : (
                <span className="text-base">📎</span>
              )}
            </button>

            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(e as any); } }}
              placeholder='Try "make me a practice exam" or "generate a cheatsheet"'
              rows={1}
              className="flex-1 resize-none border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#003262]"
              style={{ maxHeight: 120 }}
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="bg-[#003262] text-white rounded-xl px-5 py-2.5 text-sm font-semibold hover:bg-[#004a8f] transition-colors disabled:opacity-40"
            >
              Send
            </button>
          </form>
        </div>
      </main>

      {/* ── Sources sidebar ─────────────────────────────────────────────────── */}
      {sidebarCitations.length > 0 && (
        <aside className="w-56 bg-white border-l border-slate-200 p-4 overflow-y-auto flex-shrink-0">
          <div className="flex items-center justify-between mb-3">
            <span className="font-semibold text-sm text-slate-700">Sources</span>
            <button onClick={() => setSidebarCitations([])} className="text-slate-400 hover:text-slate-600 text-xs">close</button>
          </div>
          <div className="space-y-2">
            {sidebarCitations.map((c, i) => {
              const label = c.doc_type === "slide"
                ? `${c.source} — Slide ${c.slide_num ?? "?"}`
                : `${c.source}${c.heading_path ? " — " + c.heading_path : ""}`;
              return (
                <div key={i} className="text-xs border border-slate-200 rounded-lg p-2 text-slate-600">
                  {label}
                </div>
              );
            })}
          </div>
        </aside>
      )}
    </div>
  );
}
