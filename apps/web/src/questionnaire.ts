import type { RecommendationRequest } from "@advisor/api-client";

export type Category = RecommendationRequest["category"];

export interface QuestionnaireDraft {
  category: Category;
  zipCode: string;
  stateCode: string;
  monthlyBudget: number;
  experience: "BEGINNER" | "INTERMEDIATE" | "EXPERT";
  childrenPresent: boolean;
  petsPresent: ("DOG" | "CAT")[];
  lightLevel: "LOW" | "MEDIUM" | "BRIGHT_INDIRECT" | "DIRECT";
  humidity: "LOW" | "AVERAGE" | "HIGH";
  indoorTemperatureF: number;
  availableSpace: "SMALL" | "MEDIUM" | "LARGE";
  wateringAvailability: "LOW" | "MEDIUM" | "HIGH";
  housingType: "APARTMENT" | "CONDO" | "HOUSE";
  homeSize: "SMALL" | "MEDIUM" | "LARGE";
  activityLevel: "LOW" | "MEDIUM" | "HIGH";
  hoursAlone: number;
  groomingTolerance: "LOW" | "MEDIUM" | "HIGH";
  outdoorSpace: "NONE" | "BALCONY" | "YARD";
  rentalAllowsPets: boolean;
  existingPets: ("DOG" | "CAT")[];
  affectionPreference: "INDEPENDENT" | "BALANCED" | "AFFECTIONATE";
}

export const initialDraft: QuestionnaireDraft = {
  category: "PLANT",
  zipCode: "10001",
  stateCode: "NY",
  monthlyBudget: 50,
  experience: "BEGINNER",
  childrenPresent: false,
  petsPresent: ["CAT"],
  lightLevel: "BRIGHT_INDIRECT",
  humidity: "AVERAGE",
  indoorTemperatureF: 72,
  availableSpace: "MEDIUM",
  wateringAvailability: "MEDIUM",
  housingType: "APARTMENT",
  homeSize: "MEDIUM",
  activityLevel: "MEDIUM",
  hoursAlone: 6,
  groomingTolerance: "MEDIUM",
  outdoorSpace: "NONE",
  rentalAllowsPets: true,
  existingPets: [],
  affectionPreference: "BALANCED",
};

export function buildRecommendationRequest(
  draft: QuestionnaireDraft,
  sessionId: string,
): RecommendationRequest {
  const destination = {
    zip_code: draft.zipCode,
    state_code: draft.stateCode || null,
  };

  if (draft.category === "PLANT") {
    return {
      category: "PLANT",
      session_id: sessionId,
      destination,
      use_saved_preferences: false,
      questionnaire: {
        monthly_budget: draft.monthlyBudget,
        experience: draft.experience,
        children_present: draft.childrenPresent,
        pets_present: draft.petsPresent,
        light_level: draft.lightLevel,
        humidity: draft.humidity,
        indoor_temperature_f: draft.indoorTemperatureF,
        available_space: draft.availableSpace,
        watering_availability: draft.wateringAvailability,
      },
    };
  }

  const sharedPetQuestionnaire = {
    monthly_budget: draft.monthlyBudget,
    experience: draft.experience,
    children_present: draft.childrenPresent,
    existing_pets: draft.existingPets,
    activity_level: draft.activityLevel,
    grooming_tolerance: draft.groomingTolerance,
    home_size: draft.homeSize,
    housing_type: draft.housingType,
    hours_alone: draft.hoursAlone,
    outdoor_space: draft.outdoorSpace,
    rental_allows_pets: draft.rentalAllowsPets,
  };

  if (draft.category === "CAT") {
    return {
      category: "CAT",
      session_id: sessionId,
      destination,
      use_saved_preferences: false,
      questionnaire: {
        ...sharedPetQuestionnaire,
        affection_preference: draft.affectionPreference,
      },
    };
  }

  return {
    category: "DOG",
    session_id: sessionId,
    destination,
    use_saved_preferences: false,
    questionnaire: {
      ...sharedPetQuestionnaire,
    },
  };
}
