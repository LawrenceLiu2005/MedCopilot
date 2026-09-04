/**
 * Evidence Copilot — Pi 医学科研工具扩展
 * 调用 Python 侧车；consequential 工具默认需用户在桌面 UI 批准。
 */
import { spawn } from "node:child_process";
import { Type } from "@sinclair/typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const CONSEQUENTIAL_TOOLS = new Set(["run_pubmed_search"]);

function repoRoot(): string {
  return process.env.EVIDENCE_COPILOT_ROOT || process.cwd();
}

function pythonCommand(): string {
  return process.env.EVIDENCE_COPILOT_PYTHON || "python3";
}

async function runSidecar(command: string, params: Record<string, unknown>): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const args = ["-m", "src.sidecar", "--command", command, "--params", JSON.stringify(params)];
    const child = spawn(pythonCommand(), args, {
      cwd: repoRoot(),
      env: { ...process.env, PYTHONPATH: repoRoot() },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `侧车退出码 ${code}`));
        return;
      }
      try {
        const payload = JSON.parse(stdout.trim());
        if (!payload.ok) {
          reject(new Error(payload.error || "侧车返回失败"));
          return;
        }
        resolve(payload.result);
      } catch (err) {
        reject(new Error(`侧车 JSON 解析失败：${String(err)}`));
      }
    });
  });
}

export default function evidenceCopilotExtension(pi: ExtensionAPI) {
  pi.on("tool_call", async (event, ctx) => {
    if (CONSEQUENTIAL_TOOLS.has(event.toolName)) {
      const approved = Boolean((event.input as { approved?: boolean }).approved);
      if (!approved) {
        const ok = await ctx.ui.confirm(
          "需要你的确认",
          `是否批准执行 ${event.toolName}？未批准将不会调用 PubMed。`,
        );
        if (!ok) {
          return { block: true, reason: "用户未批准 consequential 工具调用" };
        }
      }
    }
    return undefined;
  });

  pi.registerTool({
    name: "propose_pubmed_search",
    label: "提议 PubMed 检索",
    description:
      "根据白话科研想法生成 PICO 与 PubMed 检索式提议。不会执行检索；必须等用户确认后再调用 run_pubmed_search。",
    parameters: Type.Object({
      research_idea: Type.String({ description: "用户的白话科研想法" }),
      project_id: Type.Optional(Type.String({ description: "已有项目 ID，可选" })),
      year_from: Type.Optional(Type.Integer()),
      year_to: Type.Optional(Type.Integer()),
      retmax: Type.Optional(Type.Integer({ description: "返回条数，默认 50" })),
    }),
    async execute(_toolCallId, params) {
      const result = await runSidecar("propose_search", params as Record<string, unknown>);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: result,
      };
    },
  });

  pi.registerTool({
    name: "run_pubmed_search",
    label: "执行 PubMed 检索",
    description:
      "在用户已明确批准后执行 PubMed 检索。参数 approved 必须为 true；否则工具应被拦截。",
    parameters: Type.Object({
      project_id: Type.String({ description: "ResearchProject ID" }),
      query: Type.Optional(Type.String({ description: "最终检索式；缺省用已提议检索式" })),
      approved: Type.Boolean({ description: "用户是否已批准执行" }),
      year_from: Type.Optional(Type.Integer()),
      year_to: Type.Optional(Type.Integer()),
      retmax: Type.Optional(Type.Integer()),
    }),
    async execute(_toolCallId, params) {
      const result = await runSidecar("run_pubmed_search", params as Record<string, unknown>);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: result,
      };
    },
  });

  pi.registerTool({
    name: "get_research_project",
    label: "读取科研项目",
    description: "读取持久化的 ResearchProject 状态与审计轨迹摘要。",
    parameters: Type.Object({
      project_id: Type.String(),
    }),
    async execute(_toolCallId, params) {
      const result = await runSidecar("get_project", params as Record<string, unknown>);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: result,
      };
    },
  });
}
