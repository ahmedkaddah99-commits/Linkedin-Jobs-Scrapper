import { browser } from "wxt/browser";

export interface LibraryDocument { id: string; name: string; role: "cv" | "cover_letter"; updatedAt?: string }
export interface ReviewedAnswer { question: string; text: string }
export interface Library { documents: LibraryDocument[]; answers: ReviewedAnswer[] }
function record(value: unknown): value is Record<string, unknown> { return !!value && typeof value === "object" && !Array.isArray(value); }
function text(value: unknown, max: number): value is string { return typeof value === "string" && value.length > 0 && value.length <= max; }
function document(value: unknown): boolean {
  return record(value) && text(value.id, 300) && text(value.name, 300) && /\.(pdf|docx)$/iu.test(value.name) && ["cv", "cover_letter"].includes(String(value.role));
}
export function validWorkspaceResult(action: string, value: unknown): boolean {
  if (!record(value)) return false;
  switch (action) {
    case "library": return Array.isArray(value.documents) && value.documents.length <= 1000 && value.documents.every(document)
      && Array.isArray(value.answers) && value.answers.length <= 100 && value.answers.every((answer) => record(answer) && text(answer.question, 3000) && text(answer.text, 10000));
    case "document": return text(value.id, 300) && text(value.name, 300) && /\.(pdf|docx)$/iu.test(value.name) && text(value.base64, 28 * 1024 * 1024) && /^[A-Za-z0-9+/]*={0,2}$/u.test(value.base64);
    case "draft": return text(value.text, 30000);
    case "save-document": return document(value.document);
    case "save-answer": return record(value.answer) && text(value.answer.question, 3000) && text(value.answer.text, 10000);
    case "report": return text(value.receipt, 100) && /^issue_[a-z0-9_]+$/u.test(value.receipt);
    default: return false;
  }
}
export async function workspaceRequest<T>(action: string, payload: object = {}): Promise<T> {
  const response = await browser.runtime.sendMessage({ type: "ASSISTED_APPLY_PANEL_WORKSPACE", action, payload });
  if (!response || typeof response !== "object" || response.ok !== true) throw new Error(response?.error || "Couldn't load this workspace. Connect Runr and retry.");
  if (!validWorkspaceResult(action, response.result)) throw new Error("Runr returned an incomplete response. Refresh and try again.");
  return response.result as T;
}
