import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type RecommendationRequest =
  | components["schemas"]["PlantRecommendationRequest"]
  | components["schemas"]["DogRecommendationRequest"]
  | components["schemas"]["CatRecommendationRequest"];
export type RecommendationResponse = components["schemas"]["RecommendationResponse"];
export type RecommendationItem = components["schemas"]["RecommendationItem"];
export type RecommendationStreamEvent = components["schemas"]["RecommendationStreamEvent"];
export type CarePlanPreviewRequest = components["schemas"]["CarePlanPreviewRequest"];
export type CarePlanPreviewResponse = components["schemas"]["CarePlanPreviewResponse"];
export type CarePlan = components["schemas"]["CarePlan"];

export class AdvisorApiError extends Error {
  readonly status: number;
  readonly requestId: string | null;

  constructor(message: string, status: number, requestId: string | null) {
    super(message);
    this.name = "AdvisorApiError";
    this.status = status;
    this.requestId = requestId;
  }
}

export function createAdvisorClient(baseUrl = "/api") {
  const client = createClient<paths>({ baseUrl });

  return {
    async previewCarePlan(body: CarePlanPreviewRequest): Promise<CarePlanPreviewResponse> {
      const { data, error, response } = await client.POST("/v1/care-plans/preview", {
        body,
      });
      if (!data) {
        throw apiError(response, error);
      }
      return data;
    },

    async createCarePlan(previewId: string): Promise<CarePlan> {
      const { data, error, response } = await client.POST("/v1/care-plans", {
        body: { preview_id: previewId, confirmed: true },
      });
      if (!data) {
        throw apiError(response, error);
      }
      return data;
    },

    streamRecommendations(
      body: RecommendationRequest,
      onEvent: (event: RecommendationStreamEvent) => void,
      options: { signal?: AbortSignal; lastEventId?: string } = {},
    ): Promise<void> {
      return streamRecommendationEvents(baseUrl, body, onEvent, options);
    },
  };
}

async function streamRecommendationEvents(
  baseUrl: string,
  body: RecommendationRequest,
  onEvent: (event: RecommendationStreamEvent) => void,
  options: { signal?: AbortSignal; lastEventId?: string },
): Promise<void> {
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  };
  if (options.lastEventId) {
    headers["Last-Event-ID"] = options.lastEventId;
  }
  const response = await fetch(`${baseUrl}/v1/recommendations/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorBody: unknown = await response.json().catch(() => undefined);
    throw apiError(response, errorBody);
  }
  if (!response.body) {
    throw new AdvisorApiError("The server returned an empty progress stream.", 502, null);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const parsed = parseSseBuffer(done && buffer ? `${buffer}\n\n` : buffer);
    buffer = parsed.remainder;
    for (const event of parsed.events) {
      onEvent(event);
    }
    if (done) {
      break;
    }
  }
}

export function parseSseBuffer(buffer: string): {
  events: RecommendationStreamEvent[];
  remainder: string;
} {
  const normalized = buffer.replaceAll("\r\n", "\n");
  const blocks = normalized.split("\n\n");
  const remainder = blocks.pop() ?? "";
  const events = blocks.flatMap((block) => {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    return data ? [JSON.parse(data) as RecommendationStreamEvent] : [];
  });
  return { events, remainder };
}

function apiError(response: Response, body?: unknown): AdvisorApiError {
  const message = extractErrorMessage(body) ?? `API request failed with status ${response.status}.`;
  return new AdvisorApiError(message, response.status, response.headers.get("X-Request-ID"));
}

function extractErrorMessage(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("error" in body)) {
    return null;
  }
  const error = body.error;
  if (!error || typeof error !== "object" || !("message" in error)) {
    return null;
  }
  return typeof error.message === "string" ? error.message : null;
}
