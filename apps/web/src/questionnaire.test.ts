import { describe, expect, it } from "vitest";

import { buildRecommendationRequest, initialDraft } from "./questionnaire";

const sessionId = "00000000-0000-4000-8000-000000000001";

describe("buildRecommendationRequest", () => {
  it("only sends plant questionnaire fields for a plant request", () => {
    const request = buildRecommendationRequest(initialDraft, sessionId);

    expect(request.category).toBe("PLANT");
    expect(request.questionnaire).toMatchObject({ light_level: "BRIGHT_INDIRECT" });
    expect(request.questionnaire).not.toHaveProperty("housing_type");
  });

  it("uses the category-specific cat questionnaire", () => {
    const request = buildRecommendationRequest(
      { ...initialDraft, category: "CAT", affectionPreference: "AFFECTIONATE" },
      sessionId,
    );

    expect(request.category).toBe("CAT");
    expect(request.questionnaire).toMatchObject({ affection_preference: "AFFECTIONATE" });
    expect(request.questionnaire).toHaveProperty("outdoor_space");
  });

  it("uses the category-specific dog questionnaire", () => {
    const request = buildRecommendationRequest(
      { ...initialDraft, category: "DOG", outdoorSpace: "YARD" },
      sessionId,
    );

    expect(request.category).toBe("DOG");
    expect(request.questionnaire).toMatchObject({ outdoor_space: "YARD" });
    expect(request.questionnaire).not.toHaveProperty("affection_preference");
  });
});
