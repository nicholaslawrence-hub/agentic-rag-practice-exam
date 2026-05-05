const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Course {
  id: string;
  name: string;
  color: string;
}

export interface Thread {
  id: string;
  course: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  source: string;
  title: string;
  doc_type: string;
  slide_num?: number;
  slide_image_url?: string;   // relative API path → prepend API_BASE
  heading_path?: string;
}

export interface Attachment {
  filename: string;
  url: string;                // relative API path → prepend API_BASE
  mime_type: string;
  label: string;
  preview_urls?: string[];    // page PNGs for in-chat carousel (practice exam)
}

export interface UploadedDoc {
  doc_id: string;
  filename: string;
  chars: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  intent?: string;
  citations?: Citation[];
  attachments?: Attachment[];
  created_at: string;
}

async function apiFetch(path: string, token: string, init?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res;
}

export const getCourses = (t: string) =>
  apiFetch("/courses", t).then((r) => r.json() as Promise<Course[]>);

export const getThreads = (t: string) =>
  apiFetch("/chat/threads", t).then((r) => r.json() as Promise<Thread[]>);

export const getMessages = (threadId: string, t: string) =>
  apiFetch(`/chat/threads/${threadId}/messages`, t).then((r) => r.json() as Promise<ChatMessage[]>);

export const deleteThread = (threadId: string, t: string) =>
  apiFetch(`/chat/threads/${threadId}`, t, { method: "DELETE" });

export function staticUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export async function uploadDocument(params: {
  file: File;
  threadId?: string;
  course: string;
  token: string;
}): Promise<{ doc_id: string; thread_id: string; filename: string; chars: number }> {
  const { file, threadId, course, token } = params;
  const qs = new URLSearchParams({ course });
  if (threadId) qs.set("thread_id", threadId);
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/upload?${qs}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) throw new Error(`Upload failed: ${await res.text()}`);
  return res.json();
}

export const listDocuments = (threadId: string, token: string) =>
  apiFetch(`/upload/documents?thread_id=${threadId}`, token).then(
    (r) => r.json() as Promise<UploadedDoc[]>
  );

export interface SendResult {
  threadId: string;
  intent: string;
  citations: Citation[];
  attachments: Attachment[];
}

export async function sendMessage(
  params: { threadId?: string; course: string; content: string; token: string },
  onToken: (text: string) => void,
): Promise<SendResult> {
  const { threadId, course, content, token } = params;
  const res = await fetch(`${API_BASE}/chat/send`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ thread_id: threadId ?? null, course, content }),
  });
  if (!res.ok) throw new Error(`API ${res.status}`);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let result: SendResult | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const parsed = JSON.parse(line.slice(6));
        if ("text" in parsed) {
          onToken(parsed.text);
        } else if ("thread_id" in parsed) {
          result = {
            threadId: parsed.thread_id,
            intent: parsed.intent,
            citations: parsed.citations ?? [],
            attachments: parsed.attachments ?? [],
          };
        }
      } catch {}
    }
  }
  return result!;
}
